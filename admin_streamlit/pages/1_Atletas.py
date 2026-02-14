import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.title("Atletas")

# ==========================
# Cadastro novo atleta
# ==========================
st.subheader("Cadastrar novo atleta")

nome = st.text_input("Nome")
nivel = st.slider("Nível", 1, 5)
posicao = st.selectbox("Posição", ["Goleiro", "Zagueiro", "Ala", "Volante", "Atacante"])
mensalista = st.checkbox("Mensalista")

if st.button("Cadastrar"):
    requests.post(f"{API_URL}/atletas", json={
        "nome": nome,
        "nivel": nivel,
        "posicao": posicao.lower(),
        "mensalista": mensalista
    })
    st.rerun()

st.divider()

# ==========================
# Edição de atletas
# ==========================
st.subheader("Editar atletas")

resp = requests.get(f"{API_URL}/atletas")
atletas = resp.json()

for a in atletas:
    with st.container(border=True):

        col1, col2, col3, col4, col5 = st.columns([2,1,1,1,1])

        with col1:
            novo_nome = st.text_input(
                "Nome",
                value=a["nome"],
                key=f"nome_{a['id']}"
            )

        with col2:
            novo_nivel = st.selectbox(
                "Nível",
                [1,2,3,4,5],
                index=a["nivel"]-1,
                key=f"nivel_{a['id']}"
            )

        with col3:
            nova_posicao = st.selectbox(
                "Posição",
                ["goleiro","zagueiro","ala","volante","atacante"],
                index=["goleiro","zagueiro","ala","volante","atacante"].index(a["posicao"]),
                key=f"pos_{a['id']}"
            )

        with col4:
            novo_mensalista = st.checkbox(
                "Mensalista",
                value=a["mensalista"],
                key=f"mens_{a['id']}"
            )

        with col5:
            if st.button("Salvar", key=f"salvar_{a['id']}"):
                requests.put(
                    f"{API_URL}/atletas/{a['id']}",
                    json={
                        "id": a["id"],
                        "nome": novo_nome,
                        "nivel": novo_nivel,
                        "posicao": nova_posicao,
                        "mensalista": novo_mensalista,
                        "titulos": a["titulos"]
                    }
                )
                st.rerun()
