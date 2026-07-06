"""add name to campaigns

Revision ID: a1b2c3d4e5f6
Revises: 22ae62759397
Create Date: 2026-06-29

Ajoute le champ name (optionnel) à la table campaigns.
Les campagnes existantes auront name = NULL.
"""

from typing import Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "22ae62759397"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS name VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE campaigns DROP COLUMN IF EXISTS name"
    )
