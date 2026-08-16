"""Parametres de l'application et regles de categorisation."""
import json

from flask import jsonify

from ..db import execute, new_id, query, rows_to_list, set_setting
from ._blueprint import bp
from ._helpers import as_int, body, fail


# Reglages qui ne SORTENT jamais de la base. La cle API des cours est un
# secret : la renvoyer au navigateur la rendrait lisible dans les outils de
# developpement et dans n'importe quelle capture reseau. L'interface n'a pas
# besoin de la valeur, seulement de savoir si elle est renseignee — c'est deja
# ce que fait /api/market/status avec `cle_configuree`.
CLES_SECRETES = ("market_api_key",)

# Suffixe des indicateurs qui remplacent ces valeurs dans la reponse. Ils sont
# calcules, donc jamais ecrits : les refuser en ecriture evite de creer un
# reglage fantome `market_api_key_configuree` dans la base.
SUFFIXE_INDICATEUR = "_configuree"


@bp.get("/api/settings")
def get_settings():
    rows = query("SELECT key, value FROM settings")
    out = {}
    for row in rows:
        try:
            out[row["key"]] = json.loads(row["value"])
        except (ValueError, TypeError):
            out[row["key"]] = row["value"]
    for cle in CLES_SECRETES:
        valeur = out.pop(cle, None)
        renseignee = bool(valeur.strip()) if isinstance(valeur, str) else bool(valeur)
        out[cle + SUFFIXE_INDICATEUR] = renseignee
    return jsonify(out)


@bp.put("/api/settings")
def put_settings():
    data = body()
    if not isinstance(data, dict) or not data:
        return fail("Corps invalide.")
    for key, value in data.items():
        if key.endswith(SUFFIXE_INDICATEUR):
            # Indicateur calcule renvoye tel quel par un client naif : l'ecrire
            # creerait un reglage qui ne sert a rien et que plus rien ne met a
            # jour. On l'ignore en silence plutot que d'echouer.
            continue
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
