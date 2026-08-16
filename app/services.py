"""Couche métier : assemble la base et le moteur de calcul.

Rien n'est mis en cache ni figé : chaque appel relit les données vivantes et
recalcule. Corriger une transaction de mars se répercute immédiatement dans
toutes les vues qui l'utilisent.
"""
from collections import defaultdict
from datetime import date, timedelta

from . import finance, market
from .db import (
    execute, famille_of, get_setting, query, row_to_dict, rows_to_list,
)

LIQUID_SAVINGS_TYPES = {"Livret", "LDDS", "LEP", "LivretJeune", "CEL"}
MARKET_TYPES = {"PEA", "CTO", "AssuranceVie", "PER"}


# --- lectures de base -----------------------------------------------------

def get_assets(include_archived=False):
    sql = "SELECT * FROM assets"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY type, label"
    return rows_to_list(query(sql))


def get_asset(asset_id):
    return row_to_dict(query("SELECT * FROM assets WHERE id = ?", (asset_id,), one=True))


def get_movements(asset_id=None):
    if asset_id:
        rows = query(
            "SELECT * FROM asset_movements WHERE asset_id = ? ORDER BY date, created_at",
            (asset_id,),
        )
    else:
        rows = query("SELECT * FROM asset_movements ORDER BY date, created_at")
    return rows_to_list(rows)


def movements_by_asset():
    grouped = defaultdict(list)
    for mv in get_movements():
        grouped[mv["asset_id"]].append(mv)
    return grouped


def get_liabilities():
    return rows_to_list(query("SELECT * FROM liabilities ORDER BY date_debut"))


def get_liability(liability_id):
    return row_to_dict(
        query("SELECT * FROM liabilities WHERE id = ?", (liability_id,), one=True)
    )


def liabilities_with_summary(at_date=None, cache=None):
    at_date = finance.parse_date(at_date) or date.today()
    cache = shared_cache(cache)
    out = []
    for liab in cache["liabilities"]:
        out.append((liab, finance.liability_summary(
            liab, at_date, cache["schedules"].get(liab["id"]))))
    return out


def shared_cache(cache=None):
    """Données indépendantes de la date, lues une seule fois.

    L'archive mensuelle rejoue le calcul du patrimoine pour chaque mois depuis
    le premier mouvement. Sans ce partage, les mêmes actifs, mouvements et
    tableaux d'amortissement étaient relus et recalculés une fois par mois —
    l'onglet Historique mettait 660 ms à s'afficher.

    Le cache ne vit que le temps d'un calcul : il n'est jamais conservé entre
    deux requêtes, donc jamais périmé.
    """
    if cache is None:
        cache = {}
    if "assets" in cache:
        return cache
    cache["assets"] = get_assets(False)
    cache["assets_archived"] = get_assets(True)
    cache["movements"] = movements_by_asset()
    cache["liabilities"] = get_liabilities()
    cache["securities"] = market.securities_by_ticker()
    cache["schedules"] = {
        l["id"]: finance.amortization_schedule(
            l["montant_emprunte"], l["taux_annuel"], l["duree_mois"],
            l["date_debut"], l["assurance_mensuelle"])
        for l in cache["liabilities"]
    }
    return cache


# --- valorisation ---------------------------------------------------------

def market_context(at_date=None, cache=None):
    """Contexte de valorisation, lu une seule fois par photo du portefeuille.

    Lecture pure : aucun appel réseau. Le rafraîchissement est un geste
    explicite (`POST /api/market/refresh`), jamais un effet de bord d'affichage.

    Le contexte existe **même quand les cours sont désactivés** : les intérêts
    de livret et la réévaluation immobilière sont des calculs purement locaux,
    qui n'ont rien à voir avec un accès réseau. Seuls les cours de marché sont
    conditionnés au réglage.
    """
    enabled = bool(get_setting("market_enabled", False))
    if cache is not None and "securities" in cache:
        return {
            "enabled": enabled,
            "prices": market.cached_prices(at_date) if enabled else {},
            "securities": cache["securities"],
        }
    return {
        "enabled": enabled,
        # Seuls les cours conditionnent la valorisation : desactives, la valeur
        # saisie reprend la main.
        "prices": market.cached_prices(at_date) if enabled else {},
        # Les correspondances, elles, sont toujours chargees : ce ne sont que
        # des libelles et des symboles, sans effet sur les montants. Sans cela,
        # vos lignes s'afficheraient sans nom des que les cours sont coupes.
        "securities": market.securities_by_ticker(),
    }


def asset_detail(asset, movements, at_date=None, ctx=None):
    at_date = finance.parse_date(at_date) or date.today()
    is_today = at_date >= date.today()
    saisie = finance.asset_value_at(asset, movements, at_date, use_manual_current=is_today)
    invested = finance.invested_amount(asset, movements)

    # Valeur calculée, par ordre de préférence. Chaque source renvoie None si
    # elle ne peut pas produire un chiffre complet : on retombe alors sur la
    # valeur saisie, jamais sur un total partiel.
    value, source = saisie, "saisie"
    if ctx:
        live, kind = market.market_value(
            asset, movements, ctx["securities"], ctx["prices"]), "marche"
        if live is None and asset["type"] in market.RATE_ASSET_TYPES:
            live, kind = market.rate_value(asset, movements, at_date), "taux"
        elif live is None and asset["type"] in market.INDEXED_ASSET_TYPES:
            live, kind = market.indexed_value(asset, at_date), "indice"
        if live is not None:
            value, source = live, kind

    detail = dict(asset)
    detail["famille"] = famille_of(asset["type"])
    detail["valeur"] = value
    detail["valeur_saisie"] = saisie
    detail["valeur_source"] = source
    detail["investi"] = invested
    detail["plus_value"] = round(value - invested, 2)
    detail["plus_value_pct"] = round((value - invested) / invested, 6) if invested else None
    detail["nb_mouvements"] = len(movements)
    return detail


def portfolio(at_date=None, include_archived=False, ctx=None, cache=None):
    """Photo du patrimoine à une date : actifs valorisés, passifs, net."""
    at_date = finance.parse_date(at_date) or date.today()
    cache = shared_cache(cache)
    grouped = cache["movements"]
    # Le contexte de marché est chargé une seule fois pour tout le portefeuille
    # (et réutilisable par l'appelant, cf. monthly_archive).
    ctx = ctx if ctx is not None else market_context(at_date, cache)
    assets = []
    for asset in cache["assets_archived" if include_archived else "assets"]:
        acq = finance.parse_date(asset["date_acquisition"])
        if acq and acq > at_date:
            continue
        assets.append(asset_detail(asset, grouped.get(asset["id"], []), at_date, ctx))

    liabilities = []
    for liab, summary in liabilities_with_summary(at_date, cache):
        item = dict(liab)
        item.update(summary)
        liabilities.append(item)

    total_actif = round(sum(a["valeur"] for a in assets), 2)
    total_passif = round(sum(l["capital_restant"] for l in liabilities), 2)
    return {
        "date": finance.iso(at_date),
        "assets": assets,
        "liabilities": liabilities,
        "total_actif": total_actif,
        "total_passif": total_passif,
        "patrimoine_net": round(total_actif - total_passif, 2),
    }


def net_worth_at(at_date):
    return portfolio(at_date)["patrimoine_net"]


def repartition(at_date=None, snap=None):
    """Répartition cible vs réelle sur les poches définies en paramètres."""
    snap = snap or portfolio(at_date)
    buckets = get_setting("repartition_cible", []) or []
    if isinstance(buckets, dict):  # ancien format {type: pct}
        buckets = [{"label": k, "types": [k], "pct": v} for k, v in buckets.items()]

    covered, out = set(), []
    for bucket in buckets:
        types = set(bucket.get("types") or [bucket.get("label")])
        covered |= types
        montant = round(sum(a["valeur"] for a in snap["assets"] if a["type"] in types), 2)
        out.append({
            "label": bucket.get("label"),
            "types": sorted(types),
            "cible_pct": float(bucket.get("pct") or 0),
            "montant": montant,
        })
    base = round(sum(b["montant"] for b in out), 2)
    for bucket in out:
        bucket["reel_pct"] = round(100 * bucket["montant"] / base, 2) if base else 0.0
        bucket["ecart_pct"] = round(bucket["reel_pct"] - bucket["cible_pct"], 2)
        cible_montant = base * bucket["cible_pct"] / 100
        bucket["ecart_montant"] = round(bucket["montant"] - cible_montant, 2)
    hors = round(sum(a["valeur"] for a in snap["assets"] if a["type"] not in covered), 2)
    return {"buckets": out, "base": base, "hors_poches": hors}


# --- flux mensuels --------------------------------------------------------

def _non_expense_categories():
    """Catégories comptées comme épargne, pas comme dépense."""
    return set(get_setting("categories_non_depense", []) or [])


def _transfer_categories():
    """Catégories totalement neutres : virements entre vos propres comptes.

    Un LCL → Revolut apparaît deux fois : en débit sur LCL et en crédit sur
    Revolut. Sans neutralisation des DEUX côtés, le même euro gonflerait à la
    fois les dépenses et les revenus.
    """
    return set(get_setting("categories_transfert", []) or [])


def transactions_between(start, end, **filters):
    sql = "SELECT * FROM transactions WHERE date >= ? AND date <= ?"
    args = [finance.iso(start), finance.iso(end)]
    if filters.get("asset_id"):
        sql += " AND asset_id = ?"
        args.append(filters["asset_id"])
    if filters.get("liability_id"):
        sql += " AND liability_id = ?"
        args.append(filters["liability_id"])
    if filters.get("import_id"):
        sql += " AND import_id = ?"
        args.append(filters["import_id"])
    if filters.get("category"):
        sql += " AND category = ?"
        args.append(filters["category"])
    sql += " ORDER BY date DESC, created_at DESC"
    return rows_to_list(query(sql, args))


def flows_cache(cache=None):
    """Transactions et versements groupés par mois, lus une seule fois.

    L'archive interroge la base une fois par mois affiché ; sur plusieurs
    années cela fait autant de requêtes pour un contenu qui tient en un seul
    parcours.
    """
    if cache is None:
        cache = {}
    if "tx_par_mois" in cache:
        return cache
    par_mois = defaultdict(list)
    for t in rows_to_list(query(
            "SELECT * FROM transactions ORDER BY date DESC, created_at DESC")):
        par_mois[(t["date"] or "")[:7]].append(t)
    cache["tx_par_mois"] = par_mois

    versements = defaultdict(float)
    for r in query(
            "SELECT m.montant, m.date, a.type FROM asset_movements m "
            "JOIN assets a ON a.id = m.asset_id WHERE m.type = 'versement'"):
        if r["type"] != "CompteCourant":
            versements[(r["date"] or "")[:7]] += float(r["montant"] or 0)
    cache["versements_par_mois"] = versements
    return cache


def month_flows(year, month, cache=None):
    """Dépenses / revenus / épargne du mois, avec détail par catégorie."""
    start, end = finance.month_bounds(year, month)
    cle = f"{year:04d}-{month:02d}"
    if cache is not None:
        cache = flows_cache(cache)
        txs = cache["tx_par_mois"].get(cle, [])
    else:
        txs = transactions_between(start, end)
    excluded = _non_expense_categories()
    neutres = _transfer_categories()

    def compte(t):
        """Une ligne neutre ne pèse ni sur les dépenses ni sur les revenus."""
        return t["category"] not in neutres

    revenus = round(sum(t["amount"] for t in txs if t["amount"] > 0 and compte(t)), 2)
    depenses = round(sum(
        -t["amount"] for t in txs
        if t["amount"] < 0 and compte(t) and t["category"] not in excluded), 2)
    transferts = round(sum(
        -t["amount"] for t in txs
        if t["amount"] < 0 and t["category"] in excluded), 2)
    transferts_internes = round(sum(
        -t["amount"] for t in txs
        if t["amount"] < 0 and t["category"] in neutres), 2)

    par_categorie = defaultdict(float)
    nb_categorie = defaultdict(int)
    for t in txs:
        if t["amount"] < 0 and compte(t) and t["category"] not in excluded:
            par_categorie[t["category"]] += -t["amount"]
            nb_categorie[t["category"]] += 1
    revenus_par_categorie = defaultdict(float)
    for t in txs:
        if t["amount"] > 0 and compte(t):
            revenus_par_categorie[t["category"]] += t["amount"]

    # Épargne du mois : versements réels sur les actifs (hors compte courant),
    # plus les virements d'épargne saisis en transaction et non rattachés à un
    # actif (évite le double comptage).
    if cache is not None:
        versements = cache["versements_par_mois"].get(cle, 0.0)
    else:
        versements = 0.0
        for r in query(
            "SELECT m.montant, a.type FROM asset_movements m "
            "JOIN assets a ON a.id = m.asset_id "
            "WHERE m.type = 'versement' AND m.date >= ? AND m.date <= ?",
            (finance.iso(start), finance.iso(end)),
        ):
            if r["type"] != "CompteCourant":
                versements += float(r["montant"] or 0)
    versements += sum(
        -t["amount"] for t in txs
        if t["amount"] < 0 and t["category"] in excluded and not t["asset_id"]
    )
    versements = round(versements, 2)

    return {
        "mois": f"{year:04d}-{month:02d}",
        "debut": finance.iso(start),
        "fin": finance.iso(end),
        "revenus": revenus,
        "depenses": depenses,
        "transferts_epargne": transferts,
        "transferts_internes": transferts_internes,
        "solde": round(revenus - depenses - transferts, 2),
        "epargne": versements,
        "taux_epargne": round(versements / revenus, 6) if revenus > 0 else None,
        "nb_transactions": len(txs),
        "par_categorie": sorted(
            ({"category": k, "montant": round(v, 2), "nb": nb_categorie[k]}
             for k, v in par_categorie.items()),
            key=lambda x: -x["montant"],
        ),
        "revenus_par_categorie": sorted(
            ({"category": k, "montant": round(v, 2)} for k, v in revenus_par_categorie.items()),
            key=lambda x: -x["montant"],
        ),
    }


def find_transfer_pairs(days=None, month=None):
    """Rapproche un débit et un crédit qui sont le même mouvement d'argent.

    Un virement LCL → Revolut se retrouve dans deux relevés : débit d'un côté,
    crédit de l'autre, même montant, à quelques jours près. On les apparie.

    Garde-fou contre les faux positifs : les deux lignes doivent provenir
    d'imports différents. Deux mouvements du même relevé sont, par
    construction, sur le même compte — ce ne peut pas être un virement entre
    comptes. Un salaire de 2 450 € et une dépense de 2 450 € du même relevé ne
    seront donc jamais appariés.
    """
    days = int(days if days is not None else get_setting("transfert_jours_tolerance", 4) or 4)
    neutres = _transfer_categories()

    sql = "SELECT * FROM transactions WHERE 1=1"
    args = []
    if month:
        sql += " AND substr(date, 1, 7) = ?"
        args.append(month[:7])
    txs = [t for t in rows_to_list(query(sql, args)) if t["category"] not in neutres]

    debits, credits = defaultdict(list), defaultdict(list)
    for t in txs:
        key = round(abs(t["amount"]), 2)
        (debits if t["amount"] < 0 else credits)[key].append(t)

    pairs, used = [], set()
    for key, sorties in debits.items():
        entrees = credits.get(key) or []
        for sortie in sorties:
            if sortie["id"] in used:
                continue
            date_sortie = finance.parse_date(sortie["date"])
            candidats = [
                e for e in entrees
                if e["id"] not in used
                and e["import_id"] != sortie["import_id"]
                and abs((finance.parse_date(e["date"]) - date_sortie).days) <= days
            ]
            if not candidats:
                continue
            entree = min(candidats, key=lambda e: abs(
                (finance.parse_date(e["date"]) - date_sortie).days))
            used.add(sortie["id"])
            used.add(entree["id"])
            pairs.append({
                "montant": key,
                "ecart_jours": abs((finance.parse_date(entree["date"]) - date_sortie).days),
                "sortie": sortie,
                "entree": entree,
            })
    return sorted(pairs, key=lambda p: (p["sortie"]["date"], -p["montant"]), reverse=True)


def mark_as_transfer(transaction_ids, categorie=None):
    """Bascule des transactions en virement interne (neutre des deux côtés)."""
    if not transaction_ids:
        return 0
    categorie = categorie or (list(_transfer_categories()) or ["Transfert interne"])[0]
    placeholders = ",".join("?" for _ in transaction_ids)
    cur = execute(
        f"UPDATE transactions SET category = ? WHERE id IN ({placeholders})",
        [categorie, *transaction_ids],
    )
    return cur.rowcount


def data_range():
    """Bornes temporelles des données existantes."""
    rows = [
        query("SELECT MIN(date) d FROM transactions", one=True),
        query("SELECT MIN(date) d FROM asset_movements", one=True),
        query("SELECT MIN(date_acquisition) d FROM assets", one=True),
        query("SELECT MIN(date_debut) d FROM liabilities", one=True),
    ]
    dates = [finance.parse_date(r["d"]) for r in rows if r and r["d"]]
    start = min(dates) if dates else date.today()
    return start, date.today()


def monthly_archive(limit=None):
    """Archive mensuelle recalculée à la volée (jamais stockée)."""
    start, end = data_range()
    keys = finance.months_between(start, end)
    if limit:
        keys = keys[-limit:]
    # Un seul chargement pour tous les mois : c'est là que se jouait l'essentiel
    # du temps de rendu de l'onglet Historique.
    cache = shared_cache()
    out = []
    for key in keys:
        year, month = int(key[:4]), int(key[5:])
        flows = month_flows(year, month, cache)
        _, last_day = finance.month_bounds(year, month)
        as_of = min(last_day, date.today())
        snap = portfolio(as_of, cache=cache)
        rep = repartition(as_of, snap)
        out.append({
            "mois": key,
            "depenses": flows["depenses"],
            "revenus": flows["revenus"],
            "solde": flows["solde"],
            "epargne": flows["epargne"],
            "taux_epargne": flows["taux_epargne"],
            "nb_transactions": flows["nb_transactions"],
            "patrimoine_net": snap["patrimoine_net"],
            "total_actif": snap["total_actif"],
            "total_passif": snap["total_passif"],
            "repartition": [
                {"label": b["label"], "reel_pct": b["reel_pct"], "cible_pct": b["cible_pct"]}
                for b in rep["buckets"]
            ],
        })
    return out


# --- métriques transverses ------------------------------------------------

def avg_expenses(months=3, reference=None):
    reference = finance.parse_date(reference) or date.today()
    total, counted = 0.0, 0
    for i in range(1, months + 1):
        d = finance.add_months(reference, -i)
        total += month_flows(d.year, d.month)["depenses"]
        counted += 1
    return round(total / counted, 2) if counted else 0.0


def metrics(at_date=None):
    at_date = finance.parse_date(at_date) or date.today()
    snap = portfolio(at_date)
    net = snap["patrimoine_net"]

    livrets = round(
        sum(a["valeur"] for a in snap["assets"] if a["type"] in LIQUID_SAVINGS_TYPES), 2
    )
    moyenne_depenses = avg_expenses(3, at_date)
    crypto = round(sum(a["valeur"] for a in snap["assets"] if a["type"] == "Crypto"), 2)
    immo = round(sum(a["valeur"] for a in snap["assets"] if a["famille"] == "Immobilier"), 2)

    flows = month_flows(at_date.year, at_date.month)

    # Taux d'endettement : seuls les prêts encore en cours pèsent. Compter une
    # mensualité déjà soldée gonflerait le ratio sans raison.
    mensualites = round(sum(
        l["mensualite_avec_assurance"] for l in snap["liabilities"]
        if l["echeances_payees"] < l["echeances_totales"]), 2)
    revenus = flows["revenus"]

    # Charges fixes : ce qui tombe tous les mois quoi qu'il arrive. Le reste à
    # vivre est ce dont on dispose réellement une fois ces charges et l'épargne
    # mises de côté.
    fixes = set(get_setting("categories_charges_fixes", []) or [])
    debut, fin = finance.month_bounds(at_date.year, at_date.month)
    charges_fixes = round(sum(
        -t["amount"] for t in transactions_between(debut, fin)
        if t["amount"] < 0 and t["category"] in fixes), 2)

    frais = get_setting("frais_annuels", {}) or {}
    frais_annee = frais.get(str(at_date.year), {})
    frais_total = round(
        float(frais_annee.get("ter", 0) or 0) + float(frais_annee.get("courtage", 0) or 0), 2
    )

    return {
        "patrimoine_net": net,
        "total_actif": snap["total_actif"],
        "total_passif": snap["total_passif"],
        "solde_livrets": livrets,
        "depenses_moyennes_3m": moyenne_depenses,
        "mois_couverture_urgence": (
            round(livrets / moyenne_depenses, 2) if moyenne_depenses > 0 else None
        ),
        "crypto_montant": crypto,
        "crypto_pct_patrimoine": round(100 * crypto / net, 2) if net else None,
        "immobilier_montant": immo,
        "taux_epargne_mois": flows["taux_epargne"],
        "epargne_mois": flows["epargne"],
        "revenus_mois": flows["revenus"],
        "depenses_mois": flows["depenses"],
        "mensualites_mois": mensualites,
        "taux_endettement": round(100 * mensualites / revenus, 2) if revenus > 0 else None,
        "charges_fixes_mois": charges_fixes,
        "reste_a_vivre_mois": round(revenus - charges_fixes - flows["epargne"], 2),
        "part_charges_fixes": (
            round(100 * charges_fixes / revenus, 2) if revenus > 0 else None),
        "frais_annuels": frais_total,
        "frais_annuels_detail": frais_annee,
        "frais_pct_encours": (
            round(100 * frais_total / snap["total_actif"], 4) if snap["total_actif"] else None
        ),
    }


def net_worth_series(months=12, reference=None):
    reference = finance.parse_date(reference) or date.today()
    cache = shared_cache()
    out = []
    for i in range(months - 1, -1, -1):
        d = finance.add_months(reference, -i)
        _, last_day = finance.month_bounds(d.year, d.month)
        as_of = min(last_day, date.today())
        snap = portfolio(as_of, cache=cache)
        out.append({
            "mois": f"{d.year:04d}-{d.month:02d}",
            "patrimoine_net": snap["patrimoine_net"],
            "total_actif": snap["total_actif"],
            "total_passif": snap["total_passif"],
        })
    return out


def assets_series(months=12, reference=None):
    """Trajectoire de CHAQUE actif, mois par mois.

    La courbe du patrimoine net dit combien ; celle-ci dit d'où ça vient. Un
    actif ne commence qu'à sa date d'acquisition : avant, la valeur est `None`
    plutôt que zéro, pour que la courbe démarre là où le produit existe au lieu
    de ramper sur l'axe.
    """
    reference = finance.parse_date(reference) or date.today()
    cache = shared_cache()
    mois, valeurs = [], {}
    for i in range(months - 1, -1, -1):
        d = finance.add_months(reference, -i)
        _, last_day = finance.month_bounds(d.year, d.month)
        as_of = min(last_day, date.today())
        mois.append(f"{d.year:04d}-{d.month:02d}")
        presents = {a["id"]: a for a in portfolio(as_of, cache=cache)["assets"]}
        for asset in cache["assets"]:
            trouve = presents.get(asset["id"])
            valeurs.setdefault(asset["id"], []).append(
                trouve["valeur"] if trouve else None)

    series = []
    for asset in cache["assets"]:
        suite = valeurs.get(asset["id"], [])
        if not any(v for v in suite):
            continue                      # jamais rien à montrer sur la période
        series.append({
            "id": asset["id"], "label": asset["label"], "type": asset["type"],
            "famille": famille_of(asset["type"]), "valeurs": suite,
        })
    series.sort(key=lambda s: -(s["valeurs"][-1] or 0))
    return {"mois": mois, "series": series}


def expense_series(months=6, reference=None):
    reference = finance.parse_date(reference) or date.today()
    out = []
    for i in range(months - 1, -1, -1):
        d = finance.add_months(reference, -i)
        flows = month_flows(d.year, d.month)
        out.append({
            "mois": flows["mois"],
            "depenses": flows["depenses"],
            "revenus": flows["revenus"],
            "epargne": flows["epargne"],
        })
    return out


# --- vues spécialisées ----------------------------------------------------

def market_asset_detail(asset_id, at_date=None, ctx=None):
    """PRU, TRI, lignes — pour PEA / CTO / Crypto.

    Quand les cours sont activés, chaque ligne porte en plus son cours, sa
    valeur de marché et son écart au PRU.
    """
    asset = get_asset(asset_id)
    if not asset:
        return None
    movements = get_movements(asset_id)
    at_date = finance.parse_date(at_date) or date.today()
    ctx = ctx if ctx is not None else market_context(at_date)

    detail = asset_detail(asset, movements, at_date, ctx)
    value = detail["valeur"]
    tri = finance.asset_xirr(asset, movements, value, at_date)
    lignes = (
        market.line_values(movements, ctx["securities"], ctx["prices"])
        if ctx else finance.pru_par_ligne(movements)
    )
    return {
        "pru": finance.pru(movements),
        "quantite": finance.quantity_held(movements),
        "lignes": lignes,
        "tri": tri,
        "tri_pct": round(tri * 100, 2) if tri is not None else None,
        "valeur": value,
        "valeur_source": detail["valeur_source"],
        "valeur_saisie": detail["valeur_saisie"],
        "investi": finance.invested_amount(asset, movements),
    }


def real_estate_detail(asset_id, at_date=None):
    """Prêt lié, loyers, charges et rendement locatif net d'un bien."""
    asset = get_asset(asset_id)
    if not asset:
        return None
    at_date = finance.parse_date(at_date) or date.today()
    movements = get_movements(asset_id)
    valeur = finance.asset_value_at(asset, movements, at_date)

    liabs = []
    for liab in rows_to_list(
        query("SELECT * FROM liabilities WHERE asset_id = ?", (asset_id,))
    ):
        item = dict(liab)
        item.update(finance.liability_summary(liab, at_date))
        item["echeancier"] = finance.amortization_schedule(
            liab["montant_emprunte"], liab["taux_annuel"], liab["duree_mois"],
            liab["date_debut"], liab["assurance_mensuelle"],
        )
        liabs.append(item)

    depuis = at_date - timedelta(days=365)
    txs = transactions_between(depuis, at_date, asset_id=asset_id)
    loyers = round(sum(t["amount"] for t in txs if t["amount"] > 0), 2)
    charges = round(
        sum(-t["amount"] for t in txs if t["amount"] < 0 and not t["liability_id"]), 2
    )
    mensualites_an = round(sum(l["mensualite_avec_assurance"] * 12 for l in liabs), 2)

    # Le remboursement du capital n'est pas une charge : il éteint une dette et
    # revient au propriétaire. Le confondre avec les intérêts fait paraître le
    # bien moins rentable qu'il ne l'est. On calcule donc les deux mesures.
    interets_an = 0.0
    for l in liabs:
        for echeance in l.get("echeancier") or []:
            d = finance.parse_date(echeance["date"])
            if d and depuis < d <= at_date:
                interets_an += echeance["interets"] + echeance["assurance"]
    interets_an = round(interets_an, 2)

    rendement = finance.rendement_locatif_net(loyers, charges, mensualites_an, valeur)
    rendement_hors_capital = finance.rendement_locatif_net(
        loyers, charges, interets_an, valeur)
    rendement_brut = round(loyers / valeur, 6) if valeur else None
    return {
        "valeur": valeur,
        "prets": liabs,
        "loyers_12m": loyers,
        "charges_12m": charges,
        "mensualites_12m": mensualites_an,
        "interets_12m": interets_an,
        "cashflow_12m": round(loyers - charges - mensualites_an, 2),
        "rendement_net": rendement,
        "rendement_net_pct": round(rendement * 100, 2) if rendement is not None else None,
        "rendement_hors_capital_pct": (
            round(rendement_hors_capital * 100, 2)
            if rendement_hors_capital is not None else None),
        "rendement_brut_pct": (
            round(rendement_brut * 100, 2) if rendement_brut is not None else None
        ),
        "capital_restant": round(sum(l["capital_restant"] for l in liabs), 2),
        "valeur_nette": round(valeur - sum(l["capital_restant"] for l in liabs), 2),
        "transactions": txs,
    }
