"""Règle de cohérence prop firm — calcul pur, sans serveur ni MongoDB ni MetaApi.

Rappel de la décision (2026-09-08) : cette règle N'ARRÊTE JAMAIS le bot. Elle bloque un
payout, elle ne fait pas perdre le compte. Ces tests vérifient le CALCUL, pas un arrêt.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_loop import prop_consistency  # noqa: E402

S = {"prop_firm_enabled": True, "prop_consistency_pct": 20.0,
     "prop_daily_reset_hour_est": 17}


def t(close_time, pnl, status="closed"):
    return {"status": status, "pnl": pnl, "close_time": close_time}


def test_aucun_trade():
    r = prop_consistency([], S)
    assert r["ok"] is True
    assert r["ratio_pct"] is None
    assert r["profit_total"] == 0.0


def test_un_seul_jour_gagnant_depasse_forcement():
    """Au démarrage, le premier jour vaut 100 % du profit : la règle est dépassée,
    et c'est normal — elle n'est satisfiable qu'après plusieurs jours."""
    r = prop_consistency([t("2026-09-08T12:00:00+00:00", 500.0)], S)
    assert r["ratio_pct"] == 100.0
    assert r["ok"] is False
    # Il faut 2500 $ au total pour que 500 $ ne pèsent que 20 % → il manque 2000 $.
    assert r["manque_pour_payout"] == 2000.0


def test_repartition_conforme():
    trades = [t("2026-09-0%dT12:00:00+00:00" % d, 200.0) for d in (1, 2, 3, 4, 5)]
    r = prop_consistency(trades, S)
    assert r["jours"] == 5
    assert r["ratio_pct"] == 20.0
    assert r["ok"] is True                      # exactement à la limite → conforme
    assert r["manque_pour_payout"] == 0.0


def test_un_jour_ecrase_les_autres():
    trades = [t("2026-09-01T12:00:00+00:00", 1000.0)] + \
             [t("2026-09-0%dT12:00:00+00:00" % d, 100.0) for d in (2, 3, 4)]
    r = prop_consistency(trades, S)
    assert r["meilleur_jour"] == 1000.0
    assert r["meilleur_jour_date"] == "2026-09-01"
    assert r["ratio_pct"] == 76.9               # 1000 / 1300
    assert r["ok"] is False
    assert r["manque_pour_payout"] == 3700.0    # 5000 requis - 1300 actuels


def test_pertes_deduites_du_total():
    """Les jours perdants réduisent le total, donc DÉGRADENT le ratio."""
    trades = [t("2026-09-01T12:00:00+00:00", 300.0),
              t("2026-09-02T12:00:00+00:00", 300.0),
              t("2026-09-03T12:00:00+00:00", -200.0)]
    r = prop_consistency(trades, S)
    assert r["profit_total"] == 400.0
    assert r["meilleur_jour"] == 300.0
    assert r["ratio_pct"] == 75.0
    assert r["jours_gagnants"] == 2


def test_pnl_inconnu_exclu():
    """Garde-fou du §9 : un P&L à None n'est jamais comblé par une estimation."""
    trades = [t("2026-09-01T12:00:00+00:00", 100.0),
              t("2026-09-02T12:00:00+00:00", None)]
    r = prop_consistency(trades, S)
    assert r["profit_total"] == 100.0
    assert r["jours"] == 1


def test_trade_ouvert_ignore():
    trades = [t("2026-09-01T12:00:00+00:00", 100.0),
              t("2026-09-02T12:00:00+00:00", 999.0, status="open")]
    assert prop_consistency(trades, S)["profit_total"] == 100.0


def test_reset_17h_est_regroupe_deux_jours_calendaires():
    """Le jour prop bascule à 17h EST, pas à minuit UTC.

    21:30 UTC le 8 septembre = 17:30 à New York = APRÈS le reset → jour prop du 9.
    16:00 UTC le 9 septembre = 12:00 à New York = AVANT le reset → jour prop du 9 aussi.
    Les deux trades tombent donc dans le MÊME jour prop, alors qu'ils sont sur deux
    dates calendaires différentes.
    """
    trades = [t("2026-09-08T21:30:00+00:00", 400.0),
              t("2026-09-09T16:00:00+00:00", 400.0)]
    r = prop_consistency(trades, S)
    assert r["jours"] == 1, r
    assert r["meilleur_jour"] == 800.0

    # Sans mode prop, c'est le jour calendaire UTC : deux jours distincts.
    r2 = prop_consistency(trades, {"prop_consistency_pct": 20.0})
    assert r2["jours"] == 2, r2


def test_regle_desactivee():
    r = prop_consistency([t("2026-09-01T12:00:00+00:00", 500.0)],
                         {"prop_consistency_pct": 0})
    assert r["ok"] is True
    assert r["ratio_pct"] is None


def test_cumul_negatif_ne_declenche_rien():
    trades = [t("2026-09-01T12:00:00+00:00", 100.0),
              t("2026-09-02T12:00:00+00:00", -400.0)]
    r = prop_consistency(trades, S)
    assert r["profit_total"] == -300.0
    assert r["ok"] is True          # rien à signaler tant qu'on est en perte
    assert r["ratio_pct"] is None
