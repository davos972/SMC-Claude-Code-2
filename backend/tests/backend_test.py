"""GoldFlow SMC backend regression tests — degraded mode (no MetaApi token).

Covers all /api endpoints listed in the test request, plus a unit test of the
shared SMC engine `smc.analyze()`.
"""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
import requests
from dotenv import load_dotenv

# Load frontend .env to get the public REACT_APP_BACKEND_URL (preview URL)
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set in /app/frontend/.env"
API = f"{BASE_URL}/api"

# Allow the shared smc module to be imported for the engine unit test
import sys
sys.path.insert(0, "/app/backend")
from smc import analyze  # noqa: E402


@pytest.fixture(scope="session")
def client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- health ----------

class TestHealth:
    def test_health_degraded_defaults(self, client):
        r = client.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["configured"] is False
        assert d["signal_only_mode"] is True
        assert "metaapi" in d and d["metaapi"]["configured"] is False
        assert "bot" in d and "running" in d["bot"]


# ---------- settings ----------

class TestSettings:
    def test_get_defaults(self, client):
        r = client.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        s = r.json()
        # Defaults from DEFAULT_SETTINGS
        assert s.get("trading_mode") == "intraday"
        assert float(s.get("min_rr")) == 2.0
        assert int(s.get("max_consec_losses")) == 3
        assert float(s.get("risk_per_trade_pct")) == 1.0
        assert s.get("signal_only_mode") is True
        # Token must not be exposed in plain form
        assert "metaapi_token" not in s

    def test_put_real_without_confirmation_returns_400(self, client):
        r = client.put(f"{API}/settings", json={"updates": {"account_type": "real"}}, timeout=15)
        assert r.status_code == 400
        # Revert to demo (defensive — should already be demo)
        client.put(f"{API}/settings", json={"updates": {"account_type": "demo", "real_confirmed": False}}, timeout=15)

    def test_put_real_with_confirmation_ok(self, client):
        r = client.put(f"{API}/settings",
                       json={"updates": {"account_type": "real", "real_confirmed": True}}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("account_type") == "real"
        # Reset back to demo
        client.put(f"{API}/settings", json={"updates": {"account_type": "demo", "real_confirmed": False}}, timeout=15)

    # NB: test for "empty token doesn't overwrite" lives in TestZTokenPreservation at the
    # end of the file, because it mutates global MetaApi state and would pollute the
    # degraded-mode assertions of TestBot/TestBacktests.
    pass


# ---------- metaapi endpoints ----------

class TestMetaApi:
    def test_status_initial(self, client):
        r = client.get(f"{API}/metaapi/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "configured" in d
        # Note: a previous test set a fake token; configured may now be True with last_error
        # The key is that the endpoint works and returns the structure
        assert "connected" in d

    def test_test_connection_degraded(self, client):
        # Reset token to ensure degraded by setting account_id empty? The wrapper requires both.
        # We can't easily clear token in API. Instead check based on status.
        r = client.post(f"{API}/metaapi/test-connection", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        # If configured (we set fake token), result will be ok=false with an error msg.
        # If not configured, error should mention non configuré.
        assert d["ok"] is False


# ---------- account / positions / prices / candles ----------

class TestMarketData:
    def test_account_degraded(self, client):
        r = client.get(f"{API}/account", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Either truly not configured or configured-but-fails — both must NOT simulate data
        if d.get("configured") is False:
            assert "error" in d
        else:
            # Connection should fail with our fake token
            assert "error" in d or "data" not in d

    def test_positions_degraded(self, client):
        r = client.get(f"{API}/positions", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "data" in d
        assert isinstance(d["data"], list)
        # In degraded mode, list is empty
        if d.get("configured") is False:
            assert d["data"] == []

    def test_price_degraded(self, client):
        r = client.get(f"{API}/price/XAUUSD", timeout=15)
        assert r.status_code == 200
        d = r.json()
        if d.get("configured") is False:
            assert d.get("error")
        else:
            # configured but unable to fetch
            assert "error" in d or "data" in d

    def test_candles_degraded(self, client):
        r = client.get(f"{API}/candles/XAUUSD", params={"timeframe": "M5"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("data"), list)
        if d.get("configured") is False:
            assert d["data"] == []


# ---------- bot ----------

class TestBot:
    def test_bot_start_without_metaapi(self, client):
        r = client.post(f"{API}/bot/start", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # configured may be False (no real meta), so start must fail
        # Or we set fake token; in that case it may try to start. Check state to confirm.
        # The endpoint condition: if not is_configured -> running False with error.
        # is_configured requires successful configure(); since our fake token failed, this should still be False.
        assert d.get("running") is False
        assert "metaapi" in (d.get("error") or "").lower() or "metaapi" in (d.get("error") or "")

    def test_bot_stop_always_works(self, client):
        r = client.post(f"{API}/bot/stop", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["running"] is False
        assert d["stop_reason"] == "manual"

    def test_bot_state_structure(self, client):
        r = client.get(f"{API}/bot/state", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "running" in d
        assert d["effective_status"] in ("active", "out_of_session", "stopped")
        assert "session" in d
        assert "rail" in d
        rail = d["rail"]
        assert "now_frac" in rail and "london_start_frac" in rail
        assert "signal_only_mode" in d


# ---------- analysis / signals ----------

class TestAnalysisSignals:
    def test_analysis_degraded(self, client):
        r = client.post(f"{API}/analysis/run",
                        json={"symbol": "XAUUSD", "persist": False}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        if d.get("configured") is False:
            assert d.get("error")
            assert d.get("result") is None
        else:
            # Fake token -> connection error; should not return simulated signals
            assert d.get("result") is None or "error" in d

    def test_signals_initial_or_empty(self, client):
        # Clear first
        rd = client.delete(f"{API}/signals", timeout=15)
        assert rd.status_code == 200
        r = client.get(f"{API}/signals", timeout=15)
        assert r.status_code == 200
        assert r.json() == []

    def test_delete_signals(self, client):
        r = client.delete(f"{API}/signals", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        r2 = client.get(f"{API}/signals", timeout=15)
        assert r2.json() == []


# ---------- notifications ----------

class TestNotifications:
    def test_list_notifications(self, client):
        # Trigger a notification by stopping bot
        client.post(f"{API}/bot/stop", timeout=15)
        r = client.get(f"{API}/notifications", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "unread" in d
        assert isinstance(d["items"], list)
        assert isinstance(d["unread"], int)

    def test_read_all(self, client):
        r = client.post(f"{API}/notifications/read-all", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        r2 = client.get(f"{API}/notifications", timeout=15)
        assert r2.json()["unread"] == 0


# ---------- news ----------

class TestNews:
    def test_news_structure(self, client):
        r = client.get(f"{API}/news", params={"currency": "USD"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "events" in d
        assert isinstance(d["events"], list)
        assert "pause" in d
        assert "fetched_at" in d
        # error field exists (may be None)
        assert "error" in d


# ---------- backtests ----------

class TestBacktests:
    def test_backtest_lifecycle_degraded(self, client):
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=3)
        payload = {
            "symbol": "XAUUSD",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "mode": "intraday",
            "spread_points": 25.0,
        }
        r = client.post(f"{API}/backtest", json=payload, timeout=15)
        assert r.status_code == 200
        bt = r.json()
        assert bt["status"] == "pending"
        bt_id = bt["id"]
        # Poll for status update — in degraded mode should become error quickly
        final = None
        for _ in range(15):
            time.sleep(1)
            r2 = client.get(f"{API}/backtest/{bt_id}", timeout=15)
            assert r2.status_code == 200
            cur = r2.json()
            if cur["status"] in ("done", "error"):
                final = cur
                break
        assert final is not None, "Backtest did not finish in time"
        assert final["status"] == "error"
        assert "MetaApi" in (final.get("error") or "")

    def test_list_backtests(self, client):
        r = client.get(f"{API}/backtests", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- stats ----------

class TestStats:
    def test_stats_aggregates(self, client):
        r = client.get(f"{API}/stats", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("signals_total", "accepted", "executed", "by_day", "by_session"):
            assert k in d


# ---------- SMC engine unit test ----------

def _synthetic_candles(n: int = 120, seed: float = 1900.0) -> List[Dict[str, Any]]:
    """Generate n synthetic candles with alternating up/down trends and a final pullback.
    Time is iso-format, ascending in 5 min increments.
    """
    candles = []
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = seed
    for i in range(n):
        # Three phases: uptrend, downtrend, pullback to mid -> creates HTF bias + swings
        if i < n // 3:
            delta = 1.0 + 0.4 * math.sin(i / 2.0)
        elif i < 2 * n // 3:
            delta = -1.0 + 0.4 * math.sin(i / 2.0)
        else:
            delta = 0.6 * math.sin(i / 1.5)
        o = price
        c = price + delta
        h = max(o, c) + 0.5
        lo = min(o, c) - 0.5
        candles.append({
            "time": (t0 + timedelta(minutes=5 * i)).isoformat(),
            "open": float(o), "high": float(h), "low": float(lo), "close": float(c),
        })
        price = c
    return candles


class TestSmcEngine:
    def test_analyze_returns_expected_keys(self):
        htf = _synthetic_candles(150, seed=2000.0)
        ltf = _synthetic_candles(150, seed=2000.0)
        res = analyze(htf, ltf, fractal_n=3, min_rr=2.0)
        assert isinstance(res, dict)
        for key in ("bias", "signal", "reject_reason", "swings_htf",
                    "structure_htf", "order_blocks_htf", "fvgs_ltf",
                    "sweeps_ltf", "premium_discount"):
            assert key in res, f"missing key {key}"
        # Either a signal is produced or reject_reason is set
        assert res["signal"] is not None or res["reject_reason"] is not None

    def test_analyze_insufficient_candles(self):
        res = analyze([], [], fractal_n=3, min_rr=2.0)
        assert res["reject_reason"] == "Insufficient candles"
        assert res["signal"] is None


# ---------- (LAST) token preservation test — mutates global state ----------

class TestZTokenPreservation:
    """Runs last because it mutates MetaApi configuration state in-process."""

    def test_put_empty_token_does_not_overwrite(self, client):
        # First set a fake token
        r1 = client.put(f"{API}/settings",
                        json={"updates": {"metaapi_token": "FAKE_TOKEN_123",
                                          "metaapi_account_id": "acc1"}},
                        timeout=20)
        assert r1.status_code == 200
        # Send empty token — must not overwrite
        r2 = client.put(f"{API}/settings", json={"updates": {"metaapi_token": ""}}, timeout=15)
        assert r2.status_code == 200
        # Verify token still preserved (masked field present)
        r3 = client.get(f"{API}/settings", timeout=15)
        s = r3.json()
        assert "metaapi_token" not in s  # raw token never exposed
        masked = s.get("metaapi_token_masked", "")
        assert masked.endswith("_123") or masked.endswith("123"), f"masked token unexpected: {masked!r}"
