"""Renomme le label SHAP score_intent dans shap_explication.

Remplace "Signal comportemental" par "Score de complétude du profil"
dans le JSON stocké dans leads.shap_explication pour tous les leads
déjà scorés.

Revision ID: 22ae62759397
Revises: d2f8b4c1e9a7
Create Date: 2026-06-27
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "22ae62759397"
down_revision: Union[str, None] = "d2f8b4c1e9a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE leads
        SET shap_explication = REPLACE(
            shap_explication,
            'Signal comportemental',
            'Score de complétude du profil'
        )
        WHERE shap_explication LIKE '%Signal comportemental%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE leads
        SET shap_explication = REPLACE(
            shap_explication,
            'Score de complétude du profil',
            'Signal comportemental'
        )
        WHERE shap_explication LIKE '%Score de complétude du profil%'
        """
    )
