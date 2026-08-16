"""Mouvements d'actifs : apports, retraits, valorisations."""
from datetime import date

from flask import jsonify

from .. import importer, market, services
from ..db import execute, new_id, query, row_to_dict
from ._blueprint import bp
from ._helpers import as_date, as_float, body, fail


@bp.get("/api/assets/<aid>/movements")
def list_movements(aid):
    return jsonify(services.get_movements(aid))


@bp.post("/api/assets/<aid>/movements")
def create_movement(aid):
    if not services.get_asset(aid):
        return fail("Actif introuvable.", 404)
    data = body()
    mtype = (data.get("type") or "versement").strip()
    if mtype not in ("versement", "retrait", "valorisation"):
        return fail("Type de mouvement inconnu.")
    montant = as_float(data.get("montant"))
    if montant is None:
        return fail("Montant invalide.")
    if mtype == "versement":
        montant = abs(montant)
    elif mtype == "retrait":
        montant = -abs(montant)
    mid = new_id()
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "prix_unitaire, ticker, note) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            mid, aid, as_date(data.get("date"), date.today().isoformat()),
            round(montant, 2), mtype,
            as_float(data.get("quantite"), None), as_float(data.get("prix_unitaire"), None),
            (data.get("ticker") or "").strip() or None,
            (data.get("note") or "").strip() or None,
        ),
    )
    return jsonify(row_to_dict(
        query("SELECT * FROM asset_movements WHERE id = ?", (mid,), one=True)
    )), 201


@bp.delete("/api/movements/<mid>")
def delete_movement(mid):
    execute("DELETE FROM asset_movements WHERE id = ?", (mid,))
    return jsonify({"ok": True})


@bp.post("/api/assets/<aid>/movements/preview")
def preview_movements(aid):
    """Previsualise un releve de titres colle (Trade Republic, courtier...).

    Marque les lignes deja presentes : un releve se reimporte souvent avec un
    chevauchement de periode, et un doublon fausserait la quantite detenue.
    """
    if not services.get_asset(aid):
        return fail("Actif introuvable.", 404)
    lines, warnings = importer.parse_movements(body().get("text") or "")

    existing = {r["dedup_hash"] for r in query(
        "SELECT dedup_hash FROM asset_movements WHERE dedup_hash IS NOT NULL"
    )}
    securities = market.securities_by_ticker()
    seen, doublons, sans_symbole = set(), 0, set()
    for line in lines:
        montant = line.get("montant")
        if montant is None and line.get("quantite") and line.get("prix_unitaire"):
            montant = line["quantite"] * line["prix_unitaire"]
        h = importer.movement_hash(
            aid, line["date"], line.get("ticker"), line.get("quantite"), montant)
        duplicate = h in existing or h in seen
        seen.add(h)
        if duplicate:
            doublons += 1
        ticker = (line.get("ticker") or "").strip()
        if ticker and not (securities.get(ticker) or {}).get("symbol"):
            sans_symbole.add(ticker)
        line["hash"] = h
        line["doublon"] = duplicate
        line["ignore"] = duplicate

    return jsonify({
        "lignes": lines,
        "avertissements": warnings,
        "total": len(lines),
        "doublons": doublons,
        "tickers_sans_symbole": sorted(sans_symbole),
    })


@bp.post("/api/assets/<aid>/movements/confirm")
def confirm_movements(aid):
    """Enregistre les mouvements d'un releve de titres.

    Les quantites detenues, le PRU et la valorisation des lignes en decoulent
    automatiquement : ils sont recalcules depuis les mouvements a chaque
    affichage, jamais stockes.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    lines = body().get("lignes") or []
    kind = "crypto" if asset["type"] in market.CRYPTO_ASSET_TYPES else "titre"
    securities = market.securities_by_ticker()

    created, ignores, mappes = 0, 0, []
    for line in lines:
        if line.get("ignore"):
            ignores += 1
            continue
        montant = as_float(line.get("montant"))
        quantite = as_float(line.get("quantite"))
        prix = as_float(line.get("prix_unitaire"))
        if montant is None and quantite is not None and prix is not None:
            montant = quantite * prix
        if montant is None:
            ignores += 1
            continue
        mtype = line.get("type") or ("retrait" if montant < 0 else "versement")
        montant = abs(montant) if mtype == "versement" else -abs(montant)
        ticker = (line.get("ticker") or "").strip() or None
        d = as_date(line.get("date"), date.today().isoformat())

        # Sans correspondance de symbole, une ligne importee reste non cotable
        # et fait retomber tout le compte sur sa valeur saisie. On l'amorce ici
        # avec le ticker du releve ; l'utilisateur l'affine si besoin.
        if ticker and not (securities.get(ticker) or {}).get("symbol"):
            market.upsert_security(ticker, symbol=ticker, kind=kind,
                                   label=(line.get("label") or "").strip() or None)
            securities = market.securities_by_ticker()
            mappes.append(ticker)

        h = line.get("hash") or importer.movement_hash(aid, d, ticker, quantite, montant)
        try:
            execute(
                "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
                "prix_unitaire, ticker, note, dedup_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    new_id(), aid, d, round(montant, 2), mtype, quantite, prix,
                    ticker, (line.get("note") or "").strip() or None, h,
                ),
            )
            created += 1
        except Exception:      # doublon rattrape par l'index unique
            ignores += 1

    return jsonify({
        "ok": True, "crees": created, "ignorees": ignores,
        "symboles_amorces": sorted(set(mappes)),
    })
