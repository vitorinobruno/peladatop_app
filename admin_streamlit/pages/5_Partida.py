import streamlit as st
import requests
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

API_URL = "http://127.0.0.1:8000"

st.title("⚽ Partida")

st_autorefresh(interval=1000, key="cronometro")

# --------------------------------------------------
# Validação de contexto
# --------------------------------------------------
jogo_id = st.session_state.get("jogo_id")
if not jogo_id:
    st.warning("Selecione um jogo primeiro.")
    st.stop()

jogo_id = st.session_state["jogo_id"]

# --------------------------------------------------
# Criar ou obter partida
# --------------------------------------------------
if "partida_id" not in st.session_state:
    resp = requests.post(
        f"{API_URL}/jogos/{jogo_id}/partida"
    )

    if resp.status_code != 200:
        st.error("Erro ao iniciar a partida.")
        st.stop()

    partida = resp.json()
    st.session_state.partida_id = partida["id"]

partida_id = st.session_state.partida_id

# --------------------------------------------------
# Buscar estado atual da partida (FONTE DA VERDADE)
# --------------------------------------------------
resp = requests.get(f"{API_URL}/partidas/{partida_id}")

if resp.status_code != 200:
    st.error("Erro ao carregar dados da partida.")
    st.stop()

partida = resp.json()

tempo_total_segundos = partida["tempo_minutos"] * 60

# --------------------------------------------------
# Times
# --------------------------------------------------
time_a = partida["time_a"]
time_b = partida["time_b"]

MAPA_CORES = {
    "Branco": "#f5f5f5",
    "Azul": "#cce5ff",
    "Laranja": "#ffe5cc",
    "Verde": "#d4edda",
}

# --------------------------------------------------
# Cronômetro
# --------------------------------------------------
inicio = datetime.fromisoformat(partida["iniciada_em"])

# Corrige: torna inicio UTC-aware
if inicio.tzinfo is None:
    inicio = inicio.replace(tzinfo=timezone.utc)

agora = datetime.now(timezone.utc)

decorrido = int((agora - inicio).total_seconds())

tempo_total_segundos = partida["tempo_minutos"] * 60
restante = max(0, tempo_total_segundos - decorrido)

minutos = restante // 60
segundos = restante % 60

st.metric("⏱️ Tempo", f"{minutos:02d}:{segundos:02d}")

# --------------------------------------------------
# Placar
# --------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        <div style="
            background:{MAPA_CORES.get(time_a['cor'], '#eee')};
            padding:1rem;
            border-radius:8px;
            text-align:center;
        ">
            <h3>{time_a['nome']}</h3>
            <h1>{partida['placar_a']}</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        f"""
        <div style="
            background:{MAPA_CORES.get(time_b['cor'], '#eee')};
            padding:1rem;
            border-radius:8px;
            text-align:center;
        ">
            <h3>{time_b['nome']}</h3>
            <h1>{partida['placar_b']}</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

# --------------------------------------------------
# Registro de gol
# --------------------------------------------------
st.subheader("⚽ Registrar Gol")

time_escolhido = st.radio(
    "Time",
    options=[time_a, time_b],
    format_func=lambda t: t["nome"],
    horizontal=True
)

atletas = time_escolhido["atletas"]

gol = st.selectbox(
    "Autor do gol",
    atletas,
    format_func=lambda a: a["nome"]
)

assistencia = st.selectbox(
    "Assistência (opcional)",
    [None] + atletas,
    format_func=lambda a: a["nome"] if a else "—"
)

if st.button("Registrar Gol", use_container_width=True):
    resp = requests.post(
        f"{API_URL}/partidas/{partida_id}/gol",
        params={
            "time_id": time_escolhido["id"],
            "atleta_gol_id": gol["id"],
            "atleta_assistencia_id": assistencia["id"] if assistencia else None,
            "instante_segundos": decorrido
        }
    )

    if resp.status_code == 200:
        st.rerun()
    else:
        st.error("Erro ao registrar gol.")

# --------------------------------------------------
# FINALIZAÇÃO AUTOMÁTICA
# --------------------------------------------------
if restante == 0 and partida["status"] != "finalizada":
    resp = requests.post(f"{API_URL}/partidas/{partida_id}/finalizar")

    if resp.status_code == 200:
        st.success("⏹️ Partida finalizada!")
        st.session_state.pop("partida_id", None)
        st.switch_page("pages/4_Jogos.py")
    else:
        st.error("Erro ao finalizar partida.")