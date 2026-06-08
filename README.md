# SMA Prospection — Système Multi-Agent de Prospection Commerciale

Plateforme intelligente de prospection B2B intégrant une architecture multi-agent (LangGraph) avec un CRM Odoo 17.

## Stack

| Couche | Technologie |
|---|---|
| Frontend | React 18 + TypeScript + Ant Design + Vite |
| Backend | FastAPI + Python 3.11 + SQLAlchemy (async) |
| Orchestration | LangGraph + LangSmith |
| LLM | Mistral API / Ollama (local fallback) |
| Scoring ML | XGBoost 2.0 + SHAP + MLflow |
| Base de données | PostgreSQL 16 |
| CRM | Odoo 17 Community |
| DevOps | Docker Compose + GitHub Actions |

## Démarrage rapide

### Prérequis

- Docker & Docker Compose
- Node.js 20+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (gestionnaire de packages Python)

### 1. Cloner & configurer

```bash
git clone https://github.com/amalboubakri/sma-prospection.git
cd sma-prospection
cp .env.example .env
# Remplir les variables dans .env (Mistral API key, etc.)
```

### 2. Démarrer PostgreSQL

```bash
docker compose up -d
# Vérifie que postgres est healthy :
docker compose ps
```

### 3. Backend

```bash
cd backend
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
alembic upgrade head                   # Appliquer les migrations
uvicorn app.main:app --reload --port 8000
```

API disponible sur `http://localhost:8000`
Docs Swagger : `http://localhost:8000/docs`

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App disponible sur `http://localhost:5173`

## Structure du projet

```
sma-prospection/
├── frontend/               # React 18 + TS + Ant Design
│   └── src/
│       ├── pages/          # Dashboard, Campaigns, Leads, etc.
│       ├── components/     # Composants réutilisables
│       ├── hooks/          # Custom hooks
│       ├── store/          # État global (Zustand)
│       ├── types/          # Types TypeScript
│       └── utils/          # Helpers
├── backend/                # FastAPI + Python
│   └── app/
│       ├── api/v1/         # Routes API
│       ├── agents/         # Agents LangGraph (Veille, Scoring, Rédaction, CRM)
│       ├── models/         # Modèles SQLAlchemy
│       ├── schemas/        # Schemas Pydantic
│       ├── core/           # Config, sécurité JWT
│       ├── db/             # Session DB, base
│       └── services/       # Logique métier
├── docker-compose.yml      # PostgreSQL uniquement (dev)
├── .env.example
└── .github/workflows/ci.yml
```

## Branches

- `main` — production-ready
- `develop` — intégration
- `feat/<name>` — nouvelles fonctionnalités

## Auteure

Amal Boubakri — Stage Ingénieur, École Centrale de Lyon (2026)
