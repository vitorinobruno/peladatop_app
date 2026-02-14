import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.title("📅 Pelada da Semana")

# =========================
# Peladas existentes
# =========================
st.subheader("Peladas existentes")

resp = requests.get(f"{API_URL}/peladas")
peladas = resp.json() if resp.status_code == 200 else []

def label_pelada(p):
    return f"{p['data']} - {p['local']}"

if peladas:
    pelada_escolhida = st.selectbox(
        "Selecione uma pelada",
        peladas,
        format_func=label_pelada
    )

    if st.button("Usar esta pelada"):
        st.session_state["pelada_ativa"] = pelada_escolhida
        st.success("Pelada selecionada!")
    
    st.warning("⚠️ A exclusão é permanente")

    if st.button("Excluir pelada"):
        r = requests.delete(f"{API_URL}/peladas/{pelada_escolhida['id']}")

        if r.status_code == 200:
            st.success("Pelada excluída com sucesso!")

            if "pelada_ativa" in st.session_state:
                del st.session_state["pelada_ativa"]

            st.rerun()
        else:
            st.error(r.text)
else:
    st.info("Nenhuma pelada cadastrada ainda.")

# =========================
# Criar pelada
# =========================
st.subheader("Criar pelada")
data = st.date_input("Data da pelada")
local = st.text_input("Local da pelada")

if st.button("Criar Pelada"):
    payload = {
        "data": str(data),
        "local": local
    }
    r = requests.post(f"{API_URL}/peladas", json=payload)

    if r.status_code == 200:
        pelada = r.json()
        st.session_state["pelada_ativa"] = pelada
        st.success("Pelada criada e selecionada!")
    else:
        st.error(f"Erro: {r.status_code} - {r.text}")

st.divider()
st.subheader("Confirmação de Presença")

if "pelada_ativa" not in st.session_state:
    st.info("Crie ou selecione uma pelada primeiro.")
    st.stop()

pelada = st.session_state["pelada_ativa"]
pelada_id = pelada["id"]

# =====================================
# Configuração de vagas
# =====================================
MAX_ATLETAS = pelada.get("max_atletas", 30)  # ajuste se quiser

# =====================================
# Buscar atletas e presenças atuais
# =====================================
resp = requests.get(f"{API_URL}/atletas")
atletas = resp.json()

resp = requests.get(f"{API_URL}/peladas/{pelada_id}/presencas")
presencas = resp.json() if resp.status_code == 200 else []

ids_confirmados = {p["id"] for p in presencas}
vagas_restantes = MAX_ATLETAS - len(ids_confirmados)

mensalistas = [a for a in atletas if a["mensalista"]]
nao_mensalistas = [a for a in atletas if not a["mensalista"]]

# =====================================
# ETAPA 1 — mensalistas
# =====================================
st.markdown("### 🧾 Mensalistas")

if "presenca_mensalistas" not in st.session_state:
    st.session_state.presenca_mensalistas = {}

for atleta in mensalistas:
    if atleta["id"] in ids_confirmados:
        st.checkbox(atleta["nome"], value=True, disabled=True)
        continue

    confirmado = st.checkbox(
        atleta["nome"],
        value=st.session_state.presenca_mensalistas.get(atleta["id"], False),
        key=f"mens_{atleta['id']}"
    )
    st.session_state.presenca_mensalistas[atleta["id"]] = confirmado

if st.button("Confirmar mensalistas"):
    selecionados = [
        aid for aid, ok in st.session_state.presenca_mensalistas.items() if ok
    ]

    if not selecionados:
        st.warning("Nenhum mensalista selecionado.")
    else:
        requests.post(
            f"{API_URL}/peladas/{pelada_id}/presencas",
            json={"atletas_ids": selecionados}
        )
        st.success(f"{len(selecionados)} mensalistas confirmados!")
        st.rerun()

# =====================================
# Atualiza vagas após mensalistas
# =====================================
resp = requests.get(f"{API_URL}/peladas/{pelada_id}/presencas")
presencas = resp.json() if resp.status_code == 200 else []
ids_confirmados = {p["id"] for p in presencas}
vagas_restantes = MAX_ATLETAS - len(ids_confirmados)

st.info(f"Vagas restantes: {vagas_restantes}")

# =====================================
# ETAPA 2 — não mensalistas
# =====================================
if vagas_restantes > 0:

    st.markdown("### 🎟️ Convidados (não mensalistas)")

    if "presenca_convidados" not in st.session_state:
        st.session_state.presenca_convidados = {}

    disponiveis = [
        a for a in nao_mensalistas if a["id"] not in ids_confirmados
    ]

    for atleta in disponiveis[:vagas_restantes]:

        confirmado = st.checkbox(
            atleta["nome"],
            value=st.session_state.presenca_convidados.get(atleta["id"], False),
            key=f"conv_{atleta['id']}"
        )
        st.session_state.presenca_convidados[atleta["id"]] = confirmado

    if st.button("Confirmar convidados"):
        selecionados = [
            aid for aid, ok in st.session_state.presenca_convidados.items() if ok
        ]

        if not selecionados:
            st.warning("Nenhum convidado selecionado.")
        else:
            requests.post(
                f"{API_URL}/peladas/{pelada_id}/presencas",
                json={"atletas_ids": selecionados}
            )
            st.success(f"{len(selecionados)} convidados confirmados!")
            st.rerun()

else:
    st.success("Pelada lotada. Não há vagas para convidados.")

