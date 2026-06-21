"""add enrichissement quality fields

Revision ID: f1c9a3b8d2e6
Revises: a1f4d8b2c3e5
Create Date: 2026-06-20 00:00:00.000000

Ajoute les champs nécessaires au scoring enrichi :
  - date_creation  : date de création de l'établissement (SIRENE)
  - ca_n1          : CA année N-1 (INPI, pour calcul evolution_ca)
  - score_intent   : proxy de joignabilité calculé par l'Agent Enrichissement [0-1]
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1c9a3b8d2e6"
down_revision: Union[str, None] = "9103b0fc0774"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("date_creation", sa.Date(), nullable=True))
    op.add_column("leads", sa.Column("ca_n1", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("score_intent", sa.Double(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "score_intent")
    op.drop_column("leads", "ca_n1")
    op.drop_column("leads", "date_creation")
