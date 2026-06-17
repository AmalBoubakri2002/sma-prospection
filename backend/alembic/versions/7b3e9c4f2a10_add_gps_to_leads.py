"""add gps to leads

Revision ID: 7b3e9c4f2a10
Revises: 3f7a2c1d8e94
Create Date: 2026-06-17 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "7b3e9c4f2a10"
down_revision = "3f7a2c1d8e94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("resultat_net", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("latitude", sa.Double(), nullable=True))
    op.add_column("leads", sa.Column("longitude", sa.Double(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "longitude")
    op.drop_column("leads", "latitude")
    op.drop_column("leads", "resultat_net")
