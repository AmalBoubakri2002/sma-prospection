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

- **Veille** — recherche d'entreprises cibles (API SIRENE), filtrées sur leur secteur NAF actuellement en vigueur
- **Enrichissement** — BODACC, INPI, recherche d'entreprises, scraping email/téléphone, géocodage
- **Scoring** — régression XGBoost sur les leads, label (`HORS_CIBLE`/`FROID`/`TIEDE`/`CHAUD`) et score de confiance (0-100) sur la part de données financières réelles vs imputées derrière le score
- **Rédaction** — génération d'emails personnalisés (API NVIDIA), avec file de validation humaine (HITL) avant envoi. Auto-déclenchée dès qu'un lead passe `QUALIFIE`, y compris hors pipeline (requalification manuelle après baisse de seuil, override commercial)
- **CRM** — synchronisation des leads validés vers Odoo (stage, vendeur assigné, historique email dans le chatter), puis **envoi effectif de l'email de prospection** via le module mail d'Odoo (lead → `CONTACTE`). En dev, les emails sont capturés par **Mailpit** (`http://localhost:8025`) — aucun prospect réel n'est contacté. Désactivable via `ODOO_SEND_EMAILS=false`.

L'état du graphe est persisté dans PostgreSQL (`AsyncPostgresSaver`, tables
`checkpoints*`) : la pause HITL survit aux redémarrages du worker et la reprise
repart exactement du nœud CRM. Si aucun checkpoint suspendu n'existe (base
purgée, campagne antérieure à la migration), la reprise bascule sur une tâche
CRM manuelle — les leads validés étant déjà en base à ce stade.

### Boucle retour CRM (webhooks Odoo → backend)

Le module Odoo `sma_pc_crm` renvoie les événements CRM vers le backend
(`POST /api/v1/webhooks/odoo`), qui met à jour le statut du lead local et
notifie le commercial :

| Événement Odoo | Déclencheur | Statut lead SMA-PC |
|---|---|---|
| `lead.won` | Opportunité passée dans une étape gagnée | `REPONDU` |
| `lead.lost` | Lead marqué perdu (archivé) | `SANS_REPONSE` |
| `message.received` | Réponse email du prospect (passerelle mail) | `REPONDU` |

Chaque événement reçu est journalisé dans la table `webhook_events` avec son
résultat de traitement (audit). L'endpoint est authentifié par secret partagé :

1. générer un secret : `openssl rand -hex 32` ;
2. le renseigner dans `backend/.env` → `ODOO_WEBHOOK_SECRET=...` ;
3. dans Odoo : *Paramètres > Technique > Paramètres système* →
   `sma_pc.webhook_secret` = la même valeur (l'URL `sma_pc.webhook_url` est
   préconfigurée pour le réseau Docker : `http://backend:8000/api/v1/webhooks/odoo`) ;
4. mettre à jour le module : Apps → *SMA-PC ProspectAI — Intégration CRM* → Upgrade.

Sans secret configuré côté backend, l'endpoint répond 503 (fermé par défaut).

## État du projet

### Implémenté
- Authentification JWT (login / token / profil)
- Gestion des rôles : `admin` et `commercial`
- CRUD commerciaux (admin)
- Dashboard admin (stats équipe)
- Dashboard commercial (KPIs, campagnes)
- Création et suivi de campagnes (UI + file de validation des leads/emails), avec estimation du vivier de prospects disponibles avant lancement (`GET /campaigns/estimate`)
- Pipeline complet Veille → Enrichissement → Scoring → Rédaction → CRM (LangGraph)
- Intégration CRM Odoo 17 (stage, vendeur, historique)
- Boucle retour CRM : webhooks Odoo (gagné / perdu / réponse email) → statuts `REPONDU` / `SANS_REPONSE` + notification du commercial
- Notifications temps réel : bus PostgreSQL LISTEN/NOTIFY entre les workers et l'API, poussé aux navigateurs par WebSocket (pas de Redis — même choix « PostgreSQL d'abord » que la file `agent_tasks`)
- Orchestrateur de reprise automatique des tâches en échec

### À venir
- Tableaux de bord d'analyse de campagne (SHAP / explicabilité du scoring)
- Endpoint `/metrics` (KPIs du rapport de performance)

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

Démarre PostgreSQL (app), PostgreSQL + Odoo 17 (CRM), Mailpit (boîte email de
démo), le worker pipeline et l'orchestrateur. Odoo : `http://localhost:8069` ·
Mailpit : `http://localhost:8025`.

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
