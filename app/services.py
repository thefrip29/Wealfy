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
            "SELECT rowid AS ordre_saisie, * FROM asset_movements "
            "WHERE asset_id = ? ORDER BY date, created_at",
            (asset_id,),
        )
    else:
        rows = query("SELECT rowid AS ordre_saisie, * FROM asset_movements "
                     "ORDER BY date, created_at")
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
    # Tous les actifs, clos compris : un produit clos compte encore dans
    # l'histoire, jusqu'a sa date de cloture (`present_le`).
    cache["assets_all"] = get_assets(True)
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


def present_le(asset, at_date):
    """Le produit existe-t-il a cette date ?

    Ouvert a sa date d'acquisition, il compte jusqu'a la veille de sa cloture.
    Retirer un produit clos de TOUTES les dates reecrivait le passe : la courbe,
    l'archive et le gain de l'annee changeaient le jour ou on le fermait.
    """
    acq = finance.parse_date(asset["date_acquisition"])
    if acq and acq > at_date:
        return False
    if asset.get("archived"):
        fin = finance.parse_date(asset.get("date_cloture"))
        return fin is not None and at_date < fin
    return True


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


NOTE_SOLDE_DECLARE = "Solde declare a la creation"


def flux_de_valorisation(asset, movements):
    """L'argent entre ou sorti d'un livret, lu sur ses valorisations.

    Un livret ne fait pas de plus-value : ses interets sont calcules a part.
    Quand on recale son solde sur le releve, l'ecart avec le solde precedent
    est donc un depot ou un retrait, pas un gain. Le compter comme une
    plus-value faisait passer 458 EUR verses sur un Livret A pour une
    performance, et les laissait hors de l'epargne du mois.

    L'ecart se mesure au solde juste avant : la valorisation precedente, plus
    les interets credites et les mouvements depuis. Avant toute valorisation,
    le montant declare, sans interets inventes (voir `finance.valeur_livret`).
    Le solde pose a la creation n'est pas un flux : c'est le point de depart.
    """
    if asset["type"] not in market.RATE_ASSET_TYPES:
        return []
    # Memorise sur les donnees elles-memes : la meme cle ne peut pas donner
    # un autre resultat, donc jamais de valeur perimee. Sans cela, l'archive
    # rejouait ce calcul pour chaque mois et chaque livret.
    cle = (asset["id"], asset["valeur_acquisition"], str(asset.get("metadata")),
           asset["date_acquisition"], market.date_credit_interets(),
           tuple((m.get("id"), m["date"], m["montant"], m["type"], m.get("note"),
                  m.get("created_at")) for m in movements))
    if cle in _FLUX_MEMO:
        return _FLUX_MEMO[cle]
    if len(_FLUX_MEMO) > 2048:
        _FLUX_MEMO.clear()
    _FLUX_MEMO[cle] = _flux_de_valorisation(asset, movements)
    return _FLUX_MEMO[cle]


_FLUX_MEMO = {}


def _flux_de_valorisation(asset, movements):
    ordre = sorted(movements, key=lambda m: (
        finance.parse_date(m["date"]) or date.min, m.get("created_at") or ""))
    out = []
    for i, mv in enumerate(ordre):
        if mv["type"] != "valorisation" or (mv.get("note") or "") == NOTE_SOLDE_DECLARE:
            continue
        d = finance.parse_date(mv["date"])
        if d is None:
            continue
        avant = ordre[:i]
        if any(m["type"] == "valorisation" for m in avant):
            solde = market.rate_value(asset, avant, d)
            if solde is None:
                solde = finance.asset_value_at(asset, avant, d, use_manual_current=False)
        else:
            solde = float(asset["valeur_acquisition"] or 0) + sum(
                float(m["montant"] or 0) for m in avant
                if m["type"] in ("versement", "retrait", "frais"))
        ecart = round(float(mv["montant"] or 0) - solde, 2)
        if abs(ecart) >= 0.01:
            out.append((d, ecart))
    return out


def asset_detail(asset, movements, at_date=None, ctx=None):
    at_date = finance.parse_date(at_date) or date.today()
    is_today = at_date >= date.today()
    saisie = finance.asset_value_at(asset, movements, at_date, use_manual_current=is_today)
    invested = finance.invested_amount(asset, movements, at_date)
    # Sur un livret, ce qu'une valorisation ajoute ou retire est de l'argent
    # verse ou repris : il entre dans le capital investi, pas dans la
    # plus-value.
    invested = round(invested + sum(
        e for d, e in flux_de_valorisation(asset, movements) if d <= at_date), 2)

    # Valeur calculée, par ordre de préférence. Chaque source renvoie None si
    # elle ne peut pas produire un chiffre complet : on retombe alors sur la
    # valeur saisie, jamais sur un total partiel.
    value, source = saisie, "saisie"
    if ctx:
        live, kind = market.market_value(
            asset, movements, ctx["securities"], ctx["prices"], at_date), "marche"
        if live is None and asset["type"] in market.RATE_ASSET_TYPES:
            live, kind = market.rate_value(asset, movements, at_date), "taux"
        elif live is None and asset["type"] in market.INDEXED_ASSET_TYPES:
            live, kind = market.indexed_value(asset, at_date), "indice"
        if live is not None:
            value, source = live, kind
            # Une valeur de marche est recalculee a chaque affichage depuis les
            # cours du jour : elle ne garde AUCUNE trace d'un frais preleve il y
            # a trois mois. Sur un portefeuille crypto, enregistrer 25 EUR de
            # frais de plateforme ne changeait donc rien — ni la valeur, ni la
            # plus-value.
            #
            # C'est le capital investi qui les porte : cet argent est bien sorti
            # de votre poche pour detenir ce produit. La plus-value baisse
            # d'autant, ce qui est le resultat attendu, et durablement.
            #
            # Sur une valeur reconstituee, au contraire, le flux du frais a deja
            # fait baisser le solde : l'ajouter ici le compterait deux fois.
            invested += finance.frais_autonomes(movements, at_date)

    detail = dict(asset)
    detail["famille"] = famille_of(asset["type"])
    detail["valeur"] = value
    detail["valeur_saisie"] = saisie
    detail["valeur_source"] = source
    detail["investi"] = invested
    detail["plus_value"] = round(value - invested, 2)
    detail["plus_value_pct"] = round((value - invested) / invested, 6) if invested else None
    detail["nb_mouvements"] = len(movements)

    # Un livret n'a pas de plus-value : il a un taux et des interets a venir.
    # La plus-value reste calculee ci-dessus pour les agregats, mais c'est ce
    # bloc que la fiche affiche — un pourcentage de rendement partiel et non
    # annualise ne veut rien dire sur un produit a taux.
    if source == "taux":
        detail["taux_annuel"] = market.taux_du_produit(asset)
        detail["interets_prevus"] = market.rate_interests(asset, movements, at_date)
        detail["date_credit"] = market.date_credit_interets()
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
    for asset in cache["assets_all"]:
        if include_archived and asset["archived"]:
            acq = finance.parse_date(asset["date_acquisition"])
            if acq and acq > at_date:
                continue
        elif not present_le(asset, at_date):
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
        # Permet a l'interface de proposer « N produit(s) cloture(s) » sans
        # second appel. Le cache porte deja les deux listes : la difference
        # suffit, aucune lecture de plus.
        "nb_archives": sum(1 for a in cache["assets_all"] if a["archived"]),
        "liabilities": liabilities,
        "total_actif": total_actif,
        "total_passif": total_passif,
        "patrimoine_net": round(total_actif - total_passif, 2),
    }


def gain_annuel(at_date=None, snap=None, cache=None):
    """Plus-value acquise depuis le 1er janvier, versements exclus.

    C'est l'ecart entre la plus-value latente d'aujourd'hui et celle du
    31 decembre precedent.

    Passer par la PLUS-VALUE et non par la valeur est ce qui ecarte les
    versements de l'annee sans avoir a les recenser : un euro verse augmente la
    valeur ET le capital investi, donc laisse la plus-value inchangee. Un euro
    gagne n'augmente que la valeur.

    Un produit ouvert dans l'annee n'existe pas dans la photo de reference —
    `portfolio` ecarte les actifs acquis apres la date demandee. Toute sa
    plus-value compte donc pour l'annee, ce qui est exact.

    Attention a ce que ce chiffre NE dit PAS : une vente n'y apparait pas. Elle
    diminue la valeur et le capital investi du meme montant, donc laisse la
    plus-value inchangee. L'application ne suit que le latent.
    """
    at_date = finance.parse_date(at_date) or date.today()
    cache = shared_cache(cache)
    if snap is None:
        snap = portfolio(at_date, cache=cache)
    reference = date(at_date.year - 1, 12, 31)
    avant = portfolio(reference, cache=cache)
    # Seuls les produits encore detenus comptent des deux cotes. Un produit
    # clos dans l'annee emportait sinon sa plus-value du 31 decembre comme une
    # perte : clore n'est ni gagner ni perdre, c'est sortir.
    presents = {a["id"] for a in snap["assets"]}
    ecart = (sum(a["plus_value"] for a in snap["assets"])
             - sum(a["plus_value"] for a in avant["assets"] if a["id"] in presents))
    return {
        "montant": round(ecart, 2),
        "depuis": finance.iso(date(at_date.year, 1, 1)),
        "annee": at_date.year,
    }


def fin_du_mois_precedent(at_date):
    """Date d'arret du mois qui precede celui de `at_date`."""
    d = finance.add_months(at_date.replace(day=1), -1)
    return min(finance.month_bounds(d.year, d.month)[1], date.today())


def decomposer_variation(apres, avant):
    """D'ou vient l'ecart de patrimoine net entre deux photos.

    Quatre parts, dont la somme tombe au centime sur la variation :

    - **apports** : l'argent mis dans les produits ou repris (versements,
      retraits, produit ouvert ou clos). Ce n'est pas un enrichissement, c'est
      de l'epargne qui change de poche ;
    - **performance** : ce que les placements ont rapporte ou perdu, interets
      de livret compris. C'est l'ecart de plus-value des produits detenus des
      deux cotes ;
    - **immobilier** : la meme chose pour les biens, a part, parce qu'une
      reevaluation par indice n'est pas un gain realisable ;
    - **dettes** : le capital rembourse (positif), ou emprunte (negatif).

    Un produit ouvert compte en entier comme apport, un produit clos en
    entier comme retrait : clore n'est ni gagner ni perdre.
    """
    av = {a["id"]: a for a in avant["assets"]}
    ap = {a["id"]: a for a in apres["assets"]}
    apports = immobilier = 0.0
    for aid, a in ap.items():
        b = av.get(aid)
        if b is None:
            apports += a["valeur"]
            continue
        apports += a["investi"] - b["investi"]
        if a["famille"] == "Immobilier":
            immobilier += a["plus_value"] - b["plus_value"]
    for aid, b in av.items():
        if aid not in ap:
            apports -= b["valeur"]
    variation = round(apres["patrimoine_net"] - avant["patrimoine_net"], 2)
    dettes = round(avant["total_passif"] - apres["total_passif"], 2)
    apports, immobilier = round(apports, 2), round(immobilier, 2)
    return {
        "variation": variation,
        "apports": apports,
        # Par difference : la somme des quatre parts est exacte par
        # construction, sans residu d'arrondi a expliquer.
        "performance": round(variation - apports - immobilier - dettes, 2),
        "immobilier": immobilier,
        "dettes": dettes,
    }


def variation_du_mois(at_date, snap=None, cache=None):
    """Decomposition de la variation du net sur le mois de `at_date`."""
    cache = shared_cache(cache)
    snap = snap or portfolio(at_date, cache=cache)
    avant = portfolio(fin_du_mois_precedent(at_date), cache=cache)
    return decomposer_variation(snap, avant)


def net_worth_at(at_date):
    return portfolio(at_date)["patrimoine_net"]


def repartition(at_date=None, snap=None):
    """Répartition cible vs réelle sur les poches définies en paramètres."""
    snap = snap or portfolio(at_date)
    buckets = get_setting("repartition_cible", []) or []
    if isinstance(buckets, dict):  # ancien format {type: pct}
        buckets = [{"label": k, "types": [k], "pct": v} for k, v in buckets.items()]

    # Une poche sans type coche se reconnait a son nom : celui d'un type
    # (« PEA ») ou celui d'un de vos produits (« Livret A »). Elle ne cherchait
    # que le type, et « Livret A » restait a 0 € — ce qui faussait aussi la
    # part de toutes les autres poches.
    def contenu(bucket):
        types = set(bucket.get("types") or [])
        if types:
            return lambda a: a["type"] in types
        nom = (bucket.get("label") or "").strip().casefold()
        return lambda a: a["type"].casefold() == nom or (a.get("label") or "").strip().casefold() == nom

    couverts, out = set(), []
    for bucket in buckets:
        dedans = [a for a in snap["assets"] if contenu(bucket)(a)]
        couverts |= {a["id"] for a in dedans}
        montant = round(sum(a["valeur"] for a in dedans), 2)
        out.append({
            "label": bucket.get("label"),
            "types": sorted(set(bucket.get("types") or []) or {a["type"] for a in dedans}),
            "cible_pct": float(bucket.get("pct") or 0),
            "montant": montant,
        })
    base = round(sum(b["montant"] for b in out), 2)
    for bucket in out:
        bucket["reel_pct"] = round(100 * bucket["montant"] / base, 2) if base else 0.0
        bucket["ecart_pct"] = round(bucket["reel_pct"] - bucket["cible_pct"], 2)
        cible_montant = base * bucket["cible_pct"] / 100
        bucket["ecart_montant"] = round(bucket["montant"] - cible_montant, 2)
    hors = round(sum(a["valeur"] for a in snap["assets"] if a["id"] not in couverts), 2)
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

    cache["versements"] = _versements()
    return cache


def _versements(debut=None, fin=None):
    """Argent net mis dans les actifs (hors compte courant), date par date.

    Versements MOINS retraits : un echange de crypto passe par un retrait et
    un versement du meme montant, et seule la moitie versee etait comptee :
    50 EUR d'epargne fantome en septembre pour trois echanges. Un retrait
    reel, lui, est de l'epargne reprise.

    Les livrets y ajoutent l'argent lu sur leurs valorisations
    (`flux_de_valorisation`).
    """
    sql = ("SELECT m.montant, m.date, a.type FROM asset_movements m "
           "JOIN assets a ON a.id = m.asset_id "
           "WHERE m.type IN ('versement', 'retrait')")
    args = []
    if debut is not None:
        sql += " AND m.date >= ? AND m.date <= ?"
        args = [finance.iso(debut), finance.iso(fin)]
    out = [
        (finance.parse_date(r["date"]), round(float(r["montant"] or 0), 2))
        for r in query(sql, args)
        if r["type"] != "CompteCourant" and r["date"]
    ]
    livrets = [a for a in get_assets(True) if a["type"] in market.RATE_ASSET_TYPES]
    groupes = movements_by_asset() if livrets else {}
    for asset in livrets:
        for d, ecart in flux_de_valorisation(asset, groupes.get(asset["id"], [])):
            if debut is None or debut <= d <= fin:
                out.append((d, ecart))
    return out


def _deja_verse(t, versements, utilises, tolerance):
    """Ce virement d'epargne est-il le meme argent qu'un versement saisi ?

    Le virement vers le livret figure sur le releve, et le versement est saisi
    sur le livret : meme montant, a quelques jours pres. Les additionner
    comptait deux fois le meme euro. Chaque versement n'en couvre qu'un.
    """
    d = finance.parse_date(t["date"])
    montant = round(-t["amount"], 2)
    for i, (dv, mv) in enumerate(versements):
        if i in utilises or mv != montant or d is None:
            continue
        if abs((dv - d).days) <= tolerance:
            utilises.add(i)
            return True
    return False


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
    # plus les virements d'épargne du relevé qui ne correspondent à aucun
    # d'eux — ni par rattachement, ni par montant et date.
    tolerance = int(get_setting("transfert_jours_tolerance", 4) or 4)
    marge = timedelta(days=tolerance)
    if cache is not None:
        proches = [v for v in cache["versements"]
                   if start - marge <= v[0] <= end + marge]
    else:
        proches = _versements(start - marge, end + marge)
    versements = sum(m for d, m in proches if start <= d <= end)
    utilises = set()
    versements += sum(
        -t["amount"] for t in txs
        if t["amount"] < 0 and t["category"] in excluded and not t["asset_id"]
        and not _deja_verse(t, proches, utilises, tolerance)
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
        "taux_epargne": _taux(versements, revenus, decimales=6),
        "nb_transactions": len(txs),
        # Le detail par sens. `nb_transactions` compte TOUT le mois, depenses
        # comprises : affiche sous « Revenus du mois », il ne parlait de rien.
        "nb_revenus": sum(1 for t in txs if t["amount"] > 0 and compte(t)),
        "nb_depenses": sum(
            1 for t in txs
            if t["amount"] < 0 and compte(t) and t["category"] not in excluded),
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
    """Bornes de l'archive mensuelle : le premier mois ou il s'est passe
    quelque chose, jusqu'a aujourd'hui.

    La borne basse suivait auparavant la plus ancienne date de TOUTES les
    tables, date d'ouverture des comptes comprise. Un Livret A ouvert en 2003
    faisait donc calculer 275 mois, dont 265 sans la moindre transaction ni le
    moindre mouvement : 700 ms de calcul, et un tableau de 275 lignes que
    personne ne lit. Les valeurs de ces mois-la n'etaient d'ailleurs pas de
    l'histoire mais une reconstitution, faute d'enregistrement.

    Une archive raconte ce qui s'est passe. On part donc du premier mouvement
    d'argent reellement enregistre. Sans aucun, on retombe sur les dates
    d'ouverture : mieux vaut une archive plate qu'une archive vide.
    """
    mouvements = [
        query("SELECT MIN(date) d FROM transactions", one=True),
        query("SELECT MIN(date) d FROM asset_movements", one=True),
    ]
    dates = [finance.parse_date(r["d"]) for r in mouvements if r and r["d"]]
    if not dates:
        ouvertures = [
            query("SELECT MIN(date_acquisition) d FROM assets", one=True),
            query("SELECT MIN(date_debut) d FROM liabilities", one=True),
        ]
        dates = [finance.parse_date(r["d"]) for r in ouvertures if r and r["d"]]
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
    precedent = None
    for key in keys:
        year, month = int(key[:4]), int(key[5:])
        flows = month_flows(year, month, cache)
        _, last_day = finance.month_bounds(year, month)
        as_of = min(last_day, date.today())
        snap = portfolio(as_of, cache=cache)
        if precedent is None:
            precedent = portfolio(fin_du_mois_precedent(as_of), cache=cache)
        rep = repartition(as_of, snap)
        variation = decomposer_variation(snap, precedent)
        precedent = snap
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
            "variation": variation,
            # Montant par categorie, pour la vue categories x mois.
            "categories": {c["category"]: c["montant"] for c in flows["par_categorie"]},
            "repartition": [
                {"label": b["label"], "reel_pct": b["reel_pct"], "cible_pct": b["cible_pct"]}
                for b in rep["buckets"]
            ],
        })
    return out


# --- métriques transverses ------------------------------------------------

# Un ratio dont le dénominateur n'est pas un revenu crédible n'est pas un
# ratio : c'est du bruit affiché comme un fait. Le 1er du mois, le salaire n'est
# pas encore tombé ; diviser les mensualités d'un prêt par les quelques centimes
# d'intérêts déjà crédités donnait des milliers de pour cent.
REVENU_MINIMAL = 50.0


def _taux(numerateur, revenus, facteur=1.0, decimales=2):
    """Le taux, ou None quand le revenu ne permet pas d'en calculer un.

    Ne rien afficher est honnête ; afficher 1 500 000 % ne l'est pas.
    """
    if not revenus or revenus < REVENU_MINIMAL:
        return None
    return round(facteur * numerateur / revenus, decimales)


def avg_income(months=3, reference=None):
    """Revenu mensuel moyen des mois RÉVOLUS, hors mois en cours.

    Le taux d'endettement et la part des charges fixes décrivent une situation
    durable, pas le hasard d'un mois : ils se mesurent sur un revenu ordinaire.
    """
    reference = finance.parse_date(reference) or date.today()
    total, counted = 0.0, 0
    for i in range(1, months + 1):
        d = finance.add_months(reference, -i)
        total += month_flows(d.year, d.month)["revenus"]
        counted += 1
    return round(total / counted, 2) if counted else 0.0


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
    # Un mois à peine commencé n'a pas encore reçu son salaire. Les taux qui
    # décrivent une situation durable se mesurent donc sur les mois révolus, et
    # ne retombent sur le mois courant que faute d'historique.
    revenu_ordinaire = avg_income(3, at_date) or revenus

    # Charges fixes : ce qui tombe tous les mois quoi qu'il arrive. Le reste à
    # vivre est ce dont on dispose réellement une fois ces charges et l'épargne
    # mises de côté.
    fixes = set(get_setting("categories_charges_fixes", []) or [])
    debut, fin = finance.month_bounds(at_date.year, at_date.month)
    charges_fixes = round(sum(
        -t["amount"] for t in transactions_between(debut, fin)
        if t["amount"] < 0 and t["category"] in fixes), 2)

    frais_annee = frais_par_produit(at_date.year, snap)
    frais_total = round(sum(f["total"] for f in frais_annee), 2)

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
        # Sur les actifs et non sur le net : avec un pret, le net peut etre
        # minuscule ou negatif, et la part devenait 300 % ou moins de zero.
        "crypto_pct_actifs": (
            round(100 * crypto / snap["total_actif"], 2) if snap["total_actif"] > 0 else None),
        "immobilier_montant": immo,
        "taux_epargne_mois": flows["taux_epargne"],
        "epargne_mois": flows["epargne"],
        "revenus_mois": flows["revenus"],
        "depenses_mois": flows["depenses"],
        "mensualites_mois": mensualites,
        "taux_endettement": _taux(mensualites, revenu_ordinaire, 100),
        # La base des deux ratios en pourcentage : ils se rapportent au revenu
        # moyen des trois derniers mois revolus, pas a celui du mois affiche.
        "revenu_moyen_3m": revenu_ordinaire,
        "charges_fixes_mois": charges_fixes,
        "reste_a_vivre_mois": round(revenus - charges_fixes - flows["epargne"], 2),
        "part_charges_fixes": _taux(charges_fixes, revenu_ordinaire, 100),
        "frais_annuels": frais_total,
        # Le detail par produit, la ou il n'y avait qu'un total global.
        "frais_annuels_detail": frais_annee,
        "frais_pct_encours": (
            round(100 * frais_total / snap["total_actif"], 4) if snap["total_actif"] else None
        ),
    }


def frais_par_produit(annee, snap=None, cache=None):
    """Ce que chaque produit a coute dans l'annee.

    Il n'y avait qu'un reglage global — deux montants tapes a la main pour tout
    le patrimoine, `frais_annuels`. Rien ne rattachait un courtage au PEA qui
    l'avait paye, ni un frais de reseau au portefeuille crypto, et le total
    melangeait des couts sans rapport.

    Deux sources, et elles ne se comptent pas pareil :

    - les frais **payes**, lus sur les mouvements. Ceux portes par une
      transaction (`frais_de`) et ceux qui font mouvement a eux seuls (type
      `frais`). Ce sont des faits.
    - le **TER** d'un support, qui n'est jamais preleve : il est integre au
      cours et ne sort d'aucun compte. Aucun mouvement ne peut le porter, donc
      il reste une ESTIMATION — taux saisi sur la fiche, applique a la valeur
      du produit. Il est rendu a part pour ne pas etre confondu avec le reste.
    """
    cache = shared_cache(cache)
    if snap is None:
        snap = portfolio(date(annee, 12, 31), cache=cache)
    grouped = cache["movements"]
    out = []

    # L'ancien reglage global, s'il porte encore quelque chose. On ne sait pas a
    # quel produit ces montants appartenaient — c'est precisement le defaut
    # qu'on corrige — donc on ne leur en invente pas un. Ils sont comptes a
    # part, sous leur nom, plutot que de disparaitre en silence.
    ancien = (get_setting("frais_annuels", {}) or {}).get(str(annee), {}) or {}
    hors = round(float(ancien.get("ter", 0) or 0)
                 + float(ancien.get("courtage", 0) or 0), 2)
    if hors:
        out.append({
            "asset_id": None, "label": "Non rattaches (ancien reglage)",
            "payes": hors, "ter_estime": 0.0, "total": hors,
        })
    for asset in snap["assets"]:
        payes = 0.0
        for mv in grouped.get(asset["id"], []):
            d = finance.parse_date(mv["date"])
            if not d or d.year != annee:
                continue
            payes += finance.frais_de(mv)
            if mv["type"] == "frais":
                payes += abs(float(mv["montant"] or 0))
        taux = (asset.get("metadata") or {}).get("ter_annuel")
        try:
            ter = round(float(taux) / 100 * float(asset["valeur"] or 0), 2) if taux else 0.0
        except (TypeError, ValueError):
            ter = 0.0
        if not payes and not ter:
            continue
        out.append({
            "asset_id": asset["id"],
            "label": asset["label"],
            "payes": round(payes, 2),
            "ter_estime": ter,
            "total": round(payes + ter, 2),
        })
    return sorted(out, key=lambda f: -f["total"])


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
        for asset in cache["assets_all"]:
            trouve = presents.get(asset["id"])
            valeurs.setdefault(asset["id"], []).append(
                trouve["valeur"] if trouve else None)

    series = []
    for asset in cache["assets_all"]:
        suite = valeurs.get(asset["id"], [])
        if not any(v for v in suite):
            continue                      # jamais rien à montrer sur la période
        series.append({
            "id": asset["id"], "label": asset["label"], "type": asset["type"],
            "famille": famille_of(asset["type"]), "valeurs": suite,
        })
    series.sort(key=lambda s: -(s["valeurs"][-1] or 0))
    return {"mois": mois, "series": series}


# Un ecart ne se signale qu'au-dela de ces deux bornes : 50 % au-dessus de
# l'habitude, et au moins 50 EUR. Sans la seconde, un cafe de plus suffisait.
ECART_RELATIF = 1.5
ECART_MINIMAL = 50.0


def ecarts_du_mois(year, month, mois_reference=12):
    """Les categories nettement au-dessus de leur habitude ce mois-ci.

    L'habitude est la moyenne des douze mois precedents, comptee seulement
    depuis le debut des donnees : avant le premier releve, une categorie
    n'etait pas a zero, elle etait inconnue. C'est un constat chiffre, pas un
    conseil, comme les observations.
    """
    cache = flows_cache()
    courant = month_flows(year, month, cache)
    debut, _ = data_range()
    premier = date(debut.year, debut.month, 1)
    historique = []
    for i in range(1, mois_reference + 1):
        d = finance.add_months(date(year, month, 1), -i)
        if d < premier:
            break
        historique.append(month_flows(d.year, d.month, cache))
    if len(historique) < 3:
        return []          # trop peu de recul pour parler d'habitude
    out = []
    for c in courant["par_categorie"]:
        moyenne = sum(
            next((x["montant"] for x in h["par_categorie"]
                  if x["category"] == c["category"]), 0.0)
            for h in historique) / len(historique)
        if (c["montant"] >= ECART_RELATIF * moyenne
                and c["montant"] - moyenne >= ECART_MINIMAL):
            out.append({
                "category": c["category"],
                "montant": c["montant"],
                "habituel": round(moyenne, 2),
                "ecart": round(c["montant"] - moyenne, 2),
                "nb_mois": len(historique),
            })
    return sorted(out, key=lambda e: -e["ecart"])[:5]


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
    # Annualiser moins d'un an de detention extrapole un hasard : 19 % gagnes
    # en deux mois deviennent 327 % par an. Le TRI ne se donne qu'a partir
    # d'un an ; avant, la plus-value en pourcentage dit deja ce qui s'est passe.
    dates = [finance.parse_date(m["date"]) for m in movements
             if m["type"] in ("versement", "retrait")]
    acq = finance.parse_date(asset["date_acquisition"])
    if acq and float(asset["valeur_acquisition"] or 0) > 0:
        dates.append(acq)
    premier = min((d for d in dates if d), default=None)
    moins_d_un_an = premier is not None and (at_date - premier).days < 365
    if moins_d_un_an:
        tri = None
    lignes = (
        market.line_values(movements, ctx["securities"], ctx["prices"], at_date)
        if ctx else finance.pru_par_ligne(movements)
    )
    return {
        "pru": finance.pru(movements),
        "quantite": finance.quantity_held(movements),
        "lignes": lignes,
        "tri": tri,
        "tri_pct": round(tri * 100, 2) if tri is not None else None,
        "tri_moins_d_un_an": moins_d_un_an,
        "valeur": value,
        "valeur_source": detail["valeur_source"],
        "valeur_saisie": detail["valeur_saisie"],
        # Le meme capital investi que la liste : frais autonomes compris, et
        # borne a la date affichee.
        "investi": detail["investi"],
    }


def real_estate_detail(asset_id, at_date=None, ctx=None):
    """Prêt lié, loyers, charges et rendement locatif net d'un bien."""
    asset = get_asset(asset_id)
    if not asset:
        return None
    at_date = finance.parse_date(at_date) or date.today()
    movements = get_movements(asset_id)
    # La valeur de la liste, réévaluation par indice comprise. La fiche
    # calculait sur la valeur saisie : deux prix pour un même bien, et un
    # rendement rapporté à celui qui n'était pas affiché.
    ctx = ctx if ctx is not None else market_context(at_date)
    valeur = asset_detail(asset, movements, at_date, ctx)["valeur"]

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
