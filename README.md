# SMA Prospection — ProspectAI

Plateforme de prospection B2B avec orchestration multi-agent (LangGraph).

## Stack

| Couche | Technologie |
|---|---|
| Frontend | React 18 + TypeScript + Ant Design + Vite |
| Backend | FastAPI + Python 3.11 + SQLAlchemy (async) |
| Base de données | PostgreSQL 16 |
| Agents IA | LangGraph + Mistral API *(à venir)* |
| DevOps | Docker Compose |

## État du projet

### Implémenté
- Authentification JWT (login / token / profil)
- Gestion des rôles : `admin` et `commercial`
- CRUD commerciaux (admin)
- Dashboard admin (stats équipe)
- Dashboard commercial (KPIs, campagnes)
- Formulaire de création de campagne (UI)

### À venir
- Agent Veille (SIRENE + LinkedIn)
- Agent Scoring (XGBoost + SHAP)
- Agent Rédaction (Mistral)
- Intégration CRM Odoo 17

## Démarrage rapide

### Prérequis

- Docker & Docker Compose
- Node.js 20+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

### 1. Configuration

```bash
cp .env.example .env
# Remplir les variables dans .env
```

### 2. Base de données

```bash
docker compose up -d
```

### 3. Backend

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

API : `http://localhost:8000` · Swagger : `http://localhost:8000/docs`

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App : `http://localhost:5173`

Compte admin par défaut : `admin@prospectai.fr` / `Admin1234!`

## Structure

```
sma-prospection/
├── frontend/src/
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── admin/          # Dashboard, Commerciaux
│   │   └── commercial/     # Dashboard, NewCampaignPage
│   ├── components/         # AdminLayout, CommercialLayout, ProtectedRoute
│   ├── stores/             # authStore (Zustand + persist)
│   ├── utils/              # api.ts (axios + intercepteurs JWT)
│   └── styles/             # tokens.ts (design system)
├── backend/app/
│   ├── api/v1/             # Routes auth + users
│   ├── core/               # Config, sécurité JWT
│   ├── db/                 # Session SQLAlchemy async
│   ├── models/             # User
│   ├── schemas/            # Pydantic (UserCreate, UserResponse, Token…)
│   └── services/           # Logique métier utilisateurs
├── docker-compose.yml      # PostgreSQL 16
└── .env.example
```

## Auteure

Amal Boubakri — Stage Ingénieur, École Centrale de Lyon (2026)
