import requests

URL = "https://peladatop-app.onrender.com"

ids = [32, 33]

for atleta_id in ids:
    # busca atleta atual
    a = requests.get(f"{URL}/atletas").json()
    atleta = next((x for x in a if x["id"] == atleta_id), None)
    
    if not atleta:
        print(f"✗ Atleta {atleta_id} não encontrado")
        continue

    # atualiza com titulos = 0
    r = requests.put(f"{URL}/atletas/{atleta_id}", json={
        "id": atleta["id"],
        "nome": atleta["nome"],
        "nivel": atleta["nivel"],
        "posicao": atleta["posicao"],
        "mensalista": atleta["mensalista"],
        "titulos": 0
    })
    
    status = "✓" if r.status_code == 200 else f"✗ erro {r.status_code}"
    print(f"{status} {atleta['nome']} — títulos zerados")