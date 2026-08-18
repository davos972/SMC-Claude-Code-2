"""Compare A/B : configuration NORMALE vs configuration normale + SESSION ASIATIQUE.

Deux backtests sur EXACTEMENT les mêmes bougies M1 (téléchargées une seule fois puis
mises en cache), avec les réglages RÉELS de l'app lus dans MongoDB — le seul écart
entre les deux runs est `session_asia_enabled`.

Usage (depuis backend/, avec le .env pointant sur la base de l'app) :

    py -m tools.backtest_asia_compare --months 10
    py -m tools.backtest_asia_compare --months 10 --symbol XAUUSD --spread 25

Notes :
  - lecture seule : n'écrit rien dans Mongo, ne démarre pas la boucle de trading.
    Il ouvre en revanche une connexion MetaApi (RPC, lecture d'historique) sur le
    compte configuré — sans effet sur les positions.
  - le cache M1 est écrit dans backend/_m1_cache_<symbole>_<début>_<fin>.json
    (préfixe `_` = jetable, ignoré par Git, cf. Claude.md §11).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

import backtest as bt_engine  # noqa: E402
import store  # noqa: E402
from metaapi_client import metaapi_client  # noqa: E402


async def _load_candles(symbol: str, start_dt: datetime, end_dt: datetime) -> list:
    cache = BACKEND / f"_m1_cache_{symbol}_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.json"
    if cache.exists():
        candles = json.loads(cache.read_text())
        print(f"Cache réutilisé : {cache.name} ({len(candles)} bougies M1)")
        return candles

    async def on_status(label: str, _pct: float) -> None:
        print(f"  {label}", end="\r", flush=True)

    candles = await bt_engine.download_m1_history(metaapi_client, symbol, start_dt, end_dt,
                                                  on_status=on_status)
    print()
    if candles:
        cache.write_text(json.dumps(candles))
        print(f"Cache écrit : {cache.name} ({len(candles)} bougies M1)")
    return candles


def _print_report(title: str, metrics: dict) -> None:
    print(f"\n── {title} ──")
    print(f"  Trades      : {metrics.get('trades_count')}")
    print(f"  Winrate     : {metrics.get('winrate')} %")
    print(f"  Profit fact.: {metrics.get('profit_factor')}")
    print(f"  RR moyen    : 1:{metrics.get('avg_rr')}")
    print(f"  P&L total   : {metrics.get('total_pnl')} $ (equity finale {metrics.get('final_equity')} $)")
    print(f"  DD max      : {metrics.get('max_drawdown_pct')} %")
    for name, b in sorted((metrics.get("by_session") or {}).items()):
        print(f"    · {name:8s} {b['trades_count']:4d} trades | WR {b['winrate']:5.1f} % | "
              f"PF {b['profit_factor']:5.2f} | P&L {b['total_pnl']:+10.2f} $")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", type=int, default=10, help="profondeur d'historique en mois (défaut 10)")
    ap.add_argument("--symbol", default=None, help="symbole (défaut : celui des réglages)")
    ap.add_argument("--spread", type=float, default=25.0, help="spread simulé en points (défaut 25)")
    args = ap.parse_args()

    settings = await store.get_settings()
    symbol = args.symbol or settings.get("symbol", "XAUUSD")
    end_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=int(args.months * 30.5))

    token = settings.get("metaapi_token") or os.environ.get("METAAPI_TOKEN", "")
    account_id = settings.get("metaapi_account_id") or os.environ.get("METAAPI_ACCOUNT_ID", "")
    if not (token and account_id):
        print("MetaApi non configuré (token/accountId absents des réglages et du .env).")
        return 1
    await metaapi_client.configure(token, account_id)

    print(f"Symbole {symbol} — période {start_dt:%Y-%m-%d} → {end_dt:%Y-%m-%d} "
          f"({(end_dt - start_dt).days} jours), spread {args.spread} points")
    candles = await _load_candles(symbol, start_dt, end_dt)
    if not candles:
        print("Aucune bougie M1 récupérée — abandon.")
        return 1

    try:
        spec = await metaapi_client.get_symbol_spec(symbol)
        point_size = float(spec.get("point_size", 0.01))
        contract_size = float(spec.get("contract_size", 100.0))
    except Exception as e:  # spécifications indisponibles → défauts XAUUSD
        print(f"get_symbol_spec échoué ({e}) — défauts XAUUSD 0.01 / 100")
        point_size, contract_size = 0.01, 100.0

    req = {"mode": settings.get("mode", "scalping"), "spread_points": args.spread}
    results = {}
    for label, asia in (("Configuration normale", False), ("Normale + session asiatique", True)):
        s = dict(settings, session_asia_enabled=asia)
        res = await bt_engine.run_backtest(req, candles, settings=s,
                                           point_size=point_size, contract_size=contract_size)
        results[label] = res["metrics"]
        _print_report(label, res["metrics"])

    a, b = results["Configuration normale"], results["Normale + session asiatique"]
    print("\n── Écart apporté par la session asiatique ──")
    print(f"  Trades   : {b['trades_count'] - a['trades_count']:+d}")
    print(f"  P&L      : {b['total_pnl'] - a['total_pnl']:+.2f} $")
    print(f"  PF       : {a['profit_factor']} → {b['profit_factor']}")
    print(f"  DD max   : {a['max_drawdown_pct']} % → {b['max_drawdown_pct']} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
