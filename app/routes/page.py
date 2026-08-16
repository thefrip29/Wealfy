"""Page unique et metadonnees de demarrage."""
from datetime import date

from flask import jsonify, render_template

from ..db import LIABILITY_TYPES, all_asset_types, get_setting
from ..version import VERSION
from ._blueprint import bp


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/meta")
def meta():
    return jsonify({
        "today": date.today().isoformat(),
        "version": VERSION,
        "asset_types": all_asset_types(),
        "liability_types": LIABILITY_TYPES,
        "categories_depenses": get_setting("categories_depenses"),
        "categories_revenus": get_setting("categories_revenus"),
        "categories_non_depense": get_setting("categories_non_depense"),
    })
