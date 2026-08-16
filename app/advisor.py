"""Observations patrimoniales.

Ce module ne conseille pas : il **constate**. Il énonce des faits vérifiables —
plafonds légaux, ratios, écarts avec les cibles que l'utilisateur a lui-même
fixées — et jamais de recommandation d'allocation ou d'arbitrage.

« Votre Livret A a dépassé son plafond de versements » est un constat.
« Placez l'excédent sur votre PEA » serait un conseil, et n'a pas sa place ici.

Calcul pur : aucune écriture, aucun appel réseau, aucune dépendance à Flask
hors lecture des réglages. Une alerte qui se déclenche à tort est pire que pas
d'alerte du tout — chaque règle est donc testée dans les deux sens.
"""
from datetime import date

from . import finance
from .db import get_setting

# Types de produits soumis à un plafond de versements.
PRODUITS_PLAFONNES = ("Livret", "LDDS", "LEP", "LivretJeune", "PEL", "CEL")

# Ancienneté à partir de laquelle la fiscalité des retraits change.
MATURITES = {"PEA": 5, "AssuranceVie": 8}

# Types dont la valeur dépend d'un taux saisi par l'utilisateur.
TYPES_A_TAUX = ("Livret", "LDDS", "LEP", "LivretJeune", "PEL", "CEL", "DepotTerme")

# Base de comparaison pour la concentration : comparer une ligne de PEA au
# poids d'un appartement n'aurait pas de sens.
FAMILLES_FINANCIERES = ("Marches financiers", "Epargne reglementee",
                        "Liquidites", "Crypto")

# Seules ces familles peuvent déclencher une alerte de concentration. Un livret
# réglementé est garanti en capital : y concentrer son épargne n'est pas un
# risque de marché, et le signaler serait un faux positif.
FAMILLES_EXPOSEES = ("Marches financiers", "Crypto")


def _reglages(fournis=None):
    if fournis is not None:
        return fournis
    return {
        "plafonds": get_setting("plafonds_produits", {}) or {},
        "mois_precaution_cible": float(get_setting("mois_precaution_cible", 4) or 4),
        "seuil_concentration": float(get_setting("seuil_concentration", 40) or 40),
        "seuil_crypto": float(get_setting("seuil_crypto", 10) or 10),
        "seuil_endettement": float(get_setting("seuil_endettement", 35) or 35),
    }


def _alerte(niveau, titre, detail, asset_id=None, action=None):
    return {"niveau": niveau, "titre": titre, "detail": detail,
            "asset_id": asset_id, "action": action}


def alertes(snapshot, metrics, repartition=None, marche=None, reglages=None,
            at_date=None):
    """Liste des observations, de la plus urgente à la plus anodine."""
    cfg = _reglages(reglages)
    at_date = finance.parse_date(at_date) or date.today()
    out = []

    out += _plafonds(snapshot, cfg)
    out += _maturites(snapshot, at_date)
    out += _precaution(metrics, cfg)
    out += _endettement(metrics, cfg)
    out += _concentration(snapshot, metrics, cfg)
    out += _repartition(repartition)
    out += _livrets_sans_taux(snapshot)
    out += _cours(marche)

    ordre = {"attention": 0, "info": 1}
    return sorted(out, key=lambda a: ordre.get(a["niveau"], 2))


# --- règles ---------------------------------------------------------------

def _plafonds(snapshot, cfg):
    """Plafonds de versements des produits réglementés.

    La loi plafonne les VERSEMENTS, pas le solde : un livret peut légitimement
    dépasser son plafond par capitalisation des intérêts. Le dire autrement
    laisserait croire à une irrégularité.
    """
    out = []
    plafonds = cfg["plafonds"]
    for a in snapshot.get("assets", []):
        plafond = plafonds.get(a["type"])
        if not plafond:
            continue

        if a["type"] == "PEA":
            # Ici on connaît vraiment les versements : ce sont les mouvements.
            verse = a.get("investi") or 0
            if verse >= plafond:
                out.append(_alerte(
                    "attention", f"{a['label']} : plafond de versements atteint",
                    f"{_eur(verse)} versés sur un maximum de {_eur(plafond)}. "
                    "Aucun versement supplémentaire n'est possible ; la valeur "
                    "peut continuer de progresser.",
                    a["id"], "asset"))
            elif verse >= plafond * 0.95:
                out.append(_alerte(
                    "info", f"{a['label']} : proche du plafond de versements",
                    f"{_eur(verse)} versés sur {_eur(plafond)}, "
                    f"soit {_eur(plafond - verse)} de marge restante.",
                    a["id"], "asset"))
            continue

        if a["type"] not in PRODUITS_PLAFONNES:
            continue
        solde = a.get("valeur") or 0
        if solde > plafond:
            out.append(_alerte(
                "info", f"{a['label']} : au-dessus du plafond de versements",
                f"{_eur(solde)} pour un plafond de {_eur(plafond)}. "
                "C'est normal si l'écart vient des intérêts capitalisés : "
                "seuls eux peuvent encore le faire grossir, plus aucun "
                "versement n'est possible.",
                a["id"], "asset"))
        elif solde >= plafond * 0.95:
            out.append(_alerte(
                "info", f"{a['label']} : proche du plafond",
                f"{_eur(solde)} sur {_eur(plafond)}, "
                f"soit {_eur(plafond - solde)} de marge restante.",
                a["id"], "asset"))
    return out


def _maturites(snapshot, at_date):
    """Ancienneté fiscale, tant qu'elle n'est pas atteinte.

    Une fois le seuil franchi, il n'y a plus rien à surveiller : signaler la
    maturité indéfiniment ne serait que du bruit.
    """
    out = []
    for a in snapshot.get("assets", []):
        annees = MATURITES.get(a["type"])
        if not annees:
            continue
        ouverture = finance.parse_date(a.get("date_acquisition"))
        if not ouverture:
            continue
        echeance = finance.add_months(ouverture, annees * 12)
        if echeance <= at_date:
            continue
        mois = (echeance.year - at_date.year) * 12 + (echeance.month - at_date.month)
        out.append(_alerte(
            "info", f"{a['label']} : maturité fiscale le {_date(echeance)}",
            f"Encore {mois} mois avant les {annees} ans d'ancienneté, seuil "
            "au-delà duquel la fiscalité des retraits change.",
            a["id"], "asset"))
    return out


def _precaution(metrics, cfg):
    mois = metrics.get("mois_couverture_urgence")
    cible = cfg["mois_precaution_cible"]
    if mois is None or mois >= cible:
        return []
    return [_alerte(
        "attention", "Épargne de précaution sous votre cible",
        f"{_num(mois)} mois de dépenses couverts par vos livrets, "
        f"pour une cible de {_num(cible)} mois "
        f"({_eur(metrics.get('solde_livrets'))} disponibles, "
        f"{_eur(metrics.get('depenses_moyennes_3m'))} de dépenses mensuelles).",
        None, "settings")]


def _endettement(metrics, cfg):
    taux = metrics.get("taux_endettement")
    seuil = cfg["seuil_endettement"]
    if taux is None or taux <= seuil:
        return []
    return [_alerte(
        "attention", "Taux d'endettement au-dessus du seuil courant",
        f"{_num(taux)} % de vos revenus passent en mensualités de crédit "
        f"({_eur(metrics.get('mensualites_mois'))} sur "
        f"{_eur(metrics.get('revenus_mois'))}). Les banques retiennent "
        f"habituellement {_num(seuil)} % comme limite.",
        None, None)]


def _concentration(snapshot, metrics, cfg):
    """Poids d'une seule ligne dans les actifs financiers."""
    out = []
    crypto_pct = metrics.get("crypto_pct_patrimoine")
    if crypto_pct is not None and crypto_pct > cfg["seuil_crypto"]:
        out.append(_alerte(
            "info", "Poids de la crypto au-dessus de votre seuil",
            f"{_num(crypto_pct)} % du patrimoine net "
            f"({_eur(metrics.get('crypto_montant'))}), pour un seuil fixé à "
            f"{_num(cfg['seuil_crypto'])} %.",
            None, "settings"))

    financiers = [a for a in snapshot.get("assets", [])
                  if a.get("famille") in FAMILLES_FINANCIERES]
    total = sum(a.get("valeur") or 0 for a in financiers)
    # Avec un seul produit financier, dire qu'il pèse 100 % est exact et sans
    # intérêt : il faut au moins deux lignes pour parler de répartition.
    if total <= 0 or len(financiers) < 2:
        return out
    seuil = cfg["seuil_concentration"]
    for a in financiers:
        if a.get("famille") not in FAMILLES_EXPOSEES:
            continue
        part = 100 * (a.get("valeur") or 0) / total
        if part > seuil:
            out.append(_alerte(
                "info", f"{a['label']} concentre {_num(part)} % de vos actifs financiers",
                f"{_eur(a.get('valeur'))} sur {_eur(total)}, "
                f"au-delà du seuil de {_num(seuil)} % que vous avez fixé.",
                a["id"], "asset"))
    return out


def _repartition(repartition):
    """Écarts avec la répartition cible.

    Regroupés en une seule ligne dès qu'il y en a plusieurs : trois alertes
    d'affilée pour un même sujet — vos cibles ne correspondent pas à votre
    situation — noient les autres observations sans rien apprendre de plus.
    """
    if not repartition:
        return []
    ecarts = [b for b in repartition.get("buckets", [])
              if b.get("ecart_pct") is not None and abs(b["ecart_pct"]) > 10]
    if not ecarts:
        return []

    if len(ecarts) == 1:
        b = ecarts[0]
        sens = "au-dessus" if b["ecart_pct"] > 0 else "en dessous"
        return [_alerte(
            "info", f"Poche {b['label']} : {_num(abs(b['ecart_pct']))} points {sens} de la cible",
            f"{_num(b.get('reel_pct'))} % constatés pour "
            f"{_num(b.get('cible_pct'))} % visés, soit un écart de "
            f"{_eur(abs(b.get('ecart_montant') or 0))}.",
            None, "settings")]

    detail = " · ".join(
        f"{b['label']} {_num(b.get('reel_pct'))} % pour {_num(b.get('cible_pct'))} % visés"
        for b in ecarts)
    return [_alerte(
        "info", f"Répartition éloignée de vos cibles sur {len(ecarts)} poches",
        f"{detail}. Ces cibles se règlent dans les paramètres — si elles ne "
        "correspondent plus à votre situation, ce sont elles qu'il faut revoir.",
        None, "settings")]


def _livrets_sans_taux(snapshot):
    manquants = [a for a in snapshot.get("assets", [])
                 if a["type"] in TYPES_A_TAUX
                 and not (a.get("metadata") or {}).get("taux_annuel")]
    if not manquants:
        return []
    noms = ", ".join(a["label"] for a in manquants[:3])
    reste = "" if len(manquants) <= 3 else f" et {len(manquants) - 3} autre(s)"
    return [_alerte(
        "info", "Taux manquant sur un produit d'épargne",
        f"{noms}{reste} : sans taux annuel, le montant reste figé à ce que vous "
        "avez saisi, sans capitalisation des intérêts.",
        manquants[0]["id"], "asset")]


def _cours(marche):
    if not marche or not marche.get("active") or not marche.get("cache_perime"):
        return []
    return [_alerte(
        "info", "Cours de marché périmés",
        "Les valorisations affichées reposent sur les derniers cours en cache. "
        "Rafraîchissez-les depuis l'onglet Patrimoine.",
        None, None)]


# --- mise en forme --------------------------------------------------------

def _eur(v):
    if v is None:
        return "—"
    return f"{v:,.0f} €".replace(",", " ")


def _num(v):
    if v is None:
        return "—"
    return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _date(d):
    d = finance.parse_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"
