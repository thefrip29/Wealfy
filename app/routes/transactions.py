"""Transactions : depenses, revenus, virements."""
from flask import jsonify, request

from .. import importer
from ..db import execute, new_id, query, row_to_dict, rows_to_list
from ._blueprint import bp
from ._helpers import as_date, as_float, as_int, body, fail


@bp.get("/api/transactions")
def list_transactions():
    sql = "SELECT * FROM transactions WHERE 1=1"
    args = []
    month = request.args.get("month")
    if month and len(month) >= 7:
        sql += " AND substr(date, 1, 7) = ?"
        args.append(month[:7])
    if request.args.get("from"):
        sql += " AND date >= ?"
        args.append(as_date(request.args["from"]))
    if request.args.get("to"):
        sql += " AND date <= ?"
        args.append(as_date(request.args["to"]))
    for field in ("category", "asset_id", "liability_id", "import_id"):
        if request.args.get(field):
            sql += f" AND {field} = ?"
            args.append(request.args[field])
    if request.args.get("q"):
        sql += " AND lower(description) LIKE ?"
        args.append(f"%{request.args['q'].lower()}%")
    sql += " ORDER BY date DESC, created_at DESC"
    if request.args.get("limit"):
        sql += " LIMIT ?"
        args.append(as_int(request.args["limit"], 500))
    return jsonify(rows_to_list(query(sql, args)))


@bp.post("/api/transactions")
def create_transaction():
    data = body()
    d = as_date(data.get("date"))
    amount = as_float(data.get("amount"))
    if not d:
        return fail("Date invalide.")
    if amount is None:
        return fail("Montant invalide.")
    description = (data.get("description") or "").strip()
    tid = new_id()
    execute(
        "INSERT INTO transactions(id, date, description, amount, category, asset_id, "
        "liability_id, import_id, dedup_hash) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            tid, d, description, round(amount, 2),
            (data.get("category") or "Non categorise").strip(),
            data.get("asset_id") or None, data.get("liability_id") or None, None,
            importer.dedup_hash(d, amount, description) if data.get("dedup") else None,
        ),
    )
    return jsonify(row_to_dict(
        query("SELECT * FROM transactions WHERE id = ?", (tid,), one=True)
    )), 201


@bp.put("/api/transactions/<tid>")
def update_transaction(tid):
    existing = query("SELECT * FROM transactions WHERE id = ?", (tid,), one=True)
    if not existing:
        return fail("Transaction introuvable.", 404)
    data = body()
    fields, args = [], []
    if "date" in data:
        d = as_date(data["date"])
        if not d:
            return fail("Date invalide.")
        fields.append("date = ?")
        args.append(d)
    if "description" in data:
        fields.append("description = ?")
        args.append((data["description"] or "").strip())
    if "amount" in data:
        amount = as_float(data["amount"])
        if amount is None:
            return fail("Montant invalide.")
        fields.append("amount = ?")
        args.append(round(amount, 2))
    if "category" in data:
        fields.append("category = ?")
        args.append((data["category"] or "Non categorise").strip())
    for field in ("asset_id", "liability_id"):
        if field in data:
            fields.append(f"{field} = ?")
            args.append(data[field] or None)
    if not fields:
        return fail("Rien a modifier.")
    args.append(tid)
    execute(f"UPDATE transactions SET {', '.join(fields)} WHERE id = ?", args)
    return jsonify(row_to_dict(
        query("SELECT * FROM transactions WHERE id = ?", (tid,), one=True)
    ))


@bp.delete("/api/transactions/<tid>")
def delete_transaction(tid):
    execute("DELETE FROM transactions WHERE id = ?", (tid,))
    return jsonify({"ok": True})
