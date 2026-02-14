import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.title("👕 Times da Pelada")

# --------------------------------------------------
# Validação de contexto
# --------------------------------------------------
if "pelada_ativa" not in st.session_state:
    st.info("Selecione uma pelada primeiro.")
    st.stop()

pelada = st.session_state["pelada_ativa"]
pelada_id = pelada["id"]

st.caption(f"{pelada['data']} — {pelada['local']}")

# --------------------------------------------------
# Busca dados do backend
# --------------------------------------------------
resp_times = requests.get(f"{API_URL}/peladas/{pelada_id}/times")
times_backend = resp_times.json()
if not isinstance(times_backend, list):
    times_backend = []

resp = requests.get(f"{API_URL}/peladas/{pelada_id}/presencas")
atletas = resp.json()
qtd_times_backend = len(times_backend) if times_backend else 2
if "qtd_times" not in st.session_state:
    st.session_state.qtd_times = qtd_times_backend
# --------------------------------------------------
# Controle de troca de pelada
# --------------------------------------------------
if "pelada_times_loaded" not in st.session_state:
    st.session_state.pelada_times_loaded = None

if st.session_state.pelada_times_loaded != pelada_id:
    # limpa tudo relacionado a times
    for k in list(st.session_state.keys()):
        if k.startswith(("time_", "cor_", "nome_")):
            del st.session_state[k]

    # inicializa estado editável a partir do backend
    st.session_state.times_atletas = {}
    for i, t in enumerate(times_backend):
        st.session_state.times_atletas[i] = {a["id"] for a in t["atletas"]}
    st.session_state.qtd_times = qtd_times_backend
    st.session_state.pelada_times_loaded = pelada_id

# --------------------------------------------------
# Quantidade de times
# --------------------------------------------------
qtd_times = st.radio(
    "Quantidade de times",
    options=[2, 3],
    index=[2, 3].index(st.session_state.qtd_times),
    horizontal=True,
    key="radio_qtd_times"
)

st.session_state.qtd_times = qtd_times

# garante estrutura do estado
if "times_atletas" not in st.session_state:
    st.session_state.times_atletas = {}

for i in range(qtd_times):
    st.session_state.times_atletas.setdefault(i, set())

# --------------------------------------------------
# Montagem manual dos times
# --------------------------------------------------
MAPA_CORES = {
    "Branco": "#f5f5f5",
    "Azul": "#cce5ff",
    "Laranja": "#ffe5cc",
    "Verde": "#d4edda",
}
cores_disponiveis = ["Branco", "Azul", "Laranja", "Verde"]
times_payload = []

for i in range(qtd_times):
    st.subheader(f"Time {i+1}")

    time_backend = times_backend[i] if i < len(times_backend) else None

    #nome = st.text_input(
     #   "Nome do time",
      #  value=time_backend["nome"] if time_backend else f"Time {i+1}",
       # key=f"nome_{pelada_id}_{i}"
    #)

    cor = st.selectbox(
        "Cor",
        cores_disponiveis,
        index=cores_disponiveis.index(time_backend["cor"]) if time_backend else 0,
        key=f"cor_{pelada_id}_{i}"
    )
    nome = cor

    # atletas usados em outros times
    atletas_usados = set().union(
        *[
            ids for idx, ids in st.session_state.times_atletas.items()
            if idx != i
        ]
    )

    atletas_restantes = [
        a for a in atletas
        if a["id"] not in atletas_usados
    ]

    # todos os confirmados disponíveis (sem distinção)
    atletas_disponiveis = atletas_restantes

    mapa_atletas = {
        a["id"]: f'{a["nome"]} ({a["posicao"]})'
        for a in atletas_disponiveis
    }

    opcoes_ids = list(mapa_atletas.keys())

    selecionados = st.multiselect(
        "Atletas do time",
        options=opcoes_ids,
        default=list(st.session_state.times_atletas[i]),
        format_func=lambda x: mapa_atletas[x],
        key=f"time_{pelada_id}_{i}"
    )

    st.session_state.times_atletas[i] = set(selecionados)

    cor_fundo = MAPA_CORES.get(cor, "#f5f5f5")

    nomes_atletas = [
        mapa_atletas[a_id] for a_id in selecionados
    ]

    conteudo_atletas = (
        "<br>".join(f"• {n}" for n in nomes_atletas)
        if nomes_atletas
        else "<i>Nenhum atleta selecionado</i>"
    )

    st.markdown(
        f"""
        <div style="
            background-color: {cor_fundo};
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
        ">
            <div style="font-weight: 700; font-size: 1.2rem; margin-bottom: 6px;">
                👕 {nome}
            </div>
            <div style="font-size: 0.95rem;">
                {conteudo_atletas}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    times_payload.append({
        "nome": nome,
        "cor": cor,
        "atletas_ids": selecionados
    })

# --------------------------------------------------
# Salvar times
# --------------------------------------------------
if st.button("Salvar Times"):
    r = requests.post(
        f"{API_URL}/peladas/{pelada_id}/times",
        json=times_payload
    )

    if r.status_code == 200:
        st.success("Times salvos com sucesso!")
    else:
        st.error(r.text)
