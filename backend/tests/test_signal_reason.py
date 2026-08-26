"""La raison d'un signal doit décrire ce qui s'est VRAIMENT produit.

Test unitaire pur (ni serveur, ni base, ni MetaApi) :
    py -m pytest backend/tests/test_signal_reason.py -v

Les filtres d'entrée sont désactivables et le sont en pratique (FVG, séquence
sweep→CHoCH, OB non mitigé). Sans ce test, rien n'empêche de recoller un texte figé
« Sweep→CHoCH + FVG » sur un trade qui n'avait ni CHoCH ni FVG.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smc import OrderBlock, _signal_reason  # noqa: E402

PD = {"top": 2100.0, "bottom": 2000.0, "mid": 2050.0}


def _ob(zone="wick", mitigated=False):
    return OrderBlock(start_idx=0, end_idx=1, top=2030.0, bottom=2020.0,
                      direction="bullish", time=None, mitigated=mitigated, zone=zone)


def test_tous_filtres_actifs_donne_le_texte_historique():
    """Quand tout est vérifié, le libellé reste celui d'avant, au mot près."""
    txt = _signal_reason("buy", 2.35, 2025.0, PD, _ob(), "close",
                         has_sweep=True, has_choch=True, choch_after_sweep=True, fvg_ok=True)
    assert txt == "Sweep→CHoCH + FVG dans OB discount → BUY (RR 1:2.35)"


def test_sweep_seul_sans_fvg_sur_ob_mitige():
    txt = _signal_reason("sell", 2.10, 2075.0, PD, _ob(mitigated=True), "close",
                         has_sweep=True, has_choch=False, choch_after_sweep=False, fvg_ok=False)
    assert txt == "Sweep seul sans FVG dans OB mitigé premium → SELL (RR 1:2.10)"


def test_ordre_inverse_choch_puis_sweep():
    txt = _signal_reason("buy", 1.5, 2025.0, PD, _ob(), "close",
                         has_sweep=True, has_choch=True, choch_after_sweep=False, fvg_ok=True)
    assert txt.startswith("CHoCH→Sweep ")


def test_choch_seul():
    txt = _signal_reason("buy", 1.5, 2025.0, PD, _ob(), "close",
                         has_sweep=False, has_choch=True, choch_after_sweep=False, fvg_ok=True)
    assert txt.startswith("CHoCH seul ")


def test_zone_deduite_du_prix_pas_du_sens_du_trade():
    """Avec premium/discount désactivé, un ACHAT peut se faire en premium : ça doit se voir."""
    txt = _signal_reason("buy", 1.2, 2080.0, PD, _ob(), "close",
                         has_sweep=True, has_choch=True, choch_after_sweep=True, fvg_ok=True)
    assert " premium " in txt and " discount " not in txt


def test_type_de_poi_et_mode_entree():
    txt = _signal_reason("buy", 1.8, 2025.0, PD, _ob(zone="breaker"), "tap",
                         has_sweep=True, has_choch=False, choch_after_sweep=False, fvg_ok=True)
    assert "tap sur Breaker discount" in txt

    txt50 = _signal_reason("buy", 1.8, 2025.0, PD, _ob(zone="bpr"), "zone_50",
                           has_sweep=True, has_choch=False, choch_after_sweep=False, fvg_ok=True)
    assert "sous la médiane de BPR discount" in txt50


def test_confluences_verifiees_en_suffixe():
    txt = _signal_reason("buy", 1.9, 2025.0, PD, _ob(), "close",
                         has_sweep=True, has_choch=True, choch_after_sweep=True, fvg_ok=True,
                         displacement_ok=True, inducement_swept=True, second_choch_ok=True)
    assert txt == ("Sweep→CHoCH + FVG dans OB discount · displacement · inducement pris "
                   "· 2e CHoCH → BUY (RR 1:1.90)")


def test_aucune_confluence_aucun_suffixe():
    txt = _signal_reason("buy", 1.9, 2025.0, PD, _ob(), "close",
                         has_sweep=True, has_choch=True, choch_after_sweep=True, fvg_ok=True)
    assert "·" not in txt
