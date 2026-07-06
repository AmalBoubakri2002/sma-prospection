"""add scoring fields to leads

Revision ID: e5f2a9b1c7d3
Revises: c4e7b2a9d1f3
Create Date: 2026-06-22

Ajoute les colonnes de l'Agent Scoring + deux champs de collecte manquants :
  - score            : probabilité XGBoost ∈ [0, 1]
  - label_scoring    : CHAUD / TIEDE / FROID / HORS_CIBLE
  - scored_at        : horodatage du scoring
  - score_intent     : signal comportemental 0-100 (Agent Veille/Enrichissement)
  - shap_explication : explication JSON des contributions SHAP

Utilise IF NOT EXISTS sur chaque colonne pour être idempotent :
la DB contenait déjà ces colonnes issues d'une session précédente.
"""

from typing import Union

from alembic import op

revision: str = "e5f2a9b1c7d3"
down_revision: Union[str, None] = "c4e7b2a9d1f3"
branch_labels = None
depends_on = None

_COLUMNS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS score            DOUBLE PRECISION",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS label_scoring    VARCHAR(10)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS scored_at        TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_intent     DOUBLE PRECISION",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS shap_explication TEXT",
]

_DROP_COLUMNS = [
    "ALTER TABLE leads DROP COLUMN IF EXISTS shap_explication",
    "ALTER TABLE leads DROP COLUMN IF EXISTS score_intent",
    "ALTER TABLE leads DROP COLUMN IF EXISTS scored_at",
    "ALTER TABLE leads DROP COLUMN IF EXISTS label_scoring",
    "ALTER TABLE leads DROP COLUMN IF EXISTS score",
]


def upgrade() -> None:
    for stmt in _COLUMNS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DROP_COLUMNS:
        op.execute(stmt)
