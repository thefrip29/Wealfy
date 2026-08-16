"""Application Flask locale de gestion patrimoniale."""
from flask import Flask

from .db import close_db, init_db
from .paths import database_path, resource_path


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

    @app.after_request
    def no_cache(response):
        # Application locale mono-utilisateur : on veut toujours l'etat frais.
        if response.mimetype == "application/json":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
