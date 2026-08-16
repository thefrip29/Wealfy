"""Import de releves bancaires."""
from flask import jsonify

from .. import importer, services
from ..db import execute, get_setting, new_id, query, rows_to_list
from ._blueprint import bp
from ._helpers import as_date, as_float, body, fail


@bp.post("/api/imports/preview")
def preview_import():
    data = body()
    lines, warnings = importer.parse_statement(data.get("text") or "")
    rules = rows_to_list(query("SELECT * FROM rules"))
    liabs = services.liabilities_with_summary()
    tol = float(get_setting("tolerance_mensualite", 2.0) or 2.0)
    tol_days = int(get_setting("tolerance_jours_echeance", 6) or 6)
    mots_transfert = get_setting("mots_cles_transfert", []) or []
    cat_transfert = (get_setting("categories_transfert", []) or ["Transfert interne"])[0]

    existing = {r["dedup_hash"] for r in query(
        "SELECT dedup_hash FROM transactions WHERE dedup_hash IS NOT NULL"
    )}
    seen, out, doublons = set(), [], 0
    for line in lines:
        h = importer.dedup_hash(line["date"], line["amount"], line["description"])
        duplicate = h in existing or h in seen
        seen.add(h)
        if duplicate:
            doublons += 1
        category, liability_id, origine = importer.classify(
            line, rules, liabs, tol, tol_days, mots_transfert, cat_transfert
        )
        out.append({
            **line,
            "hash": h,
            "doublon": duplicate,
            "ignore": duplicate,
            "category": category,
            "liability_id": liability_id,
            "origine": origine,
        })
    return jsonify({
        "lignes": out,
        "avertissements": warnings,
        "total": len(out),
        "doublons": doublons,
    })


@bp.post("/api/imports/confirm")
def confirm_import():
    data = body()
    lines = [l for l in (data.get("lignes") or []) if not l.get("ignore")]
    if not lines:
        return fail("Aucune ligne a importer.")
    dates = [as_date(l.get("date")) for l in lines if as_date(l.get("date"))]
    import_id = new_id()
    execute(
        "INSERT INTO imports(id, source, periode_debut, periode_fin, nombre_lignes) "
        "VALUES (?,?,?,?,?)",
        (
            import_id, (data.get("source") or "Manuel").strip(),
            min(dates) if dates else None, max(dates) if dates else None, 0,
        ),
    )
    inserted, skipped = 0, 0
    for line in lines:
        d = as_date(line.get("date"))
        amount = as_float(line.get("amount"))
        if not d or amount is None:
            skipped += 1
            continue
        description = (line.get("description") or "").strip()
        h = line.get("hash") or importer.dedup_hash(d, amount, description)
        try:
            execute(
                "INSERT INTO transactions(id, date, description, amount, category, "
                "asset_id, liability_id, import_id, dedup_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    new_id(), d, description, round(amount, 2),
                    (line.get("category") or "Non categorise").strip(),
                    line.get("asset_id") or None, line.get("liability_id") or None,
                    import_id, h,
                ),
            )
            inserted += 1
        except Exception:  # doublon rattrape par l'index unique
            skipped += 1
    execute("UPDATE imports SET nombre_lignes = ? WHERE id = ?", (inserted, import_id))
    if inserted == 0:
        execute("DELETE FROM imports WHERE id = ?", (import_id,))
    return jsonify({"ok": True, "import_id": import_id, "importees": inserted, "ignorees": skipped})


@bp.get("/api/imports")
def list_imports():
    return jsonify(rows_to_list(query("SELECT * FROM imports ORDER BY date_import DESC")))


@bp.delete("/api/imports/<iid>")
def delete_import(iid):
    """Annule un import : supprime ses transactions et la ligne de journal."""
    execute("DELETE FROM transactions WHERE import_id = ?", (iid,))
    execute("DELETE FROM imports WHERE id = ?", (iid,))
    return jsonify({"ok": True})
