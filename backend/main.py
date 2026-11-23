from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlmodel import SQLModel, Session, create_engine, select, delete
from models import Atleta, Pelada, PeladaCreate, Presenca, PresencaCreate, Time, TimeAtleta, TimeCreate, Jogo, Partida, EventoPartida
from datetime import date, datetime
from database import get_session, engine
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import col
import os
from groq import Groq
import torneio as trn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois pode restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    from database import engine
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
    if pelada_in.tipo not in ("normal", "torneio"):
        raise HTTPException(400, "Tipo de pelada inválido")
    pelada = Pelada(
        data=pelada_in.data,
        local=pelada_in.local,
        status="planejada",
        tipo=pelada_in.tipo,
    )
    session.add(pelada)
    session.commit()
    session.refresh(pelada)
    return {
        "id": pelada.id,
        "data": pelada.data,
        "local": pelada.local,
        "tipo": pelada.tipo,
    }

@app.get("/peladas")
def listar_peladas(
    session: Session = Depends(get_session),
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
):
    query = select(Pelada).where(Pelada.deletada == False).order_by(col(Pelada.data).desc())
    if data_inicio:
        query = query.where(Pelada.data >= data_inicio)
    if data_fim:
        query = query.where(Pelada.data <= data_fim)
    peladas = session.exec(query).all()

    return [
        {
            "id": p.id,
            "data": p.data,
            "local": p.local,
            "status": p.status,
            "campeao": p.campeao,
            "tipo": p.tipo,
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

    pelada.deletada = True
    try:
        session.add(pelada)
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
        existente = session.exec(
            select(Presenca).where(
                Presenca.pelada_id == pelada_id,
                Presenca.atleta_id == atleta_id
            )
        ).first()
        if existente:
            existente.confirmado = True
            session.add(existente)
        else:
            session.add(Presenca(pelada_id=pelada_id, atleta_id=atleta_id))

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
        .distinct()
    ).all()

    return [
        {
            "id": a.id,
            "nome": a.nome,
            "posicao": a.posicao,
            "mensalista": a.mensalista,
            "nivel": a.nivel,
        }
        for a in atletas
    ]

@app.post("/peladas/{pelada_id}/times")
def criar_times(
    pelada_id: int,
    times: list[TimeCreate],
    session: Session = Depends(get_session)
):
    pelada = session.get(Pelada, pelada_id)
    eh_torneio = pelada is not None and pelada.tipo == "torneio"

    if eh_torneio and sorted(t.cor for t in times) != sorted(trn.CORES_TORNEIO):
        raise HTTPException(
            400, "Torneio exige 4 times, um de cada cor: Branco, Verde, Laranja e Azul"
        )

    jogos_existentes = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    times_existentes = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    if eh_torneio:
        # A tabela do torneio é por cor: pareia times existentes e novos pela cor
        ordem_cor = {c: i for i, c in enumerate(trn.CORES_TORNEIO)}
        times = sorted(times, key=lambda t: ordem_cor.get(t.cor, 99))
        times_existentes = sorted(times_existentes, key=lambda t: ordem_cor.get(t.cor, 99))

    algum_jogo_iniciado = any(
        j.status in ("em_andamento", "finalizado") for j in jogos_existentes
    )

    if jogos_existentes and algum_jogo_iniciado:
        # Algum jogo já foi iniciado: apenas atualiza atletas dos times existentes
        for i, time_existente in enumerate(times_existentes):
            if i >= len(times):
                break
            t = times[i]
            time_existente.nome = t.nome
            time_existente.cor = t.cor
            session.add(time_existente)

            session.exec(
                delete(TimeAtleta).where(TimeAtleta.time_id == time_existente.id)
            )
            for atleta_id in t.atletas_ids:
                session.add(TimeAtleta(
                    time_id=time_existente.id,
                    atleta_id=atleta_id
                ))

        session.commit()
        return {"msg": "Times atualizados com sucesso"}

    if jogos_existentes:
        # Jogos gerados mas nenhum iniciado: apaga jogos e times, recria tudo
        for j in jogos_existentes:
            session.exec(delete(Partida).where(Partida.jogo_id == j.id))
            session.delete(j)
        session.commit()

    # Sem jogos (ou após limpeza): recria times do zero
    for t in times_existentes:
        session.exec(
            delete(TimeAtleta).where(TimeAtleta.time_id == t.id)
        )
        session.delete(t)
    session.commit()

    for t in times:
        time = Time(pelada_id=pelada_id, nome=t.nome, cor=t.cor)
        session.add(time)
        session.commit()
        session.refresh(time)

        for atleta_id in t.atletas_ids:
            session.add(TimeAtleta(time_id=time.id, atleta_id=atleta_id))

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
    pausavel: bool = False,
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

    pelada = session.get(Pelada, pelada_id)
    if pelada and pelada.tipo == "torneio":
        por_cor = {t.cor: t for t in times}
        if len(times) != 4 or sorted(por_cor) != sorted(trn.CORES_TORNEIO):
            raise HTTPException(
                400, "Torneio exige 4 times salvos, um de cada cor: Branco, Verde, Laranja e Azul"
            )
        for ordem, (cor_a, cor_b) in enumerate(trn.TABELA_GRUPOS, start=1):
            jogos.append(Jogo(
                pelada_id=pelada_id,
                time_a_id=por_cor[cor_a].id,
                time_b_id=por_cor[cor_b].id,
                tempo_minutos=tempo_minutos,
                pausavel=pausavel,
                fase="grupos",
                ordem=ordem,
            ))
        session.add_all(jogos)
        session.commit()
        return jogos

    if len(times) == 2:
        jogos.append(
            Jogo(
                pelada_id=pelada_id,
                time_a_id=times[0].id,
                time_b_id=times[1].id,
                tempo_minutos=tempo_minutos,
                pausavel=pausavel
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
                            tempo_minutos=tempo_minutos,
                            pausavel=pausavel
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
    jogos = sorted(jogos, key=lambda j: (j.ordem is None, j.ordem or 0, j.id))

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
            "pausavel": j.pausavel,
            "nome_time_a": time_a.nome if time_a else None,
            "nome_time_b": time_b.nome if time_b else None,
            "cor_time_a": time_a.cor if time_a else None,
            "cor_time_b": time_b.cor if time_b else None,
            "fase": j.fase,
            "ordem": j.ordem,
            "penaltis_a": j.penaltis_a,
            "penaltis_b": j.penaltis_b,
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
    atleta_gol_id: int | None = None,
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
        jogo.gols_time_a += 1  # ← adiciona isso
    elif time_id == jogo.time_b_id:
        partida.placar_b += 1
        jogo.gols_time_b += 1  # ← adiciona isso
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
    session.add(jogo)  # ← adiciona isso
    session.commit()

    # Gol adicionado depois de um jogo da 1ª fase finalizado pode mudar a classificação
    if jogo.status == "finalizado" and trn.eh_grupos(jogo):
        _sincronizar_segunda_fase(jogo.pelada_id, session)

    return {"ok": True}

@app.put("/partidas/{partida_id}/gol/{evento_id}")
def editar_gol(
    partida_id: int,
    evento_id: int,
    atleta_gol_id: int,
    atleta_assistencia_id: int | None = None,
    session: Session = Depends(get_session)
):
    evento = session.get(EventoPartida, evento_id)
    if not evento or evento.partida_id != partida_id:
        raise HTTPException(404, "Evento não encontrado")

    evento.atleta_gol_id = atleta_gol_id
    evento.atleta_assistencia_id = atleta_assistencia_id

    session.add(evento)
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

    goleiros = session.exec(
        select(Atleta)
        .join(Presenca)
        .where(
            Presenca.pelada_id == jogo.pelada_id,
            Presenca.confirmado == True,
            Atleta.posicao == "goleiro"
        )
    ).all()

    eventos = session.exec(
        select(EventoPartida)
        .where(EventoPartida.partida_id == partida.id)
        .order_by(EventoPartida.instante_segundos)
    ).all()

    todos_atletas = {a.id: a.nome for a in [*atletas_a, *atletas_b, *goleiros]}

    def formatar_evento(e):
        return {
            "id": e.id,
            "instante_segundos": e.instante_segundos,
            "time_id": e.time_id,
            "atleta_gol_id": e.atleta_gol_id,
            "atleta_gol_nome": todos_atletas.get(e.atleta_gol_id, "?") if e.atleta_gol_id else None,
            "atleta_assistencia_id": e.atleta_assistencia_id,
            "atleta_assistencia_nome": todos_atletas.get(e.atleta_assistencia_id, "?") if e.atleta_assistencia_id else None,
        }

    return {
        "id": partida.id,
        "tempo_minutos": partida.tempo_minutos,
        "pausavel": jogo.pausavel,
        "jogo_id": jogo.id,
        "fase": jogo.fase,
        "ordem": jogo.ordem,
        "penaltis_a": jogo.penaltis_a,
        "penaltis_b": jogo.penaltis_b,
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
        "goleiros": [{"id": a.id, "nome": a.nome} for a in goleiros],
        "eventos": [formatar_evento(e) for e in eventos],
    }

@app.post("/partidas/{partida_id}/finalizar")
def finalizar_partida(
    partida_id: int,
    penaltis_a: Optional[int] = None,
    penaltis_b: Optional[int] = None,
    session: Session = Depends(get_session)
):
    partida = session.get(Partida, partida_id)
    if not partida:
        raise HTTPException(404, "Partida não encontrada")

    if partida.status == "finalizada":
        return {"msg": "Partida já finalizada"}

    jogo = session.get(Jogo, partida.jogo_id)

    # Mata-mata do torneio empatado → exige placar dos pênaltis
    if trn.eh_mata_mata(jogo):
        if partida.placar_a == partida.placar_b:
            if penaltis_a is None or penaltis_b is None:
                raise HTTPException(400, "Jogo empatado: informe o placar dos pênaltis")
            if penaltis_a == penaltis_b:
                raise HTTPException(400, "Placar dos pênaltis não pode terminar empatado")
            jogo.penaltis_a = penaltis_a
            jogo.penaltis_b = penaltis_b
        else:
            jogo.penaltis_a = None
            jogo.penaltis_b = None

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

    if trn.eh_grupos(jogo):
        _sincronizar_segunda_fase(jogo.pelada_id, session)

    return {"msg": "Partida finalizada com sucesso"}


@app.put("/jogos/{jogo_id}/penaltis")
def definir_penaltis(
    jogo_id: int,
    penaltis_a: int,
    penaltis_b: int,
    session: Session = Depends(get_session)
):
    """Define/corrige pênaltis de um jogo de mata-mata já finalizado e empatado."""
    jogo = session.get(Jogo, jogo_id)
    if not jogo:
        raise HTTPException(404, "Jogo não encontrado")
    if not trn.eh_mata_mata(jogo):
        raise HTTPException(400, "Pênaltis só existem na final e na disputa de 3º lugar")
    if jogo.gols_time_a != jogo.gols_time_b:
        raise HTTPException(400, "Jogo não terminou empatado")
    if penaltis_a == penaltis_b:
        raise HTTPException(400, "Placar dos pênaltis não pode terminar empatado")
    jogo.penaltis_a = penaltis_a
    jogo.penaltis_b = penaltis_b
    session.add(jogo)
    session.commit()
    return {"ok": True}

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

    pelada = session.get(Pelada, pelada_id)
    if pelada and pelada.tipo == "torneio":
        return _classificacao_grupos_torneio(times, jogos)["tabela"]

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
    # Torneio: campeão = vencedor da final (inclui pênaltis).
    # Não incrementa títulos nem entra no ranking anual de times.
    # --------------------------------------------------
    if pelada.tipo == "torneio":
        final = session.exec(
            select(Jogo).where(Jogo.pelada_id == pelada_id, Jogo.fase == "final")
        ).first()
        if not final or final.status != "finalizado":
            raise HTTPException(400, "A final ainda não foi disputada")
        campeao_id = trn.vencedor(final)
        if campeao_id is None:
            raise HTTPException(400, "Final empatada sem placar de pênaltis")
        time_campeao = session.get(Time, campeao_id)
        pelada.status = "finalizada"
        pelada.campeao = time_campeao.nome
        session.add(pelada)
        session.commit()
        return {"msg": "Torneio finalizado com sucesso", "campeao": pelada.campeao}

    # --------------------------------------------------
    # Calcula classificação
    # --------------------------------------------------
    classificacao = classificacao_pelada(pelada_id, session)

    if not classificacao:
        raise HTTPException(400, "Nenhum jogo finalizado")

    campeao = classificacao[0]

    # --------------------------------------------------
    # Verifica empate no topo da tabela
    # --------------------------------------------------
    empate_no_topo = len(classificacao) > 1 and (
        campeao["pontos"] == classificacao[1]["pontos"] and
        (campeao["gols_pro"] - campeao["gols_contra"]) == (classificacao[1]["gols_pro"] - classificacao[1]["gols_contra"]) and
        campeao["gols_pro"] == classificacao[1]["gols_pro"]
    )

    pelada.status = "finalizada"

    if empate_no_topo:
        pelada.campeao = None
        session.add(pelada)
        session.commit()
        return {"msg": "Pelada finalizada — empate, sem campeão", "campeao": None}

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
    pelada.campeao = nome_campeao
    session.add(pelada)

    session.commit()

    return {
        "msg": "Pelada finalizada com sucesso",
        "campeao": nome_campeao
    }

# ==================================================
# TORNEIO DE FIM DE ANO
# ==================================================

def _classificacao_grupos_torneio(times, jogos):
    """Classificação da 1ª fase. Se a 2ª fase já existe (ex: definida por sorteio
    manual), a ordem da tabela respeita quem foi para a final."""
    resultado = trn.classificar_grupos(times, jogos)
    final = next((j for j in jogos if j.fase == "final"), None)
    if final and resultado["sorteio_necessario"]:
        finalistas = {final.time_a_id, final.time_b_id}
        tabela = sorted(
            resultado["tabela"],
            key=lambda r: (r["time_id"] not in finalistas, r["posicao"]),
        )
        for i, r in enumerate(tabela, start=1):
            r["posicao"] = i
        resultado["tabela"] = tabela
        resultado["sorteio_resolvido"] = True
    return resultado


def _criar_ou_atualizar_mata_mata(pelada_id: int, ordem: list[int], session: Session):
    """ordem = [1º, 2º, 3º, 4º] da 1ª fase → cria/atualiza jogos 07 e 08."""
    jogos = session.exec(select(Jogo).where(Jogo.pelada_id == pelada_id)).all()
    mata = {j.fase: j for j in jogos if trn.eh_mata_mata(j)}
    if any(j.status != "nao_iniciado" for j in mata.values()):
        raise HTTPException(400, "A 2ª fase já começou e não pode mais ser alterada")

    ref = next((j for j in jogos if trn.eh_grupos(j)), None)
    tempo = ref.tempo_minutos if ref else trn.TEMPO_PADRAO_MINUTOS
    pausavel = ref.pausavel if ref else True

    confrontos = {
        "terceiro": (trn.ORDEM_TERCEIRO, ordem[2], ordem[3]),
        "final": (trn.ORDEM_FINAL, ordem[0], ordem[1]),
    }
    for fase, (num, time_a, time_b) in confrontos.items():
        jogo = mata.get(fase) or Jogo(
            pelada_id=pelada_id, time_a_id=time_a, time_b_id=time_b,
            tempo_minutos=tempo, pausavel=pausavel, fase=fase, ordem=num,
        )
        jogo.time_a_id = time_a
        jogo.time_b_id = time_b
        session.add(jogo)
    session.commit()


def _sincronizar_segunda_fase(pelada_id: int, session: Session):
    """Gera (ou recalcula, se ainda não começou) a 2ª fase quando os 6 jogos
    da 1ª fase estão finalizados. Se houver empate que dependa de sorteio,
    aguarda a escolha manual (POST /peladas/{id}/torneio/segunda-fase)."""
    pelada = session.get(Pelada, pelada_id)
    if not pelada or pelada.tipo != "torneio":
        return

    jogos = session.exec(select(Jogo).where(Jogo.pelada_id == pelada_id)).all()
    grupos = [j for j in jogos if trn.eh_grupos(j)]
    mata = [j for j in jogos if trn.eh_mata_mata(j)]

    if len(grupos) < len(trn.TABELA_GRUPOS) or any(j.status != "finalizado" for j in grupos):
        return
    if any(j.status != "nao_iniciado" for j in mata):
        return  # 2ª fase em andamento: não mexe

    times = session.exec(select(Time).where(Time.pelada_id == pelada_id)).all()
    cls = trn.classificar_grupos(times, jogos)

    if cls["sorteio_necessario"]:
        # Mantém escolha manual existente se ainda for compatível com a tabela
        final = next((j for j in mata if j.fase == "final"), None)
        if final:
            finalistas = {final.time_a_id, final.time_b_id}
            empatados = set(cls["empatados"])
            acima = {r["time_id"] for r in cls["tabela"]
                     if r["time_id"] not in empatados and r["posicao"] <= 2}
            if acima <= finalistas <= (acima | empatados):
                return
            for j in mata:
                session.delete(j)
            session.commit()
        return

    _criar_ou_atualizar_mata_mata(pelada_id, [r["time_id"] for r in cls["tabela"]], session)


@app.get("/peladas/{pelada_id}/torneio")
def resumo_torneio(pelada_id: int, session: Session = Depends(get_session)):
    pelada = session.get(Pelada, pelada_id)
    if not pelada or pelada.tipo != "torneio":
        raise HTTPException(404, "Torneio não encontrado")

    times = session.exec(select(Time).where(Time.pelada_id == pelada_id)).all()
    jogos = session.exec(select(Jogo).where(Jogo.pelada_id == pelada_id)).all()
    times_map = {t.id: t for t in times}

    grupos = _classificacao_grupos_torneio(times, jogos)
    grupos_finalizados = (
        sum(1 for j in jogos if trn.eh_grupos(j) and j.status == "finalizado")
        == len(trn.TABELA_GRUPOS)
    )
    segunda_fase_gerada = any(trn.eh_mata_mata(j) for j in jogos)

    def time_info(tid, posicao):
        if tid is None:
            return None
        t = times_map.get(tid)
        return {"posicao": posicao, "time_id": tid,
                "nome": t.nome if t else "?", "cor": t.cor if t else None}

    final_ids = trn.classificacao_final(jogos)

    return {
        "grupos": grupos,
        "grupos_finalizados": grupos_finalizados,
        "segunda_fase_gerada": segunda_fase_gerada,
        "aguardando_sorteio": grupos_finalizados and grupos["sorteio_necessario"] and not segunda_fase_gerada,
        "classificacao_final": [time_info(tid, i) for i, tid in enumerate(final_ids, start=1)],
    }


class SegundaFaseRequest(SQLModel):
    finalistas: list[int]  # time_ids escolhidos (após sorteio) entre os empatados


@app.post("/peladas/{pelada_id}/torneio/segunda-fase")
def definir_segunda_fase(
    pelada_id: int,
    body: SegundaFaseRequest,
    session: Session = Depends(get_session)
):
    """Resolve o critério iv (sorteio): informa quem dos empatados vai para a final."""
    pelada = session.get(Pelada, pelada_id)
    if not pelada or pelada.tipo != "torneio":
        raise HTTPException(404, "Torneio não encontrado")

    times = session.exec(select(Time).where(Time.pelada_id == pelada_id)).all()
    jogos = session.exec(select(Jogo).where(Jogo.pelada_id == pelada_id)).all()
    grupos = [j for j in jogos if trn.eh_grupos(j)]
    if any(j.status != "finalizado" for j in grupos):
        raise HTTPException(400, "A 1ª fase ainda não terminou")

    cls = trn.classificar_grupos(times, jogos)
    if not cls["sorteio_necessario"]:
        raise HTTPException(400, "Não há empate a ser resolvido por sorteio")

    escolhidos = list(dict.fromkeys(body.finalistas))
    empatados = cls["empatados"]
    if len(escolhidos) != cls["vagas_final"] or not set(escolhidos) <= set(empatados):
        raise HTTPException(
            400, f"Escolha exatamente {cls['vagas_final']} time(s) entre os empatados"
        )

    restantes = [t for t in empatados if t not in escolhidos]
    ordem = []
    bloco_inserido = False
    for r in cls["tabela"]:
        tid = r["time_id"]
        if tid in empatados:
            if not bloco_inserido:
                ordem.extend(escolhidos + restantes)
                bloco_inserido = True
        else:
            ordem.append(tid)

    _criar_ou_atualizar_mata_mata(pelada_id, ordem, session)
    return {"ok": True}


@app.get("/estatisticas/gols")
def ranking_gols(pelada_id: Optional[int] = None, session: Session = Depends(get_session)):
    
    if pelada_id:
        # busca jogo_ids da pelada
        jogos = session.exec(
            select(Jogo).where(Jogo.pelada_id == pelada_id)
        ).all()
        jogo_ids = [j.id for j in jogos]
        
        # busca partida_ids dos jogos
        partidas = session.exec(
            select(Partida).where(col(Partida.jogo_id).in_(jogo_ids))
        ).all()
        partida_ids = [p.id for p in partidas]

        eventos = session.exec(
            select(EventoPartida).where(
                col(EventoPartida.atleta_gol_id) != None,
                col(EventoPartida.partida_id).in_(partida_ids)
            )
        ).all()
    else:
        eventos = session.exec(
            select(EventoPartida).where(col(EventoPartida.atleta_gol_id) != None)
        ).all()

    contagem = {}
    for e in eventos:
        contagem[e.atleta_gol_id] = contagem.get(e.atleta_gol_id, 0) + 1

    ranking = []
    for atleta_id, gols in contagem.items():
        atleta = session.get(Atleta, atleta_id)
        if atleta:
            ranking.append({"atleta_id": atleta.id, "nome": atleta.nome, "gols": gols})

    ranking.sort(key=lambda x: x["gols"], reverse=True)
    return ranking


@app.get("/estatisticas/assistencias")
def ranking_assistencias(pelada_id: Optional[int] = None, session: Session = Depends(get_session)):
    
    if pelada_id:
        jogos = session.exec(
            select(Jogo).where(Jogo.pelada_id == pelada_id)
        ).all()
        jogo_ids = [j.id for j in jogos]
        
        partidas = session.exec(
            select(Partida).where(col(Partida.jogo_id).in_(jogo_ids))
        ).all()
        partida_ids = [p.id for p in partidas]

        eventos = session.exec(
            select(EventoPartida).where(
                col(EventoPartida.atleta_assistencia_id) != None,
                col(EventoPartida.partida_id).in_(partida_ids)
            )
        ).all()
    else:
        eventos = session.exec(
            select(EventoPartida).where(col(EventoPartida.atleta_assistencia_id) != None)
        ).all()

    contagem = {}
    for e in eventos:
        contagem[e.atleta_assistencia_id] = contagem.get(e.atleta_assistencia_id, 0) + 1

    ranking = []
    for atleta_id, assistencias in contagem.items():
        atleta = session.get(Atleta, atleta_id)
        if atleta:
            ranking.append({"atleta_id": atleta.id, "nome": atleta.nome, "assistencias": assistencias})

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
def pontos_no_ano(ano: Optional[int] = None, session: Session = Depends(get_session)):

    query = select(Pelada).where(Pelada.status == "finalizada", Pelada.tipo != "torneio")
    if ano:
        query = query.where(col(Pelada.data) >= date(ano, 1, 1)).where(col(Pelada.data) <= date(ano, 12, 31))
    peladas = session.exec(query).all()

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

@app.get("/peladas/{pelada_id}/presenca-link", response_class=HTMLResponse)
def pagina_presenca(pelada_id: int, session: Session = Depends(get_session)):
    pelada = session.get(Pelada, pelada_id)
    if not pelada:
        return HTMLResponse("<h2>Pelada não encontrada</h2>", status_code=404)

    atletas = session.exec(select(Atleta).where(Atleta.mensalista == True)).all()

    opcoes = "".join([
        f'<option value="{a.id}">{a.nome}</option>'
        for a in atletas
    ])

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PeladaTop — Presença</title>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f0f4f8;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 32px 24px;
                max-width: 420px;
                width: 100%;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }}
            .logo {{ text-align: center; font-size: 48px; margin-bottom: 8px; }}
            h1 {{ text-align: center; font-size: 22px; color: #1a1a1a; margin-bottom: 4px; }}
            .subtitulo {{ text-align: center; color: #666; font-size: 14px; margin-bottom: 8px; }}
            .vagas {{ text-align: center; font-size: 14px; font-weight: 600; color: #1E88E5; margin-bottom: 16px; }}
            .btn-whatsapp {{
                display: flex; align-items: center; justify-content: center; gap: 8px;
                width: 100%; padding: 12px; background: #25D366; color: white;
                border: none; border-radius: 10px; font-size: 15px; font-weight: 600;
                cursor: pointer; margin-bottom: 20px; text-decoration: none;
            }}
            .btn-whatsapp:active {{ opacity: 0.8; }}
            label {{ display: block; font-size: 14px; font-weight: 600; color: #333; margin-bottom: 8px; }}
            select {{
                width: 100%; padding: 12px 16px; border: 2px solid #e0e0e0;
                border-radius: 10px; font-size: 16px; color: #333;
                background: white; appearance: none; margin-bottom: 20px; outline: none;
            }}
            select:focus {{ border-color: #1E88E5; }}
            .botoes {{ display: flex; gap: 12px; margin-bottom: 24px; }}
            button {{
                flex: 1; padding: 14px; border: none; border-radius: 10px;
                font-size: 16px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
            }}
            button:active {{ opacity: 0.8; }}
            .btn-confirmar {{ background: #43A047; color: white; }}
            .btn-cancelar {{ background: #f5f5f5; color: #e53935; border: 2px solid #e53935; }}
            .mensagem {{
                display: none; text-align: center; padding: 16px;
                border-radius: 10px; font-size: 16px; font-weight: 600; margin-bottom: 16px;
            }}
            .sucesso {{ background: #e8f5e9; color: #2e7d32; }}
            .erro {{ background: #ffebee; color: #c62828; }}
            .divider {{ border: none; border-top: 1px solid #eee; margin: 16px 0; }}
            .secao-titulo {{ font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px; }}
            .posicao-titulo {{
                font-size: 11px; font-weight: 700; color: #888;
                text-transform: uppercase; margin-bottom: 4px; margin-top: 10px;
                letter-spacing: 0.5px;
            }}
            .atleta-item {{
                display: flex; align-items: center; padding: 8px 12px;
                margin-bottom: 6px; border-radius: 8px; font-size: 15px;
            }}
            .confirmado-item {{ background: #e8f5e9; }}
            .ausente-item {{ background: #ffebee; }}
            .sem-resposta-item {{ background: #fff8e1; }}
            .atleta-item .icone {{ margin-right: 8px; }}
            .atleta-item .nome {{ font-weight: 600; }}
            .confirmado-item .nome {{ color: #2e7d32; }}
            .ausente-item .nome {{ color: #c62828; }}
            .sem-resposta-item .nome {{ color: #f57f17; }}
            .vazio {{ color: #aaa; font-size: 14px; text-align: center; padding: 8px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="logo">⚽</div>
            <h1>PeladaTop</h1>
            <div class="subtitulo">{pelada.local} — {pelada.data}</div>
            <div class="vagas" id="vagas">Carregando...</div>

            <label>Seu nome</label>
            <select id="atleta">
                <option value="">— Selecione —</option>
                {opcoes}
            </select>

            <div class="botoes">
                <button class="btn-confirmar" onclick="responder(true)">✅ Vou!</button>
                <button class="btn-cancelar" onclick="responder(false)">❌ Não vou</button>
            </div>

            <div class="mensagem" id="mensagem"></div>

            <hr class="divider">
            <div class="secao-titulo" id="titulo-confirmados">Confirmados (0)</div>
            <div id="lista-confirmados"><div class="vazio">Carregando...</div></div>

            <hr class="divider">
            <div class="secao-titulo" id="titulo-ausentes">Ausentes (0)</div>
            <div id="lista-ausentes"><div class="vazio">Carregando...</div></div>

            <hr class="divider">
            <div class="secao-titulo" id="titulo-sem-resposta">Sem resposta (0)</div>
            <div id="lista-sem-resposta"><div class="vazio">Carregando...</div></div>

            <button class="btn-whatsapp" onclick="compartilhar()">
                📤 Exportar lista no WhatsApp
            </button>
        </div>

        <script>
            const peladaId = {pelada_id};
            const baseUrl = window.location.origin;
            const ordemPosicoes = ['goleiro', 'zagueiro', 'ala', 'volante', 'atacante'];
            const capitalizar = s => s.charAt(0).toUpperCase() + s.slice(1);

            let dadosAtuais = {{ confirmados: [], ausentes: [], semResposta: [], grupos: {{}} }};

            async function carregarStatus() {{
                try {{
                    const [resPresencas, resAtletas] = await Promise.all([
                        fetch(`${{baseUrl}}/peladas/${{peladaId}}/presencas-completo`),
                        fetch(`${{baseUrl}}/atletas`)
                    ]);

                    const presencas = await resPresencas.json();
                    const todosAtletas = await resAtletas.json();
                    const mensalistas = todosAtletas.filter(a => a.mensalista);

                    const confirmados = presencas.filter(p => p.confirmado);
                    const idsAusentes = presencas.filter(p => !p.confirmado).map(p => p.atleta_id);
                    const idsSemResposta = mensalistas
                        .filter(a => !presencas.find(p => p.atleta_id === a.id))
                        .map(a => a.id);

                    // contagem separada de goleiros
                    const confirmadosGoleiros = confirmados.filter(p => {{
                        const a = todosAtletas.find(x => x.id === p.atleta_id);
                        return a?.posicao === 'goleiro';
                    }});
                    const confirmadosJogadores = confirmados.length - confirmadosGoleiros.length;
                    const vagas = 30 - confirmadosJogadores;

                    document.getElementById('vagas').textContent =
                        `✅ ${{confirmadosJogadores}} jogadores + ${{confirmadosGoleiros.length}} goleiro(s) — ${{vagas}} vagas restantes`;

                    document.getElementById('titulo-confirmados').textContent =
                        `Confirmados (${{confirmados.length}})`;
                    document.getElementById('titulo-ausentes').textContent =
                        `Ausentes (${{idsAusentes.length}})`;
                    document.getElementById('titulo-sem-resposta').textContent =
                        `Sem resposta (${{idsSemResposta.length}})`;

                    // agrupa confirmados por posição
                    const grupos = {{}};
                    for (const p of confirmados) {{
                        const atleta = todosAtletas.find(a => a.id === p.atleta_id);
                        const posicao = atleta?.posicao || 'outro';
                        if (!grupos[posicao]) grupos[posicao] = [];
                        grupos[posicao].push(atleta?.nome ?? '?');
                    }}

                    dadosAtuais = {{
                        confirmados,
                        ausentes: idsAusentes.map(id => todosAtletas.find(a => a.id === id)?.nome ?? '?'),
                        semResposta: idsSemResposta.map(id => todosAtletas.find(a => a.id === id)?.nome ?? '?'),
                        grupos,
                        local: '{pelada.local}',
                        data: '{pelada.data}'
                    }};

                    // confirmados agrupados por posição
                    const listaConf = document.getElementById('lista-confirmados');
                    if (confirmados.length === 0) {{
                        listaConf.innerHTML = '<div class="vazio">Nenhum confirmado ainda.</div>';
                    }} else {{
                        const todasPosicoes = [...ordemPosicoes, ...Object.keys(grupos).filter(p => !ordemPosicoes.includes(p))];
                        listaConf.innerHTML = todasPosicoes
                            .filter(pos => grupos[pos] && grupos[pos].length > 0)
                            .map(pos => `
                                <div class="posicao-titulo">${{capitalizar(pos)}} (${{grupos[pos].length}})</div>
                                ${{grupos[pos].map(nome => `
                                    <div class="atleta-item confirmado-item">
                                        <span class="icone">✅</span>
                                        <span class="nome">${{nome}}</span>
                                    </div>
                                `).join('')}}
                            `).join('');
                    }}

                    // ausentes
                    document.getElementById('lista-ausentes').innerHTML =
                        idsAusentes.length === 0
                        ? '<div class="vazio">Nenhuma ausência confirmada.</div>'
                        : idsAusentes.map(id => {{
                            const a = todosAtletas.find(x => x.id === id);
                            return `<div class="atleta-item ausente-item">
                                <span class="icone">❌</span>
                                <span class="nome">${{a?.nome ?? '?'}}</span>
                            </div>`;
                        }}).join('');

                    // sem resposta
                    document.getElementById('lista-sem-resposta').innerHTML =
                        idsSemResposta.length === 0
                        ? '<div class="vazio">Todos responderam! 🎉</div>'
                        : idsSemResposta.map(id => {{
                            const a = todosAtletas.find(x => x.id === id);
                            return `<div class="atleta-item sem-resposta-item">
                                <span class="icone">⏳</span>
                                <span class="nome">${{a?.nome ?? '?'}}</span>
                            </div>`;
                        }}).join('');

                }} catch (e) {{
                    console.error('Erro ao carregar status:', e);
                }}
            }}

            function compartilhar() {{
                const d = dadosAtuais;
                let texto = `⚽ *PRESENÇAS — ${{d.local}}*\\n`;
                texto += `📅 ${{d.data}}\\n\\n`;

                texto += `✅ *Confirmados (${{d.confirmados.length}}):*\\n`;
                const todasPosicoes = [...ordemPosicoes, ...Object.keys(d.grupos).filter(p => !ordemPosicoes.includes(p))];
                for (const pos of todasPosicoes) {{
                    if (d.grupos[pos] && d.grupos[pos].length > 0) {{
                        texto += `\\n_${{capitalizar(pos)}}:_\\n`;
                        d.grupos[pos].forEach(nome => {{ texto += `• ${{nome}}\\n`; }});
                    }}
                }}

                if (d.ausentes.length > 0) {{
                    texto += `\\n❌ *Ausentes (${{d.ausentes.length}}):*\\n`;
                    d.ausentes.forEach(nome => {{ texto += `• ${{nome}}\\n`; }});
                }}

                if (d.semResposta.length > 0) {{
                    texto += `\\n⏳ *Sem resposta (${{d.semResposta.length}}):*\\n`;
                    d.semResposta.forEach(nome => {{ texto += `• ${{nome}}\\n`; }});
                }}

                const url = `https://wa.me/?text=${{encodeURIComponent(texto)}}`;
                window.open(url, '_blank');
            }}

            async function responder(confirmar) {{
                const atletaId = document.getElementById('atleta').value;
                if (!atletaId) {{
                    mostrarMensagem('Selecione seu nome!', false);
                    return;
                }}

                const url = confirmar
                    ? `${{baseUrl}}/peladas/${{peladaId}}/presenca-confirmar/${{atletaId}}`
                    : `${{baseUrl}}/peladas/${{peladaId}}/presenca-cancelar/${{atletaId}}`;

                try {{
                    const resp = await fetch(url, {{ method: 'POST' }});
                    mostrarMensagem(
                        confirmar ? '✅ Presença confirmada!' : '❌ Presença cancelada.',
                        resp.ok
                    );
                    await carregarStatus();
                }} catch (e) {{
                    mostrarMensagem('Erro de conexão. Tente novamente.', false);
                }}
            }}

            function mostrarMensagem(texto, sucesso) {{
                const el = document.getElementById('mensagem');
                el.textContent = texto;
                el.className = 'mensagem ' + (sucesso ? 'sucesso' : 'erro');
                el.style.display = 'block';
                setTimeout(() => {{ el.style.display = 'none'; }}, 3000);
            }}

            carregarStatus();
            setInterval(carregarStatus, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/peladas/{pelada_id}/presenca-confirmar/{atleta_id}")
def confirmar_presenca_link(
    pelada_id: int,
    atleta_id: int,
    session: Session = Depends(get_session)
):
    presenca = session.exec(
        select(Presenca).where(
            Presenca.pelada_id == pelada_id,
            Presenca.atleta_id == atleta_id
        )
    ).first()

    if presenca:
        presenca.confirmado = True  # ← atualiza mesmo se já existir
        session.add(presenca)
    else:
        session.add(Presenca(
            pelada_id=pelada_id,
            atleta_id=atleta_id,
            confirmado=True
        ))

    session.commit()
    return {"msg": "Presença confirmada!"}


@app.post("/peladas/{pelada_id}/presenca-cancelar/{atleta_id}")
def cancelar_presenca_link(
    pelada_id: int,
    atleta_id: int,
    session: Session = Depends(get_session)
):
    presenca = session.exec(
        select(Presenca).where(
            Presenca.pelada_id == pelada_id,
            Presenca.atleta_id == atleta_id
        )
    ).first()

    if presenca:
        presenca.confirmado = False
        session.add(presenca)
    else:
        session.add(Presenca(
            pelada_id=pelada_id,
            atleta_id=atleta_id,
            confirmado=False
        ))

    session.commit()
    return {"msg": "Presença cancelada"}

@app.get("/peladas/{pelada_id}/presencas-completo")
def listar_presencas_completo(pelada_id: int, session: Session = Depends(get_session)):
    presencas = session.exec(
        select(Presenca).where(Presenca.pelada_id == pelada_id)
    ).all()
    resultado = []
    for p in presencas:
        atleta = session.get(Atleta, p.atleta_id)
        if atleta:
            resultado.append({
                "atleta_id": p.atleta_id,
                "confirmado": p.confirmado,
                "posicao": atleta.posicao
            })
    return resultado

class ImportarStats(SQLModel):
    gols: int
    assistencias: int

@app.post("/atletas/{atleta_id}/importar-stats")
def importar_stats(
    atleta_id: int,
    dados: ImportarStats,
    session: Session = Depends(get_session)
):
    atleta = session.get(Atleta, atleta_id)
    if not atleta:
        raise HTTPException(404, "Atleta não encontrado")

    # apaga eventos históricos anteriores
    session.exec(
        delete(EventoPartida).where(
            EventoPartida.partida_id == 1,
            EventoPartida.atleta_gol_id == atleta_id
        )
    )
    session.exec(
        delete(EventoPartida).where(
            EventoPartida.partida_id == 1,
            EventoPartida.atleta_assistencia_id == atleta_id
        )
    )
    session.commit()

    # insere gols
    for _ in range(dados.gols):
        session.add(EventoPartida(
            partida_id=1,
            time_id=1,
            atleta_gol_id=atleta_id,
            atleta_assistencia_id=None,
            instante_segundos=0
        ))

    # insere assistências — usa atleta_gol_id=1 (Bruno) como neutro
    # e atleta_assistencia_id=atleta_id para registrar corretamente
    for _ in range(dados.assistencias):
        session.add(EventoPartida(
            partida_id=1,
            time_id=1,
            atleta_gol_id=None,  # ← sem autor de gol
            atleta_assistencia_id=atleta_id,
            instante_segundos=0
        ))

    session.commit()
    return {"msg": f"Stats importadas: {dados.gols} gols, {dados.assistencias} assistências"}


# ─────────────────────────────────────────
# Resenha gerada por IA
# ─────────────────────────────────────────

class ResenhaRequest(SQLModel):
    detalhes_extras: Optional[str] = None

@app.post("/peladas/{pelada_id}/resenha", response_class=PlainTextResponse)
def gerar_resenha(
    pelada_id: int,
    body: ResenhaRequest = ResenhaRequest(),
    session: Session = Depends(get_session)
):
    pelada = session.get(Pelada, pelada_id)
    if not pelada:
        raise HTTPException(404, "Pelada não encontrada")

    jogos = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    if not jogos:
        raise HTTPException(400, "Nenhum jogo encontrado para esta pelada")

    atletas_map = {a.id: a.nome for a in session.exec(select(Atleta)).all()}
    times_map = {t.id: t.nome for t in session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()}

    # Busca todas as partidas da pelada para ordenar jogos pela partida_id
    todas_partidas = session.exec(
        select(Partida).where(
            col(Partida.jogo_id).in_([j.id for j in jogos])
        )
    ).all()

    # Mapeia jogo_id → menor partida_id (ordem real de jogo)
    partida_min_por_jogo = {}
    for p in todas_partidas:
        atual = partida_min_por_jogo.get(p.jogo_id, float('inf'))
        partida_min_por_jogo[p.jogo_id] = min(atual, p.id)

    # Jogos sem partida ficam no final
    jogos_ordenados = sorted(jogos, key=lambda j: partida_min_por_jogo.get(j.id, float('inf')))

    jogos_desc = []
    for idx, jogo in enumerate(jogos_ordenados, start=1):
        nome_a = times_map.get(jogo.time_a_id, f"Time {jogo.time_a_id}")
        nome_b = times_map.get(jogo.time_b_id, f"Time {jogo.time_b_id}")

        partidas = [p for p in todas_partidas if p.jogo_id == jogo.id]

        eventos_jogo = []
        for partida in sorted(partidas, key=lambda p: p.id):
            eventos = session.exec(
                select(EventoPartida)
                .where(EventoPartida.partida_id == partida.id)
                .order_by(EventoPartida.instante_segundos)
            ).all()

            for ev in eventos:
                minuto = ev.instante_segundos // 60
                segundo = ev.instante_segundos % 60
                timestamp = f"{minuto}'{segundo:02d}\""
                goleador = atletas_map.get(ev.atleta_gol_id) if ev.atleta_gol_id else None
                assistente = atletas_map.get(ev.atleta_assistencia_id) if ev.atleta_assistencia_id else None
                time_nome = times_map.get(ev.time_id, "?")

                desc = f"  - {timestamp}: Gol de {goleador} ({time_nome})" if goleador else f"  - {timestamp}: Gol contra ({time_nome})"
                if assistente:
                    desc += f", assistência de {assistente}"
                eventos_jogo.append(desc)

        placar = f"{jogo.gols_time_a} x {jogo.gols_time_b}"
        if jogo.penaltis_a is not None and jogo.penaltis_b is not None:
            placar += f" (pênaltis: {jogo.penaltis_a} x {jogo.penaltis_b})"
        rotulo_fase = {"final": " — FINAL", "terceiro": " — Disputa de 3º lugar"}.get(jogo.fase, "")
        jogo_texto = (
            f"Jogo {idx}{rotulo_fase}: {nome_a} {placar} {nome_b} [status: {jogo.status}]\n"
            + ("\n".join(eventos_jogo) if eventos_jogo else "  (sem gols registrados — jogo terminou 0 x 0)")
        )
        jogos_desc.append(jogo_texto)

    jogos_str = "\n\n".join(jogos_desc)

    prompt = f"""Você é um narrador esportivo brasileiro bem humorado. Gere uma resenha completa da pelada abaixo em português.

Dados da pelada:
- Local: {pelada.local}
- Data: {pelada.data}
- Campeão: {pelada.campeao or 'não definido'}

Jogos (em ordem cronológica):
{jogos_str}
"""

    if body.detalhes_extras:
        prompt += f"\nDetalhes extras fornecidos pelos participantes:\n{body.detalhes_extras}\n"

    prompt += """
Instruções:
- Comece a resenha com a data da pelada em destaque (formato dia/mês/ano)
- Escreva em estilo esportivo, animado e bem humorado, como uma crônica de jornal esportivo
- Os jogos estão listados em ordem cronológica (do primeiro ao último). Respeite EXATAMENTE essa ordem ao narrar — o primeiro jogo listado foi o primeiro a acontecer, o último foi o final
- Ao referenciar jogos (ex: "segundo jogo", "última partida"), use sempre a posição correta na ordem cronológica fornecida
- Descreva cada jogo na sequência em que aconteceu, com gols e momentos marcantes
- Jogos sem gols (0 a 0) devem ser mencionados — narre-os com criatividade, destacando a disputa equilibrada ou a atuação dos goleiros
- Mencione goleadores e assistentes pelo nome de forma natural, incluindo o minuto e segundo exato de cada gol (ex: "aos 12'34\"")
- Ao final de cada jogo, destaque o placar
- Escreva um resumo geral no final com o campeão e os destaques
- Se houver detalhes extras, incorpore-os naturalmente no texto
- Use linguagem descontraída, como relato entre amigos
"""

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(500, "GROQ_API_KEY não configurada")

    client = Groq(api_key=groq_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=2048,
    )

    return response.choices[0].message.content