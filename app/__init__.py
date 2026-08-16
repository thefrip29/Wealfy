"""Application Flask locale de gestion patrimoniale."""
from flask import Flask, jsonify, request

from .db import close_db, init_db
from .paths import database_path, resource_path

# Seuls noms d'hote acceptes. Le serveur n'ecoute que sur la boucle locale, mais
# « ecouter sur 127.0.0.1 » ne protege PAS de tout :
#
# - DNS rebinding : un site malveillant fait pointer son propre domaine vers
#   127.0.0.1. Le navigateur considere alors ses requetes comme de meme origine
#   et peut LIRE la reponse — donc toute la base. La seule parade est de
#   verifier l'en-tete Host, que l'attaquant ne controle pas ;
# - CSRF : une page tierce declenche une action mutante sans lire la reponse.
#   D'ou le controle de l'en-tete Origin plus bas.
#
# Le PORT n'est volontairement pas verifie : run.py en choisit un autre si le
# port souhaite est pris, et un port n'a jamais protege de rien.
HOTES_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1"})


def _hote_seul(valeur):
    """Nom d'hote sans le port. Gere la forme IPv6 entre crochets."""
    if not valeur:
        return ""
    valeur = valeur.strip()
    if valeur.startswith("["):                      # [::1]:5000
        fin = valeur.find("]")
        return valeur[1:fin] if fin > 0 else valeur
    return valeur.rsplit(":", 1)[0] if ":" in valeur else valeur


def create_app(database=None):
    # Chemins explicites : sous PyInstaller, Flask ne retrouve pas seul ses
    # dossiers templates/ et static/ extraits dans le dossier temporaire.
    app = Flask(
        __name__,
        static_folder=resource_path("app", "static"),
        template_folder=resource_path("app", "templates"),
    )
    app.config["DATABASE"] = database or database_path()
    app.config["JSON_SORT_KEYS"] = False
    # Application locale : pas de cache navigateur sur les fichiers statiques,
    # une modification du CSS ou du JS est visible au rechargement.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.json.ensure_ascii = False

    init_db(app)
    app.teardown_appcontext(close_db)

    from .routes import bp
    app.register_blueprint(bp)

    @app.before_request
    def refuser_origine_etrangere():
        """Barriere d'entree : d'ou vient cette requete, vraiment ?

        Deux verifications, dans cet ordre. L'en-tete Host dit sous quel nom le
        client a joint le serveur : s'il ne s'agit pas de la boucle locale, la
        requete a transite par un nom de domaine, donc par le DNS — exactement
        le scenario du rebinding. L'en-tete Origin, lui, dit quelle page a
        declenche la requete ; le navigateur l'ajoute et le site ne peut pas le
        falsifier. Absent, c'est une requete hors navigateur (curl, le sondage
        de run.py) : rien a comparer, on laisse passer, puisque le Host a deja
        ete verifie.
        """
        if _hote_seul(request.host) not in HOTES_LOCAUX:
            return jsonify({"error": "Hote non autorise."}), 403
        origine = request.headers.get("Origin")
        if origine and _hote_seul(origine.split("//", 1)[-1]) not in HOTES_LOCAUX:
            return jsonify({"error": "Origine non autorisee."}), 403
        return None

    @app.after_request
    def no_cache(response):
        # Application locale mono-utilisateur : on veut toujours l'etat frais.
        if response.mimetype == "application/json":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
