import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.title("⚽ Jogos do dia")

pelada = st.session_state.get("pelada_ativa")

if not pelada:
    st.warning("Selecione uma pelada válida.")
    st.stop()

pelada_id = pelada["id"]

# Buscar times da pelada
resp = requests.get(f"{API_URL}/peladas/{pelada_id}/times")

if resp.status_code != 200:
    st.error("Erro ao carregar times da pelada.")
    st.stop()

times = resp.json()

if not times:
    st.warning("Pelada sem times cadastrados.")
    st.stop()

if not pelada_id or not times:
    st.warning("Selecione uma pelada válida.")
    st.stop()

qtd_times = len(times)

# ----------------------------
# Configuração de tempo
# ----------------------------
tempo_jogo = st.number_input(
    "Tempo de cada partida (minutos)",
    min_value=5,
    max_value=30,
    value=10,
    step=5
)

# ----------------------------
# Criar jogos (idempotente)
# ----------------------------
if st.button("Gerar jogos do dia"):
    requests.post(
        f"{API_URL}/peladas/{pelada_id}/jogos",
        params={"tempo_minutos": tempo_jogo}
    )
    st.success("Jogos prontos!")

st.divider()

# ----------------------------
# Listar jogos
# ----------------------------
resp = requests.get(f"{API_URL}/peladas/{pelada_id}/jogos")
jogos = resp.json() if resp.status_code == 200 else []

if not jogos:
    st.info("Nenhum jogo gerado ainda.")
    st.stop()

# Mapa rápido de times
mapa_times = {t["id"]: t for t in times}

# ----------------------------
# Cards de jogos
# ----------------------------
for jogo in jogos:
    time_a = mapa_times[jogo["time_a_id"]]
    time_b = mapa_times[jogo["time_b_id"]]

    with st.container(border=True):
        st.markdown(
            f"### {time_a['nome']} × {time_b['nome']}"
        )

        st.markdown(
            f"**Placar:** {jogo['gols_time_a']} × {jogo['gols_time_b']}"
        )

        st.caption(f"⏱️ {jogo['tempo_minutos']} min")

        if jogo["status"] == "nao_iniciado":
            if st.button("▶ Iniciar partida", key=f"iniciar_{jogo['id']}"):
                st.session_state["jogo_id"] = jogo["id"]
                # LIMPEZA OBRIGATÓRIA
                st.session_state.pop("partida_id", None)
                st.switch_page("pages/5_Partida.py")

        elif jogo["status"] == "em_andamento":
            if st.button("🔄 Abrir partida", key=f"abrir_{jogo['id']}"):
                st.session_state["jogo_id"] = jogo["id"]
                # LIMPEZA OBRIGATÓRIA
                st.session_state.pop("partida_id", None)
                st.switch_page("pages/5_Partida.py")

        else:
            st.success("Partida finalizada")
