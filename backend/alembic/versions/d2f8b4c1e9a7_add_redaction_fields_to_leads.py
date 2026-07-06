from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "d2f8b4c1e9a7"
down_revision: Union[str, None] = "ea6d3e773d62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("objet_email", sa.String(500), nullable=True))
    op.add_column("leads", sa.Column("contenu_email", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("email_genere_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "email_genere_at")
    op.drop_column("leads", "contenu_email")
    op.drop_column("leads", "objet_email")
