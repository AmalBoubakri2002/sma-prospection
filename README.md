# SMA Prospection — ProspectAI

Plateforme de prospection B2B avec orchestration multi-agent (LangGraph) : de la
recherche d'entreprises à la synchronisation CRM, avec validation humaine (HITL)
avant l'envoi des emails.

## Stack

| Couche | Technologie |
|---|---|
| Frontend | React 18 + TypeScript + Ant Design + Vite |
| Backend | FastAPI + Python 3.11 + SQLAlchemy (async) |
| Base de données | PostgreSQL 16 |
| Agents IA | LangGraph + XGBoost (scoring) + API NVIDIA (rédaction) |
| CRM | Odoo 17 Community (Docker) |
| DevOps | Docker Compose |

## Pipeline multi-agent

Orchestré via un graphe LangGraph (`backend/app/workers/pipeline_graph.py`), avec
reprise automatique des tâches bloquées par `orchestrateur.py` :

```
Veille → Enrichissement → Check quota → Scoring → Rédaction → [validation commerciale] → CRM
```

- **Veille** — recherche d'entreprises cibles (API SIRENE)
- **Enrichissement** — BODACC, INPI, recherche d'entreprises, scraping email/téléphone, géocodage
- **Scoring** — régression XGBoost sur les leads, label (`HORS_CIBLE`/`FROID`/`TIEDE`/`CHAUD`)
- **Rédaction** — génération d'emails personnalisés (API NVIDIA), avec file de validation humaine (HITL) avant envoi
- **CRM** — synchronisation des leads validés vers Odoo (stage, vendeur assigné, historique email dans le chatter)

Si le worker redémarre pendant la pause HITL, la reprise bascule automatiquement
sur une tâche CRM manuelle plutôt que d'échouer, car les leads validés sont déjà
en base à ce stade.

## État du projet

### Implémenté
- Authentification JWT (login / token / profil)
- Gestion des rôles : `admin` et `commercial`
- CRUD commerciaux (admin)
- Dashboard admin (stats équipe)
- Dashboard commercial (KPIs, campagnes)
- Création et suivi de campagnes (UI + file de validation des leads/emails)
- Pipeline complet Veille → Enrichissement → Scoring → Rédaction → CRM (LangGraph)
- Intégration CRM Odoo 17 (stage, vendeur, historique)
- Orchestrateur de reprise automatique des tâches en échec

### À venir
- Notifications temps réel (au-delà du polling actuel)
- Tableaux de bord d'analyse de campagne (SHAP / explicabilité du scoring)

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

### 2. Base de données & services

```bash
docker compose up -d
```

Démarre PostgreSQL (app), PostgreSQL + Odoo 17 (CRM), le worker pipeline et
l'orchestrateur. Odoo : `http://localhost:8069`.

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
│   │   ├── admin/               # Dashboard, Commerciaux
│   │   └── commercial/          # Dashboard, NewCampaignPage, CampaignLeadsPage, ValidationQueuePage
│   ├── components/              # AdminLayout, CommercialLayout, ProtectedRoute
│   ├── stores/                  # authStore (Zustand + persist)
│   ├── utils/                   # api.ts (axios + intercepteurs JWT)
│   └── styles/                  # tokens.ts (design system)
├── backend/app/
│   ├── agents/
│   │   ├── veille/            # Recherche d'entreprises (SIRENE)
│   │   ├── enrichissement/    # BODACC, INPI, scraping email/téléphone, géocodage
│   │   ├── scoring/           # Régression XGBoost + feature builder
│   │   ├── redaction/         # Génération d'emails (API NVIDIA)
│   │   └── crm/               # Synchronisation Odoo (mapping, push, historique)
│   ├── workers/
│   │   ├── pipeline_graph.py  # Graphe LangGraph (veille→…→crm), pause HITL
│   │   ├── worker_pipeline.py # Point d'entrée : poll + exécute les tâches agents
│   │   └── orchestrateur.py   # Reprise automatique des tâches/campagnes bloquées
│   ├── api/v1/                # Routes auth, users, campaigns, leads, notifications, webhooks
│   ├── core/                  # Config, sécurité JWT
│   ├── db/                    # Session SQLAlchemy async
│   ├── models/                # User, Campaign, Lead, AgentTask, CrmSync, Notification
│   ├── schemas/                # Pydantic
│   └── services/              # Logique métier (leads, campagnes, Odoo client…)
├── odoo/addons/                # Module CRM Odoo custom (champs x_score_ia, x_label_ia, x_sma_pc_id…)
├── docker-compose.yml          # PostgreSQL, Odoo 17, worker pipeline, orchestrateur
└── .env.example
```

## Auteure

Amal Boubakri — Stage Ingénieur, École Centrale de Lyon (2026)
