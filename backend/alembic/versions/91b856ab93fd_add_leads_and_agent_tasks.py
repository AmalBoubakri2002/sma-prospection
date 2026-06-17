"""add_leads_and_agent_tasks

Revision ID: 91b856ab93fd
Revises: b3d7f1a9c2e4
Create Date: 2026-06-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '91b856ab93fd'
down_revision: Union[str, None] = 'b3d7f1a9c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('siret', sa.String(length=14), nullable=False),
        sa.Column('secteur', sa.String(length=10), nullable=True),
        sa.Column('taille_entreprise', sa.String(length=10), nullable=True),
        sa.Column('adresse', sa.String(length=500), nullable=True),
        sa.Column('telephone', sa.String(length=20), nullable=True),
        sa.Column('site_web', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='COLLECTE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'siret', name='uq_leads_campaign_siret'),
    )
    op.create_index(op.f('ix_leads_campaign_id'), 'leads', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_leads_siret'), 'leads', ['siret'], unique=False)

    op.create_table(
        'agent_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_name', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_tasks_campaign_id'), 'agent_tasks', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_agent_tasks_agent_name'), 'agent_tasks', ['agent_name'], unique=False)
    op.create_index(op.f('ix_agent_tasks_status'), 'agent_tasks', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_tasks_status'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_agent_name'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_campaign_id'), table_name='agent_tasks')
    op.drop_table('agent_tasks')

    op.drop_index(op.f('ix_leads_siret'), table_name='leads')
    op.drop_index(op.f('ix_leads_campaign_id'), table_name='leads')
    op.drop_table('leads')
