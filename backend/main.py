from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel, Session, create_engine, select, delete
from models import Atleta, Pelada, PeladaCreate, Presenca, PresencaCreate, Time, TimeAtleta, TimeCreate, Jogo, Partida, EventoPartida
from datetime import date, datetime
from database import get_session, engine
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import col

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
    jogos_existentes = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    times_existentes = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    if jogos_existentes and times_existentes:
        # ── Atualiza times existentes preservando IDs ──
        for i, time_existente in enumerate(times_existentes):
            if i >= len(times):
                break
            t = times[i]
            time_existente.nome = t.nome
            time_existente.cor = t.cor
            session.add(time_existente)

            # atualiza atletas do time
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

    # ── Sem jogos: recria tudo normalmente ──
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
            .vagas {{ text-align: center; font-size: 14px; font-weight: 600; color: #1E88E5; margin-bottom: 24px; }}
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
            .secao-titulo {{
                font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px;
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
        </div>

        <script>
            const peladaId = {pelada_id};
            const baseUrl = window.location.origin;

            async function carregarStatus() {{
                try {{
                    const [resPresencas, resAtletas] = await Promise.all([
                        fetch(`${{baseUrl}}/peladas/${{peladaId}}/presencas-completo`),
                        fetch(`${{baseUrl}}/atletas`)
                    ]);

                    const presencas = await resPresencas.json();
                    const todosAtletas = await resAtletas.json();
                    const mensalistas = todosAtletas.filter(a => a.mensalista);

                    const idsConfirmados = presencas.filter(p => p.confirmado).map(p => p.atleta_id);
                    const idsAusentes = presencas.filter(p => !p.confirmado).map(p => p.atleta_id);
                    const idsSemResposta = mensalistas
                        .filter(a => !idsConfirmados.includes(a.id) && !idsAusentes.includes(a.id))
                        .map(a => a.id);

                    const vagas = 30 - idsConfirmados.length;
                    document.getElementById('vagas').textContent =
                        `✅ ${{idsConfirmados.length}} confirmados — ${{vagas}} vagas restantes`;

                    document.getElementById('titulo-confirmados').textContent =
                        `Confirmados (${{idsConfirmados.length}})`;
                    document.getElementById('titulo-ausentes').textContent =
                        `Ausentes (${{idsAusentes.length}})`;
                    document.getElementById('titulo-sem-resposta').textContent =
                        `Sem resposta (${{idsSemResposta.length}})`;

                    document.getElementById('lista-confirmados').innerHTML =
                        idsConfirmados.length === 0
                        ? '<div class="vazio">Nenhum confirmado ainda.</div>'
                        : idsConfirmados.map(id => {{
                            const a = todosAtletas.find(x => x.id === id);
                            return `<div class="atleta-item confirmado-item">
                                <span class="icone">✅</span>
                                <span class="nome">${{a?.nome ?? '?'}}</span>
                            </div>`;
                        }}).join('');

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
    return [{"atleta_id": p.atleta_id, "confirmado": p.confirmado} for p in presencas]

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