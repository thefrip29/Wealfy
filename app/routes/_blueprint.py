"""Le blueprint, seul, dans son propre module.

Il vit ici plutot que dans `__init__.py` pour casser le cycle d'import : le
paquet importe ses modules de routes, et chacun d'eux a besoin du blueprint. En
passant par un module tiers, chaque module de route obtient `bp` sans dependre
de l'etat d'initialisation du paquet.
"""
from flask import Blueprint

bp = Blueprint("api", __name__)
