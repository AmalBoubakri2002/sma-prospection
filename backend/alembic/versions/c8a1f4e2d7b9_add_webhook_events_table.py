from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'c8a1f4e2d7b9'
down_revision: Union[str, None] = '111681951433'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("odoo_lead_id", sa.Integer(), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # SET NULL : le journal d'audit survit à la purge RGPD du lead
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_webhook_events_lead_id"), "webhook_events", ["lead_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_webhook_events_lead_id"), table_name="webhook_events")
    op.drop_table("webhook_events")
