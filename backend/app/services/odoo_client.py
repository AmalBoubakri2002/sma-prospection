"""Client JSON-RPC 2.0 pour Odoo 17 — authentification + execute_kw générique.

Utilisé par l'Agent CRM pour créer/mettre à jour des crm.lead et interroger
Odoo. Un seul endpoint /jsonrpc, deux services Odoo : common (authenticate)
et object (execute_kw) — pattern stateless documenté par l'API externe
Odoo (pas de cookie de session, uid+password repassés à chaque appel).
Référence : https://www.odoo.com/documentation/17.0/developer/reference/external_api.html
"""

import asyncio
import itertools

import httpx

from app.core.config import settings

_JSONRPC_PATH = "/jsonrpc"
_id_counter = itertools.count(1)


class OdooError(Exception):
    """Erreur retournée par Odoo dans le champ 'error' de la réponse JSON-RPC."""


class OdooAuthError(OdooError):
    """Authentification échouée (identifiants invalides ou absents) — pas la peine de retenter."""


# Le uid Odoo ne change pas tant que le mot de passe ne change pas (pas de TTL,
# contrairement à un token) : on le met en cache pour éviter un appel
# authenticate() avant chaque execute_kw. _login_lock évite des logins
# concurrents si plusieurs leads sont synchronisés en parallèle.
_cached_uid: int | None = None
_login_lock = asyncio.Lock()


async def _call(client: httpx.AsyncClient, service: str, method: str, args: list) -> object:
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": next(_id_counter),
    }
    response = await client.post(f"{settings.ODOO_URL}{_JSONRPC_PATH}", json=payload, timeout=15.0)
    if response.status_code != 200:
        raise OdooError(f"Odoo ({response.status_code}) : {response.text[:300]}")

    body = response.json()
    error = body.get("error")
    if error:
        message = error.get("data", {}).get("message") or error.get("message") or str(error)
        raise OdooError(f"Odoo JSON-RPC : {message}")

    return body.get("result")


async def authenticate(client: httpx.AsyncClient) -> int:
    """Authentifie (ODOO_DB/ODOO_USERNAME/ODOO_PASSWORD) et retourne le uid Odoo (mis en cache)."""
    global _cached_uid

    async with _login_lock:
        if _cached_uid is not None:
            return _cached_uid

        if not settings.ODOO_USERNAME or not settings.ODOO_PASSWORD:
            raise OdooAuthError(
                "ODOO_USERNAME / ODOO_PASSWORD non configurés dans backend/.env"
            )

        uid = await _call(
            client,
            "common",
            "authenticate",
            [settings.ODOO_DB, settings.ODOO_USERNAME, settings.ODOO_PASSWORD, {}],
        )
        if not uid:
            raise OdooAuthError(
                f"Authentification Odoo échouée pour {settings.ODOO_USERNAME!r} "
                f"sur la base {settings.ODOO_DB!r}"
            )

        _cached_uid = uid
        return uid


async def execute_kw(model: str, method: str, args: list, kwargs: dict | None = None) -> object:
    """Appelle model.method(*args, **kwargs) côté Odoo (service object.execute_kw)."""
    async with httpx.AsyncClient() as client:
        uid = await authenticate(client)
        return await _call(
            client,
            "object",
            "execute_kw",
            [settings.ODOO_DB, uid, settings.ODOO_PASSWORD, model, method, args, kwargs or {}],
        )
