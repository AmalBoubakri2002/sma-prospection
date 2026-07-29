"""add confidence_score to leads

Revision ID: d4f7a2c9b1e6
Revises: c8a1f4e2d7b9
Create Date: 2026-07-19

Ajoute confidence_score (Double, nullable) à la table leads.
Valeur calculée par l'Agent Scoring : part (0-100) des données financières
(ca/ca_n1/resultat_net) réellement disponibles plutôt qu'imputées, derrière
le score affiché (voir app/agents/scoring/decision.py::confidence_score).
"""

import sqlalchemy as sa

from alembic import op

revision = "d4f7a2c9b1e6"
down_revision = "c8a1f4e2d7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("confidence_score", sa.Double(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "confidence_score")
