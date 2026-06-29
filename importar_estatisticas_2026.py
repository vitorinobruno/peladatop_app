import pandas as pd
import requests

# ─────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────
API_URL = "https://peladatop-app.onrender.com"
ARQUIVO_EXCEL = "Artilharia_Pelada_Top.xlsx"

# Mapeamento manual: nome na planilha → nome exato no app
# Ajuste conforme necessário antes de rodar
MAPA_NOMES = {
    "RICARDO":        "Ricardo",
    "BOMBA":          "Bomba",
    "DAVID W":        "David",
    "DIOGO AGUILAR":  "Diogo Aguilar",
    "EUGÊNIO":        "Eugênio",
    "NINHO":          "Ninho",
    "ALLYSON":        "Allyson",
    "ARTHUR":         "Arthur",
    "ANDERSON":       "Anderson",
    "RENAN":          "Renan",
    "NEGO BINHA":     "Nego Binha", #
    "BRUNO VITORINO": "Bruno Vitorino",
    "O BRUXO":        "Diogo Bruxo",
    "TIAGO PAULO":    "Tiago Paulo",
    "REINALDO":       "Reinaldo",
    "PEDRO FAGUNDES": "Pedro Fagundes",
    "DIOGO EUGÊNIO":  "Diogo Eugênio",
    "MARILSON":       "Marilson", #
    "MARQUINHOS":     "Marquinhos",
    "PAQUITO":        "Paquito",
    "WENDELL":        "Wendell",
    "CHARLES":        "Charles",
    "YURI":           "Yuri",
    "TAYRONNE":       "Tayronne",
    "AURIMAR":        "Aurimar", #
    "BERNARD":        "Bernard", 
    "CAMILO":         "Camilo", #
    "CARLOS":         "Carlos",
    "DOMINGOS":       "Domingos", #
    "ERMERSON":       "Ermerson",
    "HUDSON":         "Hudson",
    "KAUAN":          "Kauan",
    "LUIS GUSTAVO":   "Luis Gustavo", #
    "PEDRO PAULO":    "Pedro Paulo",
    "RALYSON":        "Ralyson Pifador",
    "RAUNY":          "Rauny", #
    "RYAN":           "Ryan", #
    "TÚLIO":          "Túlio",
}

# ─────────────────────────────────────────
# LÊ A PLANILHA
# ─────────────────────────────────────────
df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='2026', header=None)
dados = df.iloc[1:, 31:34].copy()
dados.columns = ['nome', 'gols', 'assistencias']
dados = dados.dropna(subset=['nome'])
dados['gols'] = dados['gols'].fillna(0).astype(int)
dados['assistencias'] = dados['assistencias'].fillna(0).astype(int)

print(f"✓ {len(dados)} atletas encontrados na planilha\n")

# ─────────────────────────────────────────
# BUSCA ATLETAS DO APP
# ─────────────────────────────────────────
resp = requests.get(f"{API_URL}/atletas")
atletas_app = resp.json()
mapa_app = {a['nome'].strip().lower(): a for a in atletas_app}

print(f"✓ {len(atletas_app)} atletas cadastrados no app\n")
print("─" * 50)

# ─────────────────────────────────────────
# PROCESSA CADA ATLETA
# ─────────────────────────────────────────
nao_encontrados = []
sem_stats = []
importados = []

for _, row in dados.iterrows():
    nome_planilha = str(row['nome']).strip()
    gols = int(row['gols'])
    assists = int(row['assistencias'])

    # pula atletas sem gols e sem assistências
    if gols == 0 and assists == 0:
        sem_stats.append(nome_planilha)
        continue

    # tenta encontrar no mapeamento
    nome_app = MAPA_NOMES.get(nome_planilha)
    if not nome_app:
        nao_encontrados.append(nome_planilha)
        continue

    # busca atleta no app
    atleta = mapa_app.get(nome_app.strip().lower())
    if not atleta:
        nao_encontrados.append(f"{nome_planilha} (mapeado como '{nome_app}' mas não encontrado no app)")
        continue

    # chama endpoint de importação histórica
    r = requests.post(f"{API_URL}/atletas/{atleta['id']}/importar-stats", json={
        "gols": gols,
        "assistencias": assists
    })

    if r.status_code == 200:
        print(f"✓ {nome_app}: {gols} gol(s), {assists} assistência(s)")
        importados.append(nome_app)
    else:
        print(f"✗ Erro em {nome_app}: {r.status_code} — {r.text}")

# ─────────────────────────────────────────
# RESUMO
# ─────────────────────────────────────────
print("\n" + "─" * 50)
print(f"✅ Importados com sucesso: {len(importados)}")

if sem_stats:
    print(f"\n⚪ Sem gols/assistências (ignorados): {len(sem_stats)}")
    for n in sem_stats:
        print(f"   • {n}")

if nao_encontrados:
    print(f"\n⚠️  Não encontrados/não mapeados: {len(nao_encontrados)}")
    for n in nao_encontrados:
        print(f"   • {n}")
    print("\nPara esses atletas, ajuste o MAPA_NOMES no script e rode novamente.")
