"""Gardien de vivacité — quand a-t-il le droit de relancer la boucle ?

🚨 CE QUE CES TESTS PROTÈGENT (diagnostic du 2026-09-11, voir DECISIONS.md).

Le gardien surveillait UN seul pouls, mis à jour uniquement après une lecture MetaApi
RÉUSSIE. Conséquence : dès que le broker avait un hoquet de 5 minutes, le gardien
déclarait « boucle figée » une boucle parfaitement vivante — qui était en fait en pleine
reconnexion — la tuait, elle repartait de zéro, et se faisait retuer 5 min plus tard.
132 relances au compteur, dont 12 h d'affilée le 2026-07-12.

La règle désormais figée par ces tests : **on ne relance QUE si la BOUCLE est morte.**
Une panne du broker alerte, elle ne relance rien.

Ni serveur, ni MongoDB, ni MetaApi : tout est simulé.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_loop  # noqa: E402

NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def bancd(monkeypatch):
    """Neutralise tout ce qui sort du processus, et enregistre ce qui a été tenté."""
    trace = {"relances": 0, "notifs": []}

    monkeypatch.setattr(bot_loop.store, "get_bot_state",
                        _async(lambda: {"running": True, "day_start_equity": 50000.0}))
    monkeypatch.setattr(bot_loop, "start", lambda **k: trace.__setitem__("relances", trace["relances"] + 1))
    monkeypatch.setattr(bot_loop.metaapi_client, "force_reconnect", _async(lambda: None))
    monkeypatch.setattr(bot_loop.metaapi_client, "is_connecting", lambda: False)

    async def fake_notify(ntype, category, title, message):
        trace["notifs"].append(category)
    monkeypatch.setattr(bot_loop, "_notify", fake_notify)

    # Aucune tâche de boucle en vol : le gardien n'a rien à annuler.
    monkeypatch.setattr(bot_loop, "_bot_task", None)
    # Anti-spam remis à zéro pour que chaque test parte propre.
    monkeypatch.setattr(bot_loop, "_last_watchdog_notify", None)
    monkeypatch.setattr(bot_loop, "_last_metaapi_notify", None)
    return trace


def _async(fn):
    async def wrapper(*a, **k):
        return fn(*a, **k)
    return wrapper


def _pouls(monkeypatch, loop_age_s, metaapi_age_s):
    """Positionne les deux pouls par leur ÂGE en secondes."""
    monkeypatch.setattr(bot_loop, "_last_loop_beat", NOW - timedelta(seconds=loop_age_s))
    monkeypatch.setattr(bot_loop, "_last_metaapi_ok", NOW - timedelta(seconds=metaapi_age_s))


def _check():
    return asyncio.run(bot_loop._watchdog_check_once(NOW))


# ─────────────────────────── le cas qui a tout causé ───────────────────────────

def test_metaapi_muet_mais_boucle_vivante_NE_RELANCE_PAS(monkeypatch, bancd):
    """LE test. Broker muet depuis 20 min, boucle qui tourne : aucune relance.

    C'est exactement la situation qui produisait une relance par minute pendant
    des heures. Relancer n'a jamais rétabli MetaApi — ça ne faisait que casser une
    boucle saine."""
    _pouls(monkeypatch, loop_age_s=10, metaapi_age_s=1200)
    assert _check() is False
    assert bancd["relances"] == 0
    assert "metaapi_down" in bancd["notifs"]      # on ALERTE…
    assert "bot_resume" not in bancd["notifs"]    # …mais on ne relance pas


def test_boucle_morte_RELANCE(monkeypatch, bancd):
    """Le seul cas qui justifie une relance : la boucle n'a plus fait un seul tour."""
    _pouls(monkeypatch, loop_age_s=1200, metaapi_age_s=1200)
    assert _check() is True
    assert bancd["relances"] == 1
    assert "bot_resume" in bancd["notifs"]


def test_reconnexion_en_cours_on_laisse_finir(monkeypatch, bancd):
    """Boucle bloquée dans une reconnexion légitime : ne pas la tuer.

    La tuer la ferait repartir de zéro — c'est le cercle vicieux lui-même."""
    monkeypatch.setattr(bot_loop.metaapi_client, "is_connecting", lambda: True)
    _pouls(monkeypatch, loop_age_s=1200, metaapi_age_s=1200)
    assert _check() is False
    assert bancd["relances"] == 0


def test_tout_va_bien_ne_fait_rien(monkeypatch, bancd):
    _pouls(monkeypatch, loop_age_s=10, metaapi_age_s=10)
    assert _check() is False
    assert bancd["relances"] == 0
    assert bancd["notifs"] == []


def test_arret_manuel_respecte(monkeypatch, bancd):
    """running=false : le gardien ne ressuscite jamais un bot arrêté à la main."""
    monkeypatch.setattr(bot_loop.store, "get_bot_state", _async(lambda: {"running": False}))
    _pouls(monkeypatch, loop_age_s=99999, metaapi_age_s=99999)
    assert _check() is False
    assert bancd["relances"] == 0
    assert bancd["notifs"] == []


# ─────────────────────────── cohérence des seuils ───────────────────────────

def test_seuil_boucle_morte_depasse_le_pire_tour_normal():
    """Le seuil de « boucle morte » doit couvrir le tour le plus lent POSSIBLE.

    Sinon on retombe dans le défaut d'origine : tuer une boucle qui travaillait.
    Pire tour : 4 téléchargements de bougies (90 s chacun) + lectures de compte
    (20 s × 2 avec réessai) + positions + placement d'ordre (30 s) ≈ 8 min."""
    pire_tour_s = 4 * 90 + 2 * 20 + 40 + 30      # ≈ 470 s
    assert bot_loop._WATCHDOG_STALE_S > pire_tour_s


def test_reconnexion_complete_tient_sous_le_seuil():
    """Les cinq étapes de connexion cumulées doivent rester sous le seuil du gardien.

    C'était la cause racine : 5 × 240 s = 20 min de reconnexion possible, pour un
    gardien qui frappait à 5 min. Ce test casse si quelqu'un rallonge les délais."""
    from metaapi_client import MetaApiWrapper
    pire_connexion_s = 5 * MetaApiWrapper._STEP_TIMEOUT_S
    assert pire_connexion_s <= bot_loop._WATCHDOG_STALE_S


def test_metaapi_alerte_avant_que_la_boucle_soit_declaree_morte():
    """L'alerte « broker muet » doit arriver AVANT le seuil de relance, pour qu'on
    voie la vraie cause plutôt qu'une relance mystérieuse."""
    assert bot_loop._METAAPI_STALE_S < bot_loop._WATCHDOG_STALE_S
