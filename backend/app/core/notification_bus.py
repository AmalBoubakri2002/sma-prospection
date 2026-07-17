"""Bus de notifications inter-processus via PostgreSQL LISTEN/NOTIFY.

Les notifications sont créées aussi bien par le processus API que par les
workers (pipeline, orchestrateur) — mais les connexions WebSocket ne vivent
que dans le processus API. Le NOTIFY est émis DANS la transaction courante :
PostgreSQL ne le délivre qu'au commit, jamais sur un rollback. Le processus
API écoute le canal (lifespan de main.py) et pousse chaque notification vers
les WebSockets de son destinataire.

Pas de Redis : PostgreSQL suffit largement à cette échelle, dans la continuité
du choix agent_tasks (file de tâches en base plutôt qu'un broker dédié).
"""

import asyncio
import json
import logging
import uuid

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.ws_manager import manager

logger = logging.getLogger("notification-bus")

CHANNEL = "sma_notifications"
_RECONNECT_DELAY_SECONDS = 5.0


async def publish(db: AsyncSession, recipient_id: uuid.UUID, payload: dict) -> None:
    """Émet un événement sur le canal, dans la transaction de `db` : délivré au
    commit uniquement — pas de faux push si la transaction échoue.

    Contrat du payload (relayé tel quel jusqu'au navigateur) :
      {"kind": "notification",    "data": NotificationResponse}   → cloche
      {"kind": "campaign_update", "data": {campaign_id, status}}  → pages"""
    envelope = json.dumps(
        {"recipient_id": str(recipient_id), "payload": payload},
        ensure_ascii=False,
    )
    await db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": envelope},
    )


async def _handle_payload(payload: str) -> None:
    """Route un événement reçu du canal vers les WebSockets du destinataire."""
    try:
        envelope = json.loads(payload)
        recipient_id = uuid.UUID(envelope["recipient_id"])
        message = envelope["payload"]
    except (ValueError, KeyError, TypeError):
        logger.warning("Payload NOTIFY invalide ignoré : %.200s", payload)
        return
    await manager.send_to_user(recipient_id, message)


def _on_notify(_conn, _pid, _channel, payload: str) -> None:
    """Callback synchrone d'asyncpg — planifie le traitement sur la boucle."""
    asyncio.get_running_loop().create_task(_handle_payload(payload))


async def listen_forever() -> None:
    """Boucle LISTEN du processus API — reconnexion automatique en cas de coupure.

    asyncpg attend un DSN "postgresql://", pas le dialecte SQLAlchemy+asyncpg."""
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(dsn)
            await conn.add_listener(CHANNEL, _on_notify)
            logger.info("Bus de notifications : LISTEN %s actif", CHANNEL)
            while not conn.is_closed():
                await asyncio.sleep(5)
            logger.warning("Bus de notifications : connexion PostgreSQL perdue")
        except asyncio.CancelledError:
            if conn is not None and not conn.is_closed():
                await conn.close()
            raise
        except Exception:
            logger.exception("Bus de notifications : erreur d'écoute")
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
