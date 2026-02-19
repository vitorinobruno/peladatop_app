from fastapi import FastAPI, Depends
from sqlmodel import SQLModel, Session, create_engine, select, delete
from models import Atleta, Pelada, PeladaCreate, Presenca, PresencaCreate, Time, TimeAtleta, TimeCreate, Jogo, Partida, EventoPartida
from datetime import date, datetime
from backend.database_antigo import get_session
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois pode restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine("sqlite:///database.db")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

@app.post("/atletas")
def criar_atleta(atleta: Atleta):
    with Session(engine) as session:
        session.add(atleta)
        session.commit()
        session.refresh(atleta)
        return atleta

@app.get("/atletas")
def listar_atletas():
    with Session(engine) as session:
        atletas = session.exec(select(Atleta)).all()
        return atletas

@app.put("/atletas/{atleta_id}")
def atualizar_atleta(
    atleta_id: int,
    dados: Atleta,
    session: Session = Depends(get_session)
):
    atleta = session.get(Atleta, atleta_id)
    if not atleta:
        raise HTTPException(404, "Atleta não encontrado")

    atleta.nome = dados.nome
    atleta.nivel = dados.nivel
    atleta.posicao = dados.posicao
    atleta.mensalista = dados.mensalista

    session.add(atleta)
    session.commit()
    session.refresh(atleta)

    return atleta


@app.post("/peladas")
def criar_pelada(
    pelada_in: PeladaCreate,
    session: Session = Depends(get_session)
):
    pelada = Pelada(
        data=pelada_in.data,
        local=pelada_in.local,
        status="planejada"
    )
    session.add(pelada)
    session.commit()
    session.refresh(pelada)
    return {
        "id": pelada.id,
        "data": pelada.data,
        "local": pelada.local
    }

@app.get("/peladas")
def listar_peladas(session: Session = Depends(get_session)):
    peladas = session.exec(select(Pelada)).all()

    return [
        {
            "id": p.id,
            "data": p.data,
            "local": p.local
        }
        for p in peladas
    ]

@app.delete("/peladas/{pelada_id}")
def excluir_pelada(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    pelada = session.get(Pelada, pelada_id)

    if not pelada:
        raise HTTPException(status_code=404, detail="Pelada não encontrada")

    session.delete(pelada)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(500, str(e))

    return {"msg": "Pelada excluída com sucesso"}

@app.post("/peladas/{pelada_id}/presencas")
def salvar_presencas(
    pelada_id: int,
    payload: PresencaCreate,
    session: Session = Depends(get_session)
):
    for atleta_id in payload.atletas_ids:
        p = Presenca(
            pelada_id=pelada_id,
            atleta_id=atleta_id
        )
        session.add(p)

    session.commit()
    return {"msg": "Presenças registradas"}

@app.get("/peladas/{pelada_id}/presencas")
def listar_presencas(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    atletas = session.exec(
        select(Atleta)
        .join(Presenca)
        .where(
            Presenca.pelada_id == pelada_id,
            Presenca.confirmado == True
        )
    ).all()

    return [
        {
            "id": a.id,
            "nome": a.nome,
            "posicao": a.posicao,
            "mensalista": a.mensalista
        }
        for a in atletas
    ]

@app.post("/peladas/{pelada_id}/times")
def criar_times(
    pelada_id: int,
    times: list[TimeCreate],
    session: Session = Depends(get_session)
):
    # Remove times antigos
    times_antigos = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    for t in times_antigos:
        session.exec(
            delete(TimeAtleta).where(TimeAtleta.time_id == t.id)
        )
        session.delete(t)

    session.commit()

    # apagar jogos da pelada
    session.exec(
        delete(Jogo).where(Jogo.pelada_id == pelada_id)
    )

    # Cria novos times
    for t in times:
        time = Time(
            pelada_id=pelada_id,
            nome=t.nome,
            cor=t.cor
        )
        session.add(time)
        session.commit()
        session.refresh(time)

        # 👇 AQUI É O PONTO-CHAVE
        for atleta_id in t.atletas_ids:
            session.add(
                TimeAtleta(
                    time_id=time.id,
                    atleta_id=atleta_id
                )
            )

    session.commit()
    return {"msg": "Times salvos com sucesso"}

@app.get("/peladas/{pelada_id}/times")
def listar_times(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    times = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    resultado = []

    for time in times:
        atletas = session.exec(
            select(Atleta)
            .join(TimeAtleta)
            .where(TimeAtleta.time_id == time.id)
        ).all()

        resultado.append({
            "id": time.id,
            "nome": time.nome,
            "cor": time.cor,
            "atletas": [
                {"id": a.id, "nome": a.nome} for a in atletas
            ]
        })

    return resultado

@app.post("/peladas/{pelada_id}/jogos")
def criar_jogos(
    pelada_id: int,
    tempo_minutos: int,
    session: Session = Depends(get_session)
):
    jogos_existentes = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    if jogos_existentes:
        return jogos_existentes

    times = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    jogos = []

    if len(times) == 2:
        jogos.append(
            Jogo(
                pelada_id=pelada_id,
                time_a_id=times[0].id,
                time_b_id=times[1].id,
                tempo_minutos=tempo_minutos
            )
        )

    elif len(times) == 3:
        for i in range(len(times)):
            for j in range(len(times)):
                if i != j:
                    jogos.append(
                        Jogo(
                            pelada_id=pelada_id,
                            time_a_id=times[i].id,
                            time_b_id=times[j].id,
                            tempo_minutos=tempo_minutos
                        )
                    )

    session.add_all(jogos)
    session.commit()

    return jogos

@app.get("/peladas/{pelada_id}/jogos")
def listar_jogos(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    jogos = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    resultado = []

    for j in jogos:
        time_a = session.get(Time, j.time_a_id)
        time_b = session.get(Time, j.time_b_id)

        resultado.append({
            "id": j.id,
            "pelada_id": j.pelada_id,
            "status": j.status,
            "gols_time_a": j.gols_time_a,
            "gols_time_b": j.gols_time_b,
            "time_a_id": j.time_a_id,
            "time_b_id": j.time_b_id,
            "tempo_minutos": j.tempo_minutos,  
            "nome_time_a": time_a.nome if time_a else None,
            "nome_time_b": time_b.nome if time_b else None
        })

    return resultado


@app.post("/jogos/{jogo_id}/partida")
def criar_ou_obter_partida(
    jogo_id: int,
    session: Session = Depends(get_session)
):
    jogo = session.get(Jogo, jogo_id)
    if not jogo:
        raise HTTPException(404, "Jogo não encontrado")

    # 1️⃣ procura partida em andamento
    partida = session.exec(
        select(Partida)
        .where(Partida.jogo_id == jogo_id)
        .where(Partida.status == "em_andamento")
    ).first()

    if partida:
        return partida

    # 2️⃣ procura última partida finalizada
    partida_finalizada = session.exec(
        select(Partida)
        .where(Partida.jogo_id == jogo_id)
        .where(Partida.status == "finalizada")
        .order_by(Partida.id.desc())
    ).first()

    if partida_finalizada:
        return partida_finalizada

    # 3️⃣ se não existe nenhuma → criar nova
    partida = Partida(
        jogo_id=jogo_id,
        tempo_minutos=jogo.tempo_minutos,
        iniciada_em=datetime.utcnow(),
        placar_a=0,
        placar_b=0,
        status="em_andamento"
    )

    jogo.status = "em_andamento"

    session.add(partida)
    session.add(jogo)
    session.commit()
    session.refresh(partida)

    return partida


@app.post("/partidas/{partida_id}/gol")
def registrar_gol(
    partida_id: int,
    time_id: int,
    atleta_gol_id: int,
    atleta_assistencia_id: int | None = None,
    instante_segundos: int = 0,
    session: Session = Depends(get_session)
):
    partida = session.get(Partida, partida_id)
    if not partida:
        raise HTTPException(404, "Partida não encontrada")

    jogo = session.get(Jogo, partida.jogo_id)

    if time_id == jogo.time_a_id:
        partida.placar_a += 1
    elif time_id == jogo.time_b_id:
        partida.placar_b += 1
    else:
        raise HTTPException(400, "Time não pertence ao jogo")

    gol = EventoPartida(
        partida_id=partida_id,
        time_id=time_id,
        atleta_gol_id=atleta_gol_id,
        atleta_assistencia_id=atleta_assistencia_id,
        instante_segundos=instante_segundos
    )

    session.add(gol)
    session.add(partida)
    session.commit()

    return {"ok": True}

@app.get("/partidas/{partida_id}")
def obter_partida(
    partida_id: int,
    session: Session = Depends(get_session)
):
    partida = session.get(Partida, partida_id)
    if not partida:
        raise HTTPException(404, "Partida não encontrada")

    jogo = session.get(Jogo, partida.jogo_id)

    time_a = session.get(Time, jogo.time_a_id)
    time_b = session.get(Time, jogo.time_b_id)

    atletas_a = session.exec(
        select(Atleta).join(TimeAtleta).where(TimeAtleta.time_id == time_a.id)
    ).all()

    atletas_b = session.exec(
        select(Atleta).join(TimeAtleta).where(TimeAtleta.time_id == time_b.id)
    ).all()

    return {
        "id": partida.id,
        "tempo_minutos": partida.tempo_minutos,
        "iniciada_em": partida.iniciada_em,
        "placar_a": partida.placar_a,
        "placar_b": partida.placar_b,
        "status": partida.status,
        "time_a": {
            "id": time_a.id,
            "nome": time_a.nome,
            "cor": time_a.cor,
            "atletas": [{"id": a.id, "nome": a.nome} for a in atletas_a],
        },
        "time_b": {
            "id": time_b.id,
            "nome": time_b.nome,
            "cor": time_b.cor,
            "atletas": [{"id": a.id, "nome": a.nome} for a in atletas_b],
        },
    }

@app.post("/partidas/{partida_id}/finalizar")
def finalizar_partida(
    partida_id: int,
    session: Session = Depends(get_session)
):
    partida = session.get(Partida, partida_id)
    if not partida:
        raise HTTPException(404, "Partida não encontrada")

    if partida.status == "finalizada":
        return {"msg": "Partida já finalizada"}

    jogo = session.get(Jogo, partida.jogo_id)

    # copia placar para o jogo
    jogo.gols_time_a = partida.placar_a
    jogo.gols_time_b = partida.placar_b

    jogo.status = "finalizado"
    jogo.finalizado_em = datetime.utcnow()

    partida.status = "finalizada"
    partida.finalizada_em = datetime.utcnow()

    session.add(jogo)
    session.add(partida)
    session.commit()

    return {"msg": "Partida finalizada com sucesso"}

@app.get("/peladas/{pelada_id}/classificacao")
def classificacao_pelada(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    times = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    jogos = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    tabela = {
        t.id: {
            "time_id": t.id,
            "nome": t.nome,
            "pontos": 0,
            "vitorias": 0,
            "empates": 0,
            "derrotas": 0,
            "gols_pro": 0,
            "gols_contra": 0,
        }
        for t in times
    }

    for j in jogos:
        if j.status != "finalizado":
            continue

        a = tabela[j.time_a_id]
        b = tabela[j.time_b_id]

        a["gols_pro"] += j.gols_time_a
        a["gols_contra"] += j.gols_time_b

        b["gols_pro"] += j.gols_time_b
        b["gols_contra"] += j.gols_time_a

        if j.gols_time_a > j.gols_time_b:
            a["pontos"] += 3
            a["vitorias"] += 1
            b["derrotas"] += 1

        elif j.gols_time_b > j.gols_time_a:
            b["pontos"] += 3
            b["vitorias"] += 1
            a["derrotas"] += 1

        else:
            a["pontos"] += 1
            b["pontos"] += 1
            a["empates"] += 1
            b["empates"] += 1

    tabela_lista = list(tabela.values())

    tabela_lista.sort(
        key=lambda x: (
            x["pontos"],
            x["gols_pro"] - x["gols_contra"],
            x["gols_pro"]
        ),
        reverse=True
    )

    return tabela_lista

@app.post("/peladas/{pelada_id}/finalizar")
def finalizar_pelada(
    pelada_id: int,
    session: Session = Depends(get_session)
):
    pelada = session.get(Pelada, pelada_id)
    if not pelada:
        raise HTTPException(404, "Pelada não encontrada")

    # --------------------------------------------------
    # Se já finalizada → apenas retorna campeão salvo
    # --------------------------------------------------
    if pelada.status == "finalizada":
        return {
            "msg": "Pelada já finalizada",
            "campeao": pelada.campeao
        }

    # --------------------------------------------------
    # Calcula classificação
    # --------------------------------------------------
    classificacao = classificacao_pelada(pelada_id, session)

    if not classificacao:
        raise HTTPException(400, "Nenhum jogo finalizado")

    campeao = classificacao[0]
    time_campeao_id = campeao["time_id"]
    nome_campeao = campeao["nome"]

    # --------------------------------------------------
    # Incrementa títulos dos atletas campeões
    # --------------------------------------------------
    atletas = session.exec(
        select(Atleta)
        .join(TimeAtleta)
        .where(TimeAtleta.time_id == time_campeao_id)
    ).all()

    for atleta in atletas:
        atleta.titulos += 1
        session.add(atleta)

    # --------------------------------------------------
    # Salva campeão e finaliza pelada
    # --------------------------------------------------
    pelada.status = "finalizada"
    pelada.campeao = nome_campeao   # ⭐ AGORA PERSISTE
    session.add(pelada)

    session.commit()

    return {
        "msg": "Pelada finalizada com sucesso",
        "campeao": nome_campeao
    }

@app.get("/estatisticas/gols")
def ranking_gols(session: Session = Depends(get_session)):

    eventos = session.exec(select(EventoPartida)).all()

    contagem = {}

    for e in eventos:
        contagem[e.atleta_gol_id] = contagem.get(e.atleta_gol_id, 0) + 1

    ranking = []

    for atleta_id, gols in contagem.items():
        atleta = session.get(Atleta, atleta_id)
        ranking.append({
            "atleta_id": atleta.id,
            "nome": atleta.nome,
            "gols": gols
        })

    ranking.sort(key=lambda x: x["gols"], reverse=True)
    return ranking

@app.get("/estatisticas/assistencias")
def ranking_assistencias(session: Session = Depends(get_session)):

    eventos = session.exec(select(EventoPartida)).all()

    contagem = {}

    for e in eventos:
        if e.atleta_assistencia_id:
            contagem[e.atleta_assistencia_id] = \
                contagem.get(e.atleta_assistencia_id, 0) + 1

    ranking = []

    for atleta_id, assists in contagem.items():
        atleta = session.get(Atleta, atleta_id)
        ranking.append({
            "atleta_id": atleta.id,
            "nome": atleta.nome,
            "assistencias": assists
        })

    ranking.sort(key=lambda x: x["assistencias"], reverse=True)
    return ranking

@app.get("/estatisticas/titulos")
def ranking_titulos(session: Session = Depends(get_session)):

    atletas = session.exec(select(Atleta)).all()

    ranking = [
        {
            "atleta_id": a.id,
            "nome": a.nome,
            "titulos": a.titulos
        }
        for a in atletas
        if a.titulos > 0
    ]

    ranking.sort(key=lambda x: x["titulos"], reverse=True)
    return ranking

@app.get("/estatisticas/pontos-ano")
def pontos_no_ano(session: Session = Depends(get_session)):

    peladas = session.exec(
        select(Pelada).where(Pelada.status == "finalizada")
    ).all()

    tabela = {}

    for p in peladas:
        if not p.campeao:
            continue

        tabela[p.campeao] = tabela.get(p.campeao, 0) + 1

    ranking = [
        {"time": nome, "pontos": pts}
        for nome, pts in tabela.items()
    ]

    ranking.sort(key=lambda x: x["pontos"], reverse=True)
    return ranking



