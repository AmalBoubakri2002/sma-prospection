"""Backfill ca_n1 pour les leads ENRICHI qui ont ca_n1 = NULL.

Stratégie :
  - Déduplique par SIREN (9 premiers chiffres du SIRET)
  - 1 appel INPI par SIREN unique → propage ca_n1 à toutes les lignes de ce SIREN
  - Respecte un délai entre chaque appel pour ne pas saturer l'API

Usage :
    cd backend
    uv run python backfill_ca_n1.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.agents.enrichissement.inpi import InpiError, get_finances_from_siren
from app.models.lead import Lead, LeadStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("backfill-ca-n1")

# ── Config ────────────────────────────────────────────────────────────────────
DELAY_BETWEEN_CALLS = 1.5   # secondes entre chaque appel INPI
BATCH_SIZE = 50             # leads récupérés par page


async def run(db_url: str, dry_run: bool = False) -> None:
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Trouver tous les SIREN uniques avec ca_n1 manquant
        stmt = (
            select(Lead.siret)
            .where(Lead.status == LeadStatus.ENRICHI, Lead.ca_n1.is_(None))
            .distinct()
        )
        result = await db.execute(stmt)
        sirets = [row[0] for row in result.all()]

    sirens_done: dict[str, int | None] = {}  # SIREN → ca_n1
    unique_sirens = list({s[:9] for s in sirets})

    log.info("%d SIRET(s) sans ca_n1 → %d SIREN(s) uniques à appeler",
             len(sirets), len(unique_sirens))

    if dry_run:
        log.info("[DRY-RUN] Aucune modification ne sera effectuée.")

    # ── Appel INPI par SIREN unique ───────────────────────────────────────────
    async with async_session() as db:
        for i, siren in enumerate(unique_sirens, 1):
            log.info("[%d/%d] SIREN %s …", i, len(unique_sirens), siren)
            try:
                data = await get_finances_from_siren(siren)
                ca_n1 = data.get("ca_n1")
                sirens_done[siren] = ca_n1
                log.info("  → ca_n1 = %s", ca_n1)
            except InpiError as exc:
                log.warning("  INPI erreur pour %s : %s", siren, exc)
                sirens_done[siren] = None

            if i < len(unique_sirens):
                await asyncio.sleep(DELAY_BETWEEN_CALLS)

        # ── Mise à jour en base ───────────────────────────────────────────────
        updated = 0
        for siren, ca_n1 in sirens_done.items():
            if ca_n1 is None:
                continue
            if dry_run:
                log.info("[DRY-RUN] UPDATE leads SET ca_n1=%d WHERE siret LIKE '%s%%' AND ca_n1 IS NULL",
                         ca_n1, siren)
                updated += 1
                continue

            stmt = (
                update(Lead)
                .where(
                    Lead.siret.like(f"{siren}%"),
                    Lead.ca_n1.is_(None),
                )
                .values(ca_n1=ca_n1)
            )
            result = await db.execute(stmt)
            updated += result.rowcount

        if not dry_run:
            await db.commit()

    log.info("Terminé — %d ligne(s) mise(s) à jour avec ca_n1.", updated)
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les requêtes sans les exécuter")
    args = parser.parse_args()

    # Importe la DATABASE_URL depuis la config de l'application
    try:
        from app.core.config import settings
        db_url = settings.DATABASE_URL
    except Exception:
        import os
        db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/sma_prospection")

    asyncio.run(run(db_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
