"""add taux_completude to leads

Revision ID: b5c3d1e8f2a4
Revises: a1b2c3d4e5f6
Create Date: 2026-06-30

Ajoute taux_completude (Float, nullable) à la table leads.
Valeur calculée par l'Agent Enrichissement : pourcentage de champs clés renseignés.
"""

import sqlalchemy as sa

from alembic import op

revision = "b5c3d1e8f2a4"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("taux_completude", sa.Double(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "taux_completude")
