"""Parametres de l'application et regles de categorisation."""
import json

from flask import jsonify

from ..db import execute, new_id, query, rows_to_list, set_setting
from ._blueprint import bp
from ._helpers import as_int, body, fail


@bp.get("/api/settings")
def get_settings():
    rows = query("SELECT key, value FROM settings")
    out = {}
    for row in rows:
        try:
            out[row["key"]] = json.loads(row["value"])
        except (ValueError, TypeError):
            out[row["key"]] = row["value"]
    return jsonify(out)


@bp.put("/api/settings")
def put_settings():
    data = body()
    if not isinstance(data, dict) or not data:
        return fail("Corps invalide.")
    for key, value in data.items():
        set_setting(key, value)
    return jsonify({"ok": True})


@bp.get("/api/rules")
def list_rules():
    return jsonify(rows_to_list(query("SELECT * FROM rules ORDER BY priorite, pattern")))


@bp.post("/api/rules")
def create_rule():
    data = body()
    pattern = (data.get("pattern") or "").strip()
    valeur = (data.get("valeur") or "").strip()
    if not pattern or not valeur:
        return fail("Motif et valeur sont obligatoires.")
    rid = new_id()
    execute(
        "INSERT INTO rules(id, pattern, cible_type, valeur, priorite) VALUES (?,?,?,?,?)",
        (
            rid, pattern, (data.get("cible_type") or "categorie_depense").strip(),
            valeur, as_int(data.get("priorite"), 100),
        ),
    )
    return jsonify({"id": rid}), 201


@bp.put("/api/rules/<rid>")
def update_rule(rid):
    data = body()
    fields, args = [], []
    for field in ("pattern", "cible_type", "valeur"):
        if field in data:
            fields.append(f"{field} = ?")
            args.append((data[field] or "").strip())
    if "priorite" in data:
        fields.append("priorite = ?")
        args.append(as_int(data["priorite"], 100))
    if not fields:
        return fail("Rien a modifier.")
    args.append(rid)
    execute(f"UPDATE rules SET {', '.join(fields)} WHERE id = ?", args)
    return jsonify({"ok": True})


@bp.delete("/api/rules/<rid>")
def delete_rule(rid):
    execute("DELETE FROM rules WHERE id = ?", (rid,))
    return jsonify({"ok": True})
