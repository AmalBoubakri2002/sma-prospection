"""Backfill qualité données enrichissement existantes.

Corrections apportées :
  1. date_creation   — par SIRET, garde la date la plus ancienne (= fondation société)
                       et la propage à toutes les lignes de ce SIRET.
                       Les lignes avec une date plus récente avaient dateCreationEtablissement
                       (siège actuel) au lieu de dateCreationUniteLegale (fondation).
  2. email           — efface les emails de bureaux étrangers détectés (hello-spain@, london@…)
  3. score_intent    — recalcule depuis les champs présents pour les lignes où la valeur est NULL

Revision ID: c4e7b2a9d1f3
Revises: f1c9a3b8d2e6
Create Date: 2026-06-20
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e7b2a9d1f3"
down_revision: Union[str, None] = "f1c9a3b8d2e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Normaliser date_creation par SIRET ─────────────────────────────────
    # Pour chaque SIRET, la date la plus ancienne est la fondation de la société
    # (dateCreationUniteLegale). Les dates plus récentes correspondent à des
    # établissements (sièges successifs) et sont incorrectes pour l'ancienneté.
    op.execute("""
        UPDATE leads AS l
        SET date_creation = siret_min.min_date
        FROM (
            SELECT siret, MIN(date_creation) AS min_date
            FROM leads
            WHERE date_creation IS NOT NULL
            GROUP BY siret
        ) AS siret_min
        WHERE l.siret = siret_min.siret
          AND (l.date_creation IS NULL OR l.date_creation > siret_min.min_date)
    """)

    # ── 2. Effacer les emails de bureaux étrangers ────────────────────────────
    # Préfixes géographiques connus : hello-spain@, london@, uk@, berlin@, etc.
    # Pattern : toute partie du préfixe (split sur -_.) qui est un mot géo.
    op.execute(r"""
        UPDATE leads
        SET email = NULL
        WHERE email ~* '^[a-z0-9]*[-_.]?(spain|espagne|london|berlin|madrid|amsterdam|dubai|singapore|brussels|rome|milan|istanbul|stockholm|oslo|copenhagen|warsaw|vienna|zurich|prague|budapest|uk|us|usa|de|es|it|nl|pt|pl|se|no|dk|fi|be|at|ch|cz|hu)[a-z0-9]*@'
           OR email ~* '^(spain|espagne|london|berlin|madrid|amsterdam|dubai|singapore|brussels|rome|milan|istanbul|stockholm|oslo|copenhagen|warsaw|vienna|zurich|prague|budapest|uk|us|usa|de|es|it|nl|pt|pl|se|no|dk|fi|be|at|ch|cz|hu)@'
    """)

    # ── 3. Recalculer score_intent pour les lignes NULL ───────────────────────
    # Formule identique à _compute_score_intent() dans agent.py :
    # (email×2 + telephone + site_web + prenom_dirigeant + ca) / 6.0
    op.execute("""
        UPDATE leads
        SET score_intent = ROUND(
            (
                CASE WHEN email           IS NOT NULL THEN 2 ELSE 0 END +
                CASE WHEN telephone       IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN site_web        IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN prenom_dirigeant IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN ca              IS NOT NULL THEN 1 ELSE 0 END
            )::numeric / 6.0,
            4
        )
        WHERE score_intent IS NULL AND status = 'ENRICHI'
    """)


def downgrade() -> None:
    # Irréversible : on ne peut pas retrouver les valeurs effacées.
    # Le downgrade laisse les données en l'état.
    pass
