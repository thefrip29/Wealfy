"""Virements internes entre actifs."""
from flask import jsonify, request

from .. import services
from ..db import get_setting
from ._blueprint import bp
from ._helpers import as_int, body, fail


@bp.get("/api/transfers/detect")
def detect_transfers():
    """Propose les paires debit/credit qui sont un meme mouvement d'argent."""
    pairs = services.find_transfer_pairs(
        days=as_int(request.args.get("jours"), None),
        month=request.args.get("month"),
    )
    return jsonify({
        "paires": pairs,
        "total": len(pairs),
        "montant_total": round(sum(p["montant"] for p in pairs), 2),
        "categorie": (get_setting("categories_transfert", []) or ["Transfert interne"])[0],
    })


@bp.post("/api/transfers/apply")
def apply_transfers():
    ids = body().get("ids") or []
    if not ids:
        return fail("Aucune transaction selectionnee.")
    updated = services.mark_as_transfer(ids, body().get("categorie"))
    return jsonify({"ok": True, "modifiees": updated})
