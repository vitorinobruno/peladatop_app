import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.title("📊 Estatísticas Gerais")

# ============================
# Ranking de gols
# ============================
st.header("🥅 Ranking de Gols")

resp = requests.get(f"{API_URL}/estatisticas/gols")

if resp.status_code == 200:
    dados = resp.json()
    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum gol registrado ainda.")
else:
    st.error("Erro ao carregar ranking de gols")

st.divider()

# ============================
# Assistências
# ============================
st.header("🎯 Ranking de Assistências")

resp = requests.get(f"{API_URL}/estatisticas/assistencias")

if resp.status_code == 200:
    dados = resp.json()
    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhuma assistência registrada.")
else:
    st.error("Erro ao carregar assistências")

st.divider()

# ============================
# Títulos
# ============================
st.header("🏆 Títulos por Atleta")

resp = requests.get(f"{API_URL}/estatisticas/titulos")

if resp.status_code == 200:
    dados = resp.json()
    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum título ainda.")
else:
    st.error("Erro ao carregar títulos")

st.divider()

# ============================
# Pontos no ano
# ============================
st.header("📅 Pontos ao longo do ano")

resp = requests.get(f"{API_URL}/estatisticas/pontos-ano")

if resp.status_code == 200:
    dados = resp.json()
    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhuma pelada finalizada.")
else:
    st.error("Erro ao carregar pontuação anual")
