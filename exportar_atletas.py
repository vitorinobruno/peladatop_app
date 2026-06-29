import requests
import json

URL = "https://peladatop-app.onrender.com"

atletas = requests.get(f"{URL}/atletas").json()
print(f"{len(atletas)} atletas encontrados")

with open("atletas_backup.json", "w", encoding="utf-8") as f:
    json.dump(atletas, f, ensure_ascii=False, indent=2)

print("Salvo em atletas_backup.json!")