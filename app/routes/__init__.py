"""Routes HTTP, un module par domaine.

Un seul blueprint pour toute l'API : le decoupage sert la lecture du code, pas
l'adressage. Les URL n'ont donc pas bouge, et aucun prefixe n'est ajoute.

    page          la page unique et ses metadonnees
    transactions  depenses, revenus, virements
    assets        actifs (comptes, placements, biens)
    movements     apports, retraits, valorisations
    positions     lignes detenues dans un actif (PEA, cryptos)
    liabilities   prets et dettes
    bank_imports  import de releves bancaires
    analytics     synthese, historique, conseils
    quotes        cours de marche
    settings      parametres et regles de categorisation
    backups       sauvegardes CSV
    transfers     virements internes

Importer un module suffit a enregistrer ses routes : c'est le decorateur
`@bp.get`/`@bp.post` qui fait le travail, a l'import. D'ou la liste ci-dessous,
sans laquelle les routes n'existeraient tout simplement pas.
"""
from ._blueprint import bp

from . import (                                                  # noqa: F401
    analytics,
    assets,
    backups,
    bank_imports,
    liabilities,
    movements,
    page,
    positions,
    quotes,
    settings,
    transactions,
    transfers,
)

__all__ = ["bp"]
