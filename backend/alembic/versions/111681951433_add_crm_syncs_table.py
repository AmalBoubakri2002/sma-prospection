"""add crm_syncs table

Revision ID: 111681951433
Revises: a0f6fd9702e7
Create Date: 2026-07-09 13:04:48.132731

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '111681951433'
down_revision: Union[str, None] = 'a0f6fd9702e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("odoo_lead_id", sa.Integer(), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # unique=True suffit : Postgres crée automatiquement un index btree unique
    # pour supporter la contrainte, pas besoin d'un index séparé en plus.
    op.create_index(op.f("ix_crm_syncs_lead_id"), "crm_syncs", ["lead_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_crm_syncs_lead_id"), table_name="crm_syncs")
    op.drop_table("crm_syncs")
