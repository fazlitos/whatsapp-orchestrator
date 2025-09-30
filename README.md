# WhatsApp Orchestrator (Render Starter)

Minimaler WhatsApp-Orchestrator (FastAPI) mit mehrsprachigen Prompts und Formular-Plugin-System.
Deploy via Render Blueprint (`render.yaml`).

## Ordner
- `app/main.py` → Webhook-Endpunkte (GET/POST), WhatsApp-Senden
- `app/orchestrator.py` → Zustandsmaschine, Mehrsprachigkeit, Formular-Plugins
- `app/validators.py` → Validierung/Normalisierung
- `app/forms/kindergeld.json` → Beispiel-Formular
- `app/locales/*.json` → Texte/Prompts (DE/EN/SQ)

## Start lokal (optional)
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 10000
```
Dann `GET /health` prüfen.
