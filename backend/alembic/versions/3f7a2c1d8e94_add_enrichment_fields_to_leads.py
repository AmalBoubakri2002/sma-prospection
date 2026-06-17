"""add enrichment fields to leads

Revision ID: 3f7a2c1d8e94
Revises: 91b856ab93fd
Create Date: 2026-06-17 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "3f7a2c1d8e94"
down_revision = "91b856ab93fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("leads", sa.Column("prenom_dirigeant", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("nom_dirigeant", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("titre_dirigeant", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("ca", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "ca")
    op.drop_column("leads", "titre_dirigeant")
    op.drop_column("leads", "nom_dirigeant")
    op.drop_column("leads", "prenom_dirigeant")
    op.drop_column("leads", "email")
