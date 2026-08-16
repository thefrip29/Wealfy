"""Actifs : comptes, placements, biens."""
import json
from datetime import date

from flask import jsonify, request

from .. import finance, services
from ..db import execute, new_id, query, row_to_dict
from ._blueprint import bp
from ._helpers import as_date, as_float, body, fail


@bp.get("/api/assets")
def list_assets():
    at = as_date(request.args.get("date"), date.today().isoformat())
    include_archived = request.args.get("archived") == "1"
    snap = services.portfolio(at, include_archived)
    return jsonify(snap)


@bp.get("/api/assets/<aid>")
def get_asset_detail(aid):
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    at = as_date(request.args.get("date"), date.today().isoformat())
    movements = services.get_movements(aid)
    ctx = services.market_context(at)
    detail = services.asset_detail(asset, movements, at, ctx)
    payload = {"asset": detail, "movements": movements}
    if asset["type"] in ("PEA", "CTO", "Crypto", "AssuranceVie", "PER"):
        payload["marche"] = services.market_asset_detail(aid, at, ctx)
    if asset["type"] in ("Immobilier", "SCPI", "Vehicule"):
        payload["immobilier"] = services.real_estate_detail(aid, at)
    payload["transactions"] = services.transactions_between(
        "1900-01-01", at, asset_id=aid
    )
    return jsonify(payload)


@bp.post("/api/assets")
def create_asset():
    data = body()
    label = (data.get("label") or "").strip()
    atype = (data.get("type") or "").strip()
    if not label:
        return fail("Le libelle est obligatoire.")
    if not atype:
        return fail("Le type est obligatoire.")
    d = as_date(data.get("date_acquisition"), date.today().isoformat())
    aid = new_id()
    execute(
        "INSERT INTO assets(id, type, label, date_acquisition, valeur_acquisition, "
        "valeur_actuelle, metadata) VALUES (?,?,?,?,?,?,?)",
        (
            aid, atype, label, d,
            as_float(data.get("valeur_acquisition"), 0.0) or 0.0,
            as_float(data.get("valeur_actuelle"), None),
            json.dumps(data.get("metadata") or {}, ensure_ascii=False),
        ),
    )
    return jsonify(row_to_dict(query("SELECT * FROM assets WHERE id = ?", (aid,), one=True))), 201


@bp.post("/api/assets/batch")
def create_assets_batch():
    """Cree plusieurs actifs d'un coup — saisie initiale du patrimoine existant.

    Pour un produit deja constitue, on ne connait pas l'historique : la valeur
    d'acquisition est posee egale au montant declare a la date de reference.
    La plus-value demarre donc a zero, ce qui est la seule chose honnete a
    afficher tant que les versements passes ne sont pas saisis.
    """
    data = body()
    reference = as_date(data.get("date"), date.today().isoformat())
    lignes = data.get("actifs") or []
    if not lignes:
        return fail("Aucun actif a creer.")

    crees, ignores = [], 0
    for ligne in lignes:
        montant = as_float(ligne.get("montant"))
        atype = (ligne.get("type") or "").strip()
        label = (ligne.get("label") or "").strip() or atype
        if montant is None or not atype:
            ignores += 1
            continue

        metadata = dict(ligne.get("metadata") or {})
        taux = as_float(ligne.get("taux_annuel"))
        if taux is not None:
            metadata["taux_annuel"] = taux

        aid = new_id()
        execute(
            "INSERT INTO assets(id, type, label, date_acquisition, valeur_acquisition, "
            "valeur_actuelle, metadata) VALUES (?,?,?,?,?,?,?)",
            (aid, atype, label, reference, round(montant, 2), round(montant, 2),
             json.dumps(metadata, ensure_ascii=False)),
        )
        crees.append({"id": aid, "label": label, "type": atype, "montant": montant})

    return jsonify({
        "ok": True, "crees": len(crees), "ignores": ignores, "actifs": crees,
        "total": round(sum(a["montant"] for a in crees), 2),
    }), 201


@bp.put("/api/assets/<aid>")
def update_asset(aid):
    if not services.get_asset(aid):
        return fail("Actif introuvable.", 404)
    data = body()
    fields, args = [], []
    for field in ("type", "label"):
        if field in data:
            fields.append(f"{field} = ?")
            args.append((data[field] or "").strip())
    if "date_acquisition" in data:
        fields.append("date_acquisition = ?")
        args.append(as_date(data["date_acquisition"], date.today().isoformat()))
    if "valeur_acquisition" in data:
        fields.append("valeur_acquisition = ?")
        args.append(as_float(data["valeur_acquisition"], 0.0) or 0.0)
    if "valeur_actuelle" in data:
        fields.append("valeur_actuelle = ?")
        args.append(as_float(data["valeur_actuelle"], None))
    if "metadata" in data:
        fields.append("metadata = ?")
        args.append(json.dumps(data["metadata"] or {}, ensure_ascii=False))
    if "archived" in data:
        fields.append("archived = ?")
        args.append(1 if data["archived"] else 0)
    if not fields:
        return fail("Rien a modifier.")
    args.append(aid)
    execute(f"UPDATE assets SET {', '.join(fields)} WHERE id = ?", args)
    return jsonify(row_to_dict(query("SELECT * FROM assets WHERE id = ?", (aid,), one=True)))


@bp.delete("/api/assets/<aid>")
def delete_asset(aid):
    execute("DELETE FROM assets WHERE id = ?", (aid,))
    return jsonify({"ok": True})


@bp.post("/api/assets/<aid>/valorisation")
def revalue_asset(aid):
    """Enregistre une valorisation datee ET met a jour la valeur actuelle.

    C'est ce qui permet a la courbe de patrimoine d'avoir un historique reel
    plutot qu'un saut au dernier point.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    data = body()
    value = as_float(data.get("valeur"))
    if value is None:
        return fail("Valeur invalide.")
    d = as_date(data.get("date"), date.today().isoformat())
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, note) "
        "VALUES (?,?,?,?,'valorisation',?)",
        (new_id(), aid, d, round(value, 2), (data.get("note") or "").strip() or None),
    )
    if finance.parse_date(d) >= date.today():
        execute("UPDATE assets SET valeur_actuelle = ? WHERE id = ?", (round(value, 2), aid))
    return jsonify({"ok": True})
