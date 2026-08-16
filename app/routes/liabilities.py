"""Passifs : prets et dettes."""
from datetime import date

from flask import jsonify, request

from .. import finance, services
from ..db import execute, new_id
from ._blueprint import bp
from ._helpers import as_date, as_float, as_int, body, fail


@bp.get("/api/liabilities")
def list_liabilities():
    at = as_date(request.args.get("date"), date.today().isoformat())
    out = []
    for liab, summary in services.liabilities_with_summary(at):
        item = dict(liab)
        item.update(summary)
        out.append(item)
    return jsonify(out)


@bp.get("/api/liabilities/<lid>")
def liability_detail(lid):
    liab = services.get_liability(lid)
    if not liab:
        return fail("Pret introuvable.", 404)
    at = as_date(request.args.get("date"), date.today().isoformat())
    item = dict(liab)
    item.update(finance.liability_summary(liab, at))
    item["echeancier"] = finance.amortization_schedule(
        liab["montant_emprunte"], liab["taux_annuel"], liab["duree_mois"],
        liab["date_debut"], liab["assurance_mensuelle"],
    )
    item["remboursements"] = services.transactions_between(
        "1900-01-01", at, liability_id=lid
    )
    return jsonify(item)


@bp.post("/api/liabilities")
def create_liability():
    data = body()
    montant = as_float(data.get("montant_emprunte"))
    duree = as_int(data.get("duree_mois"))
    if not montant or montant <= 0:
        return fail("Montant emprunte invalide.")
    if not duree or duree <= 0:
        return fail("Duree invalide.")
    lid = new_id()
    execute(
        "INSERT INTO liabilities(id, type, label, asset_id, montant_emprunte, "
        "taux_annuel, duree_mois, date_debut, assurance_mensuelle) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            lid, (data.get("type") or "Autre").strip(),
            (data.get("label") or "").strip(), data.get("asset_id") or None,
            montant, as_float(data.get("taux_annuel"), 0.0) or 0.0, duree,
            as_date(data.get("date_debut"), date.today().isoformat()),
            as_float(data.get("assurance_mensuelle"), 0.0) or 0.0,
        ),
    )
    return jsonify({"id": lid}), 201


@bp.put("/api/liabilities/<lid>")
def update_liability(lid):
    if not services.get_liability(lid):
        return fail("Pret introuvable.", 404)
    data = body()
    fields, args = [], []
    for field in ("type", "label"):
        if field in data:
            fields.append(f"{field} = ?")
            args.append((data[field] or "").strip())
    if "asset_id" in data:
        fields.append("asset_id = ?")
        args.append(data["asset_id"] or None)
    for field in ("montant_emprunte", "taux_annuel", "assurance_mensuelle"):
        if field in data:
            fields.append(f"{field} = ?")
            args.append(as_float(data[field], 0.0) or 0.0)
    if "duree_mois" in data:
        fields.append("duree_mois = ?")
        args.append(as_int(data["duree_mois"], 0))
    if "date_debut" in data:
        fields.append("date_debut = ?")
        args.append(as_date(data["date_debut"], date.today().isoformat()))
    if not fields:
        return fail("Rien a modifier.")
    args.append(lid)
    execute(f"UPDATE liabilities SET {', '.join(fields)} WHERE id = ?", args)
    return jsonify({"ok": True})


@bp.delete("/api/liabilities/<lid>")
def delete_liability(lid):
    execute("DELETE FROM liabilities WHERE id = ?", (lid,))
    return jsonify({"ok": True})
