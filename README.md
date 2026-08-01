# SMA Prospection — ProspectAI

> Plateforme de prospection B2B pilotée par des agents IA orchestrés avec LangGraph : de la détection d'entreprises cibles à la synchronisation CRM, avec validation humaine (HITL) avant l'envoi des emails.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

## Sommaire

- [Aperçu](#aperçu)
- [Stack technique](#stack-technique)
- [Architecture — Pipeline multi-agent](#architecture--pipeline-multi-agent)
  - [Boucle retour CRM](#boucle-retour-crm-webhooks-odoo--backend)
- [Fonctionnalités](#fonctionnalités)
- [Démarrage rapide](#démarrage-rapide)
- [Structure du projet](#structure-du-projet)
- [Auteure](#auteure)

## Aperçu

ProspectAI automatise le cycle de prospection B2B de bout en bout : détection d'entreprises cibles, enrichissement de leurs données, scoring de qualification, rédaction d'emails personnalisés et synchronisation avec le CRM. Chaque étape est prise en charge par un agent dédié, orchestré via un graphe LangGraph, avec un point de validation humaine avant tout envoi d'email.

## Stack technique

| Couche | Technologie |
|---|---|
| Frontend | React 18 + TypeScript + Ant Design + Vite |
| Backend | FastAPI + Python 3.11 + SQLAlchemy (async) |
| Base de données | PostgreSQL 16 |
| Agents IA | LangGraph + XGBoost (scoring) + API NVIDIA (rédaction) |
| CRM | Odoo 17 Community (Docker) |
| DevOps | Docker Compose |

## Architecture — Pipeline multi-agent

Le pipeline est orchestré par un graphe LangGraph ([`backend/app/workers/pipeline_graph.py`](backend/app/workers/pipeline_graph.py)), avec reprise automatique des tâches bloquées assurée par `orchestrateur.py` :

```
Veille → Enrichissement → Check quota → Scoring → Rédaction → [validation commerciale] → CRM
```

| Agent | Rôle |
|---|---|
| **Veille** | Identifie les entreprises cibles via l'API SIRENE, filtrées sur leur code NAF en vigueur |
| **Enrichissement** | Complète les données via BODACC, INPI, l'API Recherche d'entreprises, du scraping email/téléphone et de la géolocalisation |
| **Scoring** | Régression XGBoost attribuant à chaque lead un label (`HORS_CIBLE` / `FROID` / `TIEDE` / `CHAUD`) et un score de confiance (0-100) reflétant la part de données financières réelles — par opposition aux données imputées — utilisées dans le calcul |
| **Rédaction** | Génère des emails personnalisés via l'API NVIDIA et les place dans une file de validation humaine (HITL) avant envoi. Se déclenche automatiquement dès qu'un lead passe au statut `QUALIFIE`, y compris hors pipeline (requalification manuelle après baisse de seuil, override commercial) |
| **CRM** | Synchronise les leads validés vers Odoo (étape, vendeur assigné, historique dans le chatter), puis envoie l'email de prospection via le module mail d'Odoo (le lead passe alors à `CONTACTE`) |

En développement, les emails sont interceptés par **Mailpit** (`http://localhost:8025`) : aucun prospect réel n'est contacté. Ce comportement est désactivable via `ODOO_SEND_EMAILS=false`.

L'état du graphe est persisté dans PostgreSQL (`AsyncPostgresSaver`, tables `checkpoints*`) : la pause HITL survit aux redémarrages du worker, et la reprise repart exactement du nœud CRM. En l'absence de checkpoint suspendu (base purgée, campagne antérieure à la migration), la reprise bascule automatiquement sur une tâche CRM manuelle — les leads validés étant déjà présents en base à ce stade.

### Boucle retour CRM (webhooks Odoo → backend)

Le module Odoo `sma_pc_crm` renvoie les événements CRM vers le backend (`POST /api/v1/webhooks/odoo`), qui met à jour le statut du lead local et notifie le commercial :

| Événement Odoo | Déclencheur | Statut lead SMA-PC |
|---|---|---|
| `lead.won` | Opportunité passée dans une étape gagnée | `REPONDU` |
| `lead.lost` | Lead marqué perdu (archivé) | `SANS_REPONSE` |
| `message.received` | Réponse email du prospect (passerelle mail) | `REPONDU` |

Chaque événement reçu est journalisé dans la table `webhook_events` avec son résultat de traitement (audit). L'endpoint est authentifié par secret partagé :

1. Générer un secret : `openssl rand -hex 32`.
2. Le renseigner dans `backend/.env` → `ODOO_WEBHOOK_SECRET=...`.
3. Dans Odoo : *Paramètres > Technique > Paramètres système* → `sma_pc.webhook_secret` = la même valeur (l'URL `sma_pc.webhook_url` est préconfigurée pour le réseau Docker : `http://backend:8000/api/v1/webhooks/odoo`).
4. Mettre à jour le module : *Apps* → *SMA-PC ProspectAI — Intégration CRM* → *Upgrade*.

> Sans secret configuré côté backend, l'endpoint répond `503` (fermé par défaut).

## Fonctionnalités

**Authentification & rôles**
- Authentification JWT (login / token / profil)
- Gestion des rôles `admin` et `commercial`
- CRUD des commerciaux (admin)

**Tableaux de bord**
- Dashboard admin (statistiques d'équipe)
- Dashboard commercial (KPIs, campagnes)

**Campagnes & leads**
- Création et suivi de campagnes, avec estimation du vivier de prospects disponibles avant lancement (`GET /campaigns/estimate`)
- File de validation des leads et des emails générés

**Pipeline & CRM**
- Pipeline complet Veille → Enrichissement → Scoring → Rédaction → CRM (LangGraph)
- Intégration CRM Odoo 17 (étape, vendeur, historique)
- Boucle retour CRM : webhooks Odoo (gagné / perdu / réponse email) → statuts `REPONDU` / `SANS_REPONSE` + notification du commercial

**Fiabilité & temps réel**
- Notifications temps réel via bus PostgreSQL LISTEN/NOTIFY, poussées aux navigateurs par WebSocket (pas de Redis — même choix « PostgreSQL d'abord » que la file `agent_tasks`)
- Orchestrateur de reprise automatique des tâches en échec

**Observabilité**
- Scoring explicable : valeurs SHAP calculées par l'agent Scoring, affichées au commercial (fiche lead et file de validation)
- Endpoint `/metrics` et tableau de bord KPIs (funnel, temps de cycle par étape, fiabilité par agent, taux de synchro CRM)

## Démarrage rapide

### Prérequis

- Docker & Docker Compose
- Node.js 20+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

### 1. Configuration

```bash
cp .env.example .env                       # identifiants des conteneurs Postgres/Odoo
cp backend/.env.example backend/.env
# Renseigner les variables dans .env et backend/.env
```

### 2. Base de données & services

```bash
docker compose up -d
```

Démarre PostgreSQL (app), PostgreSQL + Odoo 17 (CRM), Mailpit (boîte email de démo), le worker pipeline et l'orchestrateur.

- Odoo : `http://localhost:8069`
- Mailpit : `http://localhost:8025`

### 3. Backend

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

- API : `http://localhost:8000`
- Swagger : `http://localhost:8000/docs`

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

- App : `http://localhost:5173`
- Compte admin par défaut : `admin@prospectai.fr` / `Admin1234!`

## Structure du projet

```
sma-prospection/
├── frontend/src/
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── admin/              # Dashboard, Commerciaux
│   │   └── commercial/         # Dashboard, NewCampaignPage, CampaignLeadsPage, ValidationQueuePage
│   ├── components/             # AdminLayout, CommercialLayout, ProtectedRoute
│   ├── stores/                 # authStore (Zustand + persist)
│   ├── utils/                  # api.ts (axios + intercepteurs JWT)
│   └── styles/                 # tokens.ts (design system)
├── backend/app/
│   ├── agents/
│   │   ├── veille/             # Recherche d'entreprises (SIRENE)
│   │   ├── enrichissement/     # BODACC, INPI, scraping email/téléphone, géocodage
│   │   ├── scoring/            # Régression XGBoost + feature builder
│   │   ├── redaction/          # Génération d'emails (API NVIDIA)
│   │   └── crm/                # Synchronisation Odoo (mapping, push, historique)
│   ├── workers/
│   │   ├── pipeline_graph.py   # Graphe LangGraph (veille→…→crm), pause HITL
│   │   ├── worker_pipeline.py  # Point d'entrée : poll + exécution des tâches agents
│   │   └── orchestrateur.py    # Reprise automatique des tâches/campagnes bloquées
│   ├── api/v1/                 # Routes auth, users, campaigns, leads, notifications, webhooks
│   ├── core/                   # Config, sécurité JWT
│   ├── db/                     # Session SQLAlchemy async
│   ├── models/                 # User, Campaign, Lead, AgentTask, CrmSync, Notification
│   ├── schemas/                # Pydantic
│   └── services/               # Logique métier (leads, campagnes, Odoo client…)
├── odoo/addons/                 # Module CRM Odoo custom (champs x_score_ia, x_label_ia, x_sma_pc_id…)
├── docker-compose.yml           # PostgreSQL, Odoo 17, worker pipeline, orchestrateur
└── .env.example
```

## Auteure

Amal Boubakri — Stage Ingénieur, École Centrale de Lyon (2026)
