import requests
import json

URL = "https://peladatop-app.onrender.com"

with open("atletas_backup.json", "r", encoding="utf-8") as f:
    atletas = json.load(f)

print(f"Importando {len(atletas)} atletas...")

for a in atletas:
    r = requests.post(f"{URL}/atletas", json={
        "nome": a["nome"],
        "nivel": a["nivel"],
        "posicao": a["posicao"],
        "mensalista": a["mensalista"],
        "titulos": a["titulos"]
    })
    status = "✓" if r.status_code == 200 else f"✗ erro {r.status_code}"
    print(f"{status} {a['nome']}")

print("Importação concluída!")