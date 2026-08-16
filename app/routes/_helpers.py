"""Conversions et raccourcis partages par les routes.

Regroupes ici parce que chaque domaine en a besoin : sans cela, la
meme conversion serait reecrite dans une dizaine de modules.
"""
from datetime import date

from flask import jsonify, request

from .. import finance


def body():
    return request.get_json(silent=True) or {}


def as_float(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=None):
    v = as_float(value, None)
    return int(v) if v is not None else default


def as_date(value, default=None):
    d = finance.parse_date(value)
    return finance.iso(d) if d else default


def fail(message, code=400):
    return jsonify({"error": message}), code


def month_param(name="month"):
    """Renvoie (annee, mois) depuis ?month=YYYY-MM, defaut = mois courant."""
    raw = request.args.get(name) or ""
    today = date.today()
    if len(raw) >= 7 and raw[4] == "-":
        try:
            return int(raw[:4]), int(raw[5:7])
        except ValueError:
            pass
    return today.year, today.month
