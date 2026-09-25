"""P&L réalisé du jour (Dashboard) — calcul pur, sans serveur ni MetaApi.

Le « P&L JOUR » affichait équité − solde, c'est-à-dire le gain LATENT : une journée à
−400 $ réalisés sans position ouverte affichait 0. Il se calcule désormais sur les
transactions broker du jour (`bot_loop.realized_pnl_from_deals`)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot_loop import realized_pnl_from_deals  # noqa: E402


def _deal(dtype, entry, profit=0.0, swap=0.0, commission=0.0):
    return {"type": dtype, "entryType": entry, "profit": profit, "swap": swap,
            "commission": commission}


def test_somme_profit_swap_commission_des_clotures():
    deals = [
        _deal("DEAL_TYPE_BUY", "DEAL_ENTRY_IN", commission=-3.5),
        _deal("DEAL_TYPE_SELL", "DEAL_ENTRY_OUT", profit=-200.0, swap=-1.2, commission=-3.5),
    ]
    assert realized_pnl_from_deals(deals) == {"realized": -208.2, "closes": 1}


def test_tp_partiel_compte_meme_si_la_position_reste_ouverte():
    # TP1 a fermé 50 % : c'est de l'argent encaissé, même si le reste court encore.
    deals = [_deal("DEAL_TYPE_SELL", "DEAL_ENTRY_IN"),
             _deal("DEAL_TYPE_BUY", "DEAL_ENTRY_OUT", profit=100.0)]
    assert realized_pnl_from_deals(deals)["realized"] == 100.0


def test_depot_et_retrait_ne_sont_pas_du_pnl():
    deals = [_deal("DEAL_TYPE_BALANCE", "", profit=50000.0),
             _deal("DEAL_TYPE_CREDIT", "", profit=1000.0),
             _deal("DEAL_TYPE_SELL", "DEAL_ENTRY_OUT", profit=270.08)]
    assert realized_pnl_from_deals(deals) == {"realized": 270.08, "closes": 1}


def test_journee_vide():
    assert realized_pnl_from_deals([]) == {"realized": 0.0, "closes": 0}
