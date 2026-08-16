"""Sauvegardes CSV : creation, restauration, acces au dossier."""
import os
import subprocess
import sys

from flask import jsonify

from .. import backup
from ..db import get_setting
from ._blueprint import bp
from ._helpers import body, fail


@bp.get("/api/backups")
def list_backups():
    return jsonify({
        "sauvegardes": backup.list_backups(),
        "dossier": backup.backup_root(),
        "maximum": get_setting("sauvegardes_max", 30),
        "taille_totale": sum(s["taille"] for s in backup.list_backups()),
    })


@bp.post("/api/backups")
def create_backup_route():
    try:
        return jsonify(backup.create_backup(force=bool(body().get("force"))))
    except OSError as exc:
        return fail(f"Ecriture impossible : {exc}")


@bp.delete("/api/backups/<identifiant>")
def delete_backup_route(identifiant):
    if not backup.delete_backup(identifiant):
        return fail("Sauvegarde introuvable.", 404)
    return jsonify({"ok": True})


@bp.post("/api/backups/<identifiant>/restore")
def restore_backup_route(identifiant):
    """Remplace les donnees vivantes par celles de la sauvegarde.

    Irreversible : une sauvegarde de securite est prise avant, et l'interface
    demande confirmation.
    """
    try:
        return jsonify(backup.restore_backup(identifiant))
    except ValueError as exc:
        return fail(str(exc), 404)
    except Exception as exc:                      # pragma: no cover - garde-fou
        return fail(f"Restauration interrompue, donnees inchangees : {exc}")


@bp.post("/api/backups/open")
def open_backup_folder():
    """Ouvre le dossier dans l'explorateur. Confort local, sans effet ailleurs."""
    dossier = backup.backup_root()
    try:
        if sys.platform == "win32":
            os.startfile(dossier)                 # noqa: S606 - chemin maitrise
        elif sys.platform == "darwin":
            subprocess.Popen(["open", dossier])
        else:
            subprocess.Popen(["xdg-open", dossier])
    except Exception as exc:
        return fail(f"Ouverture impossible : {exc}")
    return jsonify({"ok": True, "dossier": dossier})
