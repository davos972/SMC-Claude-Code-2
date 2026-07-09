"""GoldFlow SMC — envoi de notifications push vers les téléphones (Firebase FCM).

Mode dégradé explicite : si FIREBASE_SERVICE_ACCOUNT n'est pas configuré,
le push est simplement désactivé (log au premier envoi) — les notifications
in-app continuent de fonctionner normalement.

Config (variable d'environnement) :
    FIREBASE_SERVICE_ACCOUNT : contenu JSON complet de la clé privée du compte
    de service Firebase (Paramètres du projet → Comptes de service → Générer
    une nouvelle clé privée). C'est un SECRET — jamais dans Git, uniquement
    dans backend/.env en local et dans Environment sur Render.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("goldflow.push")

_creds = None            # google.oauth2.service_account.Credentials (lazy)
_project_id: str = ""
_disabled_logged = False

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _load_credentials():
    """Charge (une fois) la clé de service depuis l'env. None si non configurée."""
    global _creds, _project_id, _disabled_logged
    if _creds is not None:
        return _creds
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not raw:
        if not _disabled_logged:
            logger.info("Push désactivé : FIREBASE_SERVICE_ACCOUNT non configuré.")
            _disabled_logged = True
        return None
    try:
        from google.oauth2 import service_account
        info = json.loads(raw)
        _project_id = info.get("project_id", "")
        _creds = service_account.Credentials.from_service_account_info(
            info, scopes=[FCM_SCOPE]
        )
        logger.info("Push FCM configuré (projet %s).", _project_id)
        return _creds
    except Exception:
        logger.exception("FIREBASE_SERVICE_ACCOUNT invalide — push désactivé.")
        return None


def is_configured() -> bool:
    return _load_credentials() is not None


def _get_access_token_sync() -> Optional[str]:
    """Jeton OAuth2 pour l'API FCM (rafraîchi si expiré). Appel bloquant."""
    creds = _load_credentials()
    if creds is None:
        return None
    from google.auth.transport.requests import Request
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


async def send_to_all(title: str, body: str, category: str = "goldflow") -> None:
    """Envoie une notification push à tous les téléphones enregistrés.

    Ne lève jamais : le push est un canal « au mieux », il ne doit jamais
    casser la création de la notification in-app ni la boucle de trading.
    """
    try:
        if not is_configured():
            return
        import store  # import local : store importe push, éviter le cycle
        tokens: List[Dict[str, Any]] = await store.list_push_devices()
        if not tokens:
            return
        access_token = await asyncio.to_thread(_get_access_token_sync)
        if not access_token:
            return
        url = f"https://fcm.googleapis.com/v1/projects/{_project_id}/messages:send"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            for dev in tokens:
                token = dev.get("token", "")
                if not token:
                    continue
                message = {
                    "message": {
                        "token": token,
                        "notification": {"title": title, "body": body},
                        "android": {
                            "priority": "HIGH",
                            "notification": {
                                "channel_id": "goldflow",
                                "tag": category,
                            },
                        },
                    }
                }
                try:
                    r = await client.post(url, json=message, headers=headers)
                    if r.status_code == 404 or (
                        r.status_code == 400 and "UNREGISTERED" in r.text
                    ):
                        # Téléphone désinstallé / jeton expiré → on l'oublie
                        await store.remove_push_device(token)
                        logger.info("Jeton push expiré supprimé (%s…).", token[:12])
                    elif r.status_code >= 300:
                        logger.warning("Échec push FCM %s : %s", r.status_code, r.text[:200])
                except Exception:
                    logger.exception("Erreur d'envoi push (jeton %s…)", token[:12])
    except Exception:
        logger.exception("send_to_all a échoué (ignoré)")
