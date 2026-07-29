"""add_user_status_and_notifications

Revision ID: b3d7f1a9c2e4
Revises: e84e2168d181
Create Date: 2026-06-16 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b3d7f1a9c2e4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE')
    )
    op.execute("UPDATE users SET status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'REJECTED' END")
    op.drop_column('users', 'is_active')

    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('related_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['related_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_notifications_recipient_id'), 'notifications', ['recipient_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_notifications_recipient_id'), table_name='notifications')
    op.drop_table('notifications')

    op.add_column(
        'users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.execute("UPDATE users SET is_active = (status = 'ACTIVE')")
    op.drop_column('users', 'status')
