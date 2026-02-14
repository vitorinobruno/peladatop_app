import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.title("🏆 Resultados da Pelada")

pelada = st.session_state.get("pelada_ativa")

if not pelada:
    st.warning("Selecione uma pelada.")
    st.stop()

pelada_id = pelada["id"]

# -----------------------------------
# PLACARES DOS JOGOS
# -----------------------------------
st.header("⚽ Placares finais")

resp = requests.get(f"{API_URL}/peladas/{pelada_id}/jogos")
jogos = resp.json()

if not jogos:
    st.info("Nenhum jogo encontrado")
else:
    for j in jogos:
        if j["status"] != "finalizado":
            continue

        st.write(
            f"{j['nome_time_a']} {j['gols_time_a']} x "
            f"{j['gols_time_b']} {j['nome_time_b']} | "
            f"Jogo {j['id']}"
        )

# -----------------------------------
# TABELA DE CLASSIFICAÇÃO
# -----------------------------------
st.header("📊 Classificação")

resp = requests.get(f"{API_URL}/peladas/{pelada_id}/classificacao")

if resp.status_code != 200:
    st.error("Erro ao carregar classificação")
    st.stop()

tabela = resp.json()

if not tabela:
    st.info("Sem classificação ainda")
    st.stop()

campeao = tabela[0]

dados = []
for i, t in enumerate(tabela, start=1):
    dados.append({
        "Pos": i,
        "Time": t["nome"],
        "Pts": t["pontos"],
        "V": t["vitorias"],
        "E": t["empates"],
        "D": t["derrotas"],
        "GP": t["gols_pro"],
        "GC": t["gols_contra"],
        "SG": t["gols_pro"] - t["gols_contra"]
    })

st.dataframe(dados, use_container_width=True)

st.success(f"🏆 Líder atual: {campeao['nome']}")

st.divider()

# -----------------------------------
# FINALIZAR PELADA
# -----------------------------------
if st.button("🏁 Finalizar Pelada", use_container_width=True):
    resp = requests.post(f"{API_URL}/peladas/{pelada_id}/finalizar")

    if resp.status_code == 200:
        resultado = resp.json()
        st.success(f"Campeão: {resultado['campeao']}")
    else:
        st.error("Erro ao finalizar pelada")
    
