"""Le backtest ne doit JAMAIS voir le futur (défaut corrigé le 2026-08-26).

Test unitaire pur : il n'a besoin ni du serveur, ni de MongoDB, ni de MetaApi.
    py -m pytest backend/tests/test_backtest_lookahead.py -v

Principe : on fabrique des bougies M1 dont le prix MONTE strictement minute après
minute. À tout instant, le plus haut des bougies déjà écoulées est donc celui de la
bougie d'entrée courante. Si la fenêtre HTF/MTF/D1 contient la moindre information
future, son dernier plus haut dépasse celui de la bougie analysée — et le test échoue.

Avec l'ancien code (`bisect_right` sur les temps de DÉBUT), la bougie supérieure en
cours était fournie DÉJÀ AGRÉGÉE avec son high/low/close définitifs : ce test échoue.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402


def _rising_m1(n=1500):
    """n bougies M1 dont chaque prix est strictement supérieur à la minute précédente."""
    t0 = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # un lundi
    out = []
    for i in range(n):
        base = 2000.0 + i * 0.10
        out.append({"time": t0 + timedelta(minutes=i), "open": base,
                    "high": base + 0.05, "low": base - 0.05, "close": base + 0.02})
    return out


SETTINGS = {
    "scalping_d1": "H1", "scalping_htf": "M15", "scalping_mtf": "M5", "scalping_ltf": "M1",
    "max_trades_per_day": 500, "max_consec_losses": 3, "max_drawdown_pct": 100.0,
}


def _run_with_spy(monkeypatch, settings):
    """Rejoue un backtest en espionnant chaque appel au moteur SMC."""
    calls = []
    violations = []

    def spy(candles_bias, candles_struct, candles_entry, candles_daily=None, **kw):
        now_high = candles_entry[-1]["high"]
        calls.append(candles_entry[-1]["time"])
        for name, window in (("HTF", candles_bias), ("MTF", candles_struct),
                             ("D1", candles_daily or [])):
            if window and window[-1]["high"] > now_high + 1e-9:
                violations.append(
                    f"{name} : dernière bougie high={window[-1]['high']:.2f} > "
                    f"bougie d'entrée {candles_entry[-1]['time']} high={now_high:.2f}")
        return {"bias": None, "signal": None, "reject_reason": "test", "reject_stage": None}

    monkeypatch.setattr(bt, "analyze", spy)
    monkeypatch.setattr(bt.sess, "is_in_session",
                        lambda dt, s: {"in_session": True, "session": "london"})
    asyncio.run(bt.run_backtest({"symbol": "XAUUSD", "mode": "scalping", "spread_points": 16},
                                _rising_m1(), settings=settings))
    return calls, violations


def test_les_fenetres_superieures_ne_contiennent_pas_le_futur(monkeypatch):
    calls, violations = _run_with_spy(monkeypatch, SETTINGS)
    assert len(calls) > 200, "le backtest n'a quasiment pas analysé de bougies"
    assert not violations, "anticipation détectée :\n" + "\n".join(violations[:5])


def test_idem_avec_un_etage_journalier_calendaire(monkeypatch):
    s = dict(SETTINGS, scalping_d1="D1")
    calls, violations = _run_with_spy(monkeypatch, s)
    assert len(calls) > 200
    assert not violations, "anticipation détectée :\n" + "\n".join(violations[:5])


def test_la_bougie_en_formation_est_bien_fournie(monkeypatch):
    """Le correctif ne doit pas se contenter de SUPPRIMER la bougie en cours : le bot
    live la voit (partielle). Sur des bougies M1 régulières, la dernière bougie M15 vue
    doit donc coller à la minute analysée, pas être en retard d'un cycle entier."""
    seen = {}

    def spy(candles_bias, candles_struct, candles_entry, candles_daily=None, **kw):
        seen["ecart"] = max(seen.get("ecart", 0),
                            round(candles_entry[-1]["high"] - candles_bias[-1]["high"], 6))
        return {"bias": None, "signal": None, "reject_reason": "test", "reject_stage": None}

    monkeypatch.setattr(bt, "analyze", spy)
    monkeypatch.setattr(bt.sess, "is_in_session",
                        lambda dt, s: {"in_session": True, "session": "london"})
    asyncio.run(bt.run_backtest({"symbol": "XAUUSD", "mode": "scalping", "spread_points": 16},
                                _rising_m1(), settings=SETTINGS))
    # Bougie en formation fournie → la fenêtre HTF est à jour à la minute près (écart 0).
    # Si on l'avait simplement supprimée, l'écart atteindrait la durée d'une M15 (1,50).
    assert seen["ecart"] == 0.0, f"la bougie en formation manque (écart {seen['ecart']})"
