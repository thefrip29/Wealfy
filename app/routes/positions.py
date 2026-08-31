"""Positions detenues dans un actif : lignes de PEA, cryptos."""
from datetime import date

from flask import jsonify, request

from .. import finance, importer, market, services
from ..db import execute, get_setting, new_id, query, rows_to_list
from ._blueprint import bp
from ._helpers import as_date, as_float, body, fail


@bp.get("/api/assets/<aid>/positions")
def list_positions(aid):
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    at = as_date(request.args.get("date"), date.today().isoformat())
    ctx = services.market_context(at)
    movements = services.get_movements(aid)
    lignes = market.line_values(movements, ctx["securities"], ctx["prices"], at)
    valorisees = [l for l in lignes if l["valeur"] is not None]
    return jsonify({
        "lignes": lignes,
        "valeur_totale": round(sum(l["valeur"] for l in valorisees), 2) if valorisees else None,
        "investi_total": round(sum(l["investi"] for l in lignes), 2),
        "complet": bool(lignes) and all(l["valeur"] is not None for l in lignes),
        "kind": "crypto" if asset["type"] in market.CRYPTO_ASSET_TYPES else "titre",
    })


@bp.post("/api/assets/<aid>/swap")
def swap_position(aid):
    """Echange une ligne contre une autre, a l'interieur du meme produit.

    Un swap n'est ni un achat ni une vente : aucun euro n'entre ni ne sort du
    produit, deux lignes changent de taille. On ne pouvait donc pas l'exprimer,
    et le frais de la plateforme n'avait nulle part ou se poser.

    Deux mouvements de MEME montant, en sens inverse : le capital investi ne
    bouge pas — c'est bien le meme argent — seul le frais l'augmente. Les
    quantites, elles, suivent chaque ligne.

    Le frais est porte par l'entree, comme un courtage d'achat : il fait partie
    du prix de revient de ce que vous recevez.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    data = body()
    sortant = (data.get("de") or "").strip()
    entrant = (data.get("vers") or "").strip()
    if not sortant or not entrant:
        return fail("Indiquez la ligne de depart et celle d'arrivee.")
    if sortant == entrant:
        return fail("Les deux lignes sont identiques.")

    q_sortie = as_float(data.get("quantite_sortie"))
    q_recue = as_float(data.get("quantite_recue"))
    if not q_sortie or not q_recue:
        return fail("Indiquez les deux quantites.")

    frais = abs(as_float(data.get("frais"), 0.0) or 0.0)
    d = as_date(data.get("date"), date.today().isoformat())

    ligne = _ligne(aid, sortant)
    detenu = ligne["quantite"] if ligne else None
    if detenu is not None and q_sortie > detenu + 1e-9:
        return fail(f"Vous ne detenez que {detenu} sur cette ligne.")

    # La valeur de l'echange n'est PAS demandee : elle se deduit du prix de
    # revient de la ligne cedee.
    #
    # Un echange entre cryptos ne realise rien — ni gain ni perte, y compris au
    # sens fiscal francais, ou seule une sortie vers l'euro compte. Le prix de
    # revient est donc simplement TRANSFERE : ce que vous aviez paye pour les
    # jetons cedes devient ce que vous avez paye pour ceux recus.
    #
    # C'est aussi la seule valeur qu'on connaisse a coup sur. Un cours du jour
    # demanderait un appel reseau ou une saisie de plus, pour un chiffre qui ne
    # changerait pas votre plus-value totale.
    valeur = as_float(data.get("valeur"))
    if valeur is None or valeur <= 0:
        if not ligne or ligne.get("pru") is None:
            return fail(
                "Prix de revient inconnu sur cette ligne : indiquez la valeur "
                "de l'echange."
            )
        valeur = round(ligne["pru"] * q_sortie, 2)

    kind = "crypto" if asset["type"] in market.CRYPTO_ASSET_TYPES else "titre"
    market.upsert_security(
        entrant,
        symbol=(data.get("symbol_vers") or entrant).strip(),
        label=(data.get("label_vers") or "").strip() or None,
        currency=(data.get("currency") or "EUR").strip().upper(),
        kind=kind,
    )

    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "prix_unitaire, ticker, frais, note) VALUES (?,?,?,?,'retrait',?,?,?,0,?)",
        (new_id(), aid, d, -round(valeur, 2), abs(q_sortie),
         round(valeur / q_sortie, 8), sortant, f"Echange vers {entrant}"),
    )
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "prix_unitaire, ticker, frais, note) VALUES (?,?,?,?,'versement',?,?,?,?,?)",
        # Le prix unitaire NE contient PAS le frais : `pru_par_ligne` l'ajoute
        # deja depuis la colonne. L'inclure ici le comptait deux fois dans le
        # prix de revient.
        (new_id(), aid, d, round(valeur, 2), abs(q_recue),
         round(valeur / q_recue, 8), entrant, round(frais, 2),
         f"Echange depuis {sortant}"),
    )
    return jsonify({"ok": True, "de": sortant, "vers": entrant}), 201


def _ligne(aid, ticker):
    """Quantite et prix de revient d'une ligne, ou None si elle n'existe pas."""
    for lg in finance.pru_par_ligne(services.get_movements(aid)):
        if lg["ticker"] == ticker:
            return lg
    return None


@bp.post("/api/assets/<aid>/frais-en-nature")
def frais_en_nature(aid):
    """Frais preleves EN JETONS sur une ligne.

    Sur une plateforme crypto, la commission n'est pas debitee en euros : elle
    est prise sur les jetons. Elle reduit donc la quantite detenue, et une seule
    information suffit — combien de jetons sont partis.

    Le montant en euros n'est pas demande : il vaut ce que ces jetons avaient
    coute, c'est-a-dire leur prix de revient. Il ne sert qu'au rapport des frais.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    data = body()
    ticker = (data.get("ticker") or "").strip()
    quantite = as_float(data.get("quantite"))
    if not ticker:
        return fail("Ligne manquante.")
    if not quantite or quantite <= 0:
        return fail("Indiquez la quantite prelevee.")

    ligne = _ligne(aid, ticker)
    if ligne is None:
        return fail("Ligne introuvable.")
    if quantite > (ligne["quantite"] or 0) + 1e-9:
        return fail(f"Vous ne detenez que {ligne['quantite']} sur cette ligne.")

    montant = round((ligne.get("pru") or 0) * quantite, 2)
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "ticker, frais, note) VALUES (?,?,?,?,'frais',?,?,0,?)",
        (new_id(), aid, as_date(data.get("date"), date.today().isoformat()),
         -montant, abs(quantite), ticker, "Frais preleves en nature"),
    )
    return jsonify({"ok": True, "ticker": ticker, "montant": montant}), 201


@bp.post("/api/assets/<aid>/positions")
def add_position(aid):
    """Ajoute une ligne a un actif : mouvement + correspondance de symbole.

    C'est le point clef : choisir l'instrument cree AUSSI sa correspondance de
    cotation. L'utilisateur n'a plus a passer par les parametres.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    data = body()
    ticker = (data.get("ticker") or "").strip()
    if not ticker:
        return fail("Instrument requis.")

    # Un support non cote n'a ni quantite ni prix unitaire : un fonds euro se
    # tient en euros, pas en parts. Seul son montant compte.
    non_cote = (data.get("kind") or "").strip() == market.NON_COTE

    quantite = as_float(data.get("quantite"))
    prix = as_float(data.get("prix_unitaire"))
    montant = as_float(data.get("montant"))
    if montant is None and quantite is not None and prix is not None:
        montant = quantite * prix
    if montant is None:
        return fail("Indiquez un montant." if non_cote
                    else "Indiquez au moins une quantite et un prix unitaire.")
    if not non_cote and not quantite:
        return fail("La quantite est necessaire pour valoriser la ligne.")

    if non_cote:
        kind = market.NON_COTE
    elif asset["type"] in market.CRYPTO_ASSET_TYPES:
        kind = "crypto"
    else:
        kind = "titre"
    champs = {
        "symbol": (data.get("symbol") or ticker).strip(),
        "exchange": (data.get("exchange") or "").strip() or None,
        "currency": (data.get("currency") or "EUR").strip().upper(),
        "label": (data.get("label") or "").strip() or None,
        "isin": (data.get("isin") or "").strip() or None,
        "benchmark_symbol": (data.get("benchmark_symbol") or "").strip() or None,
        "benchmark_label": (data.get("benchmark_label") or "").strip() or None,
        "kind": kind,
    }
    # La cle n'est posee que si un taux est effectivement fourni : un simple
    # versement sur un fonds euro deja enregistre effacerait sinon son taux, et
    # la ligne repasserait silencieusement a sa valeur nominale.
    if non_cote and as_float(data.get("taux_annuel")) is not None:
        champs["taux_annuel"] = as_float(data.get("taux_annuel"))
    market.upsert_security(ticker, **champs)

    sens = (data.get("type") or "versement").strip()
    montant = abs(montant) if sens == "versement" else -abs(montant)
    # Frais payes sur cette operation : courtage d'un achat, frais de reseau
    # d'un envoi crypto. Ils n'entrent pas dans `montant` — cet argent n'est pas
    # alle dans le produit — mais gonflent le prix de revient.
    frais = abs(as_float(data.get("frais"), 0.0) or 0.0)
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "prix_unitaire, ticker, frais, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            new_id(), aid, as_date(data.get("date"), date.today().isoformat()),
            round(montant, 2), sens,
            abs(quantite) if quantite else None, prix, ticker, round(frais, 2),
            (data.get("note") or "").strip() or None,
        ),
    )
    return jsonify({"ok": True, "ticker": ticker}), 201


@bp.put("/api/assets/<aid>/positions/<ticker>/benchmark")
def set_position_benchmark(aid, ticker):
    data = body()
    market.upsert_security(
        ticker,
        benchmark_symbol=(data.get("benchmark_symbol") or "").strip() or None,
        benchmark_label=(data.get("benchmark_label") or "").strip() or None,
    )
    return jsonify({"ok": True})


@bp.get("/api/securities")
def list_securities():
    return jsonify({
        "securities": rows_to_list(query("SELECT * FROM securities ORDER BY ticker")),
        "tickers_utilises": [
            {"ticker": t, "type_actif": a} for t, a in market.known_tickers()
        ],
    })


@bp.post("/api/securities")
def upsert_security_route():
    data = body()
    ticker = (data.get("ticker") or "").strip()
    if not ticker:
        return fail("Ticker requis.")
    # `if k in data` et non la liste entiere : l'ecran de correspondance
    # n'envoie que les colonnes qu'il affiche, et les absentes repartaient a
    # NULL. Corriger une place effacait donc le nom saisi et l'ISIN, sans un mot.
    fields = {k: (data.get(k) or None) for k in (
        "symbol", "exchange", "currency", "isin", "label",
        "benchmark_symbol", "benchmark_label") if k in data}
    sid = market.upsert_security(ticker, **fields)
    return jsonify({"id": sid}), 201


@bp.delete("/api/securities/<sid>")
def delete_security(sid):
    execute("DELETE FROM securities WHERE id = ?", (sid,))
    return jsonify({"ok": True})


@bp.get("/api/assets/<aid>/benchmark")
def asset_benchmark(aid):
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    try:
        return jsonify(market.benchmark_comparison(
            asset, services.get_movements(aid), market.securities_by_ticker()))
    except market.MarketError as exc:
        return fail(str(exc))


@bp.post("/api/rules/apply")
def apply_rules_now():
    """Reclasse les transactions existantes encore non categorisees."""
    rules = rows_to_list(query("SELECT * FROM rules"))
    liabs = services.liabilities_with_summary()
    tol = float(get_setting("tolerance_mensualite", 2.0) or 2.0)
    tol_days = int(get_setting("tolerance_jours_echeance", 6) or 6)
    only_uncategorised = body().get("seulement_non_categorise", True)

    sql = "SELECT * FROM transactions"
    if only_uncategorised:
        sql += " WHERE category IN ('Non categorise', 'Autre revenu', 'Autre depense')"
    updated = 0
    for tx in rows_to_list(query(sql)):
        line = {"date": tx["date"], "description": tx["description"], "amount": tx["amount"]}
        category, liability_id, _ = importer.classify(
            line, rules, liabs, tol, tol_days)
        if category != tx["category"] or (liability_id and liability_id != tx["liability_id"]):
            execute(
                "UPDATE transactions SET category = ?, liability_id = ? WHERE id = ?",
                (category, liability_id or tx["liability_id"], tx["id"]),
            )
            updated += 1
    return jsonify({"ok": True, "modifiees": updated})
