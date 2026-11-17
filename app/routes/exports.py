"""Export d'images : un graphique enregistre en PNG sur la machine."""
import base64
import re
import subprocess
import sys
from pathlib import Path

from flask import current_app, jsonify

from ._blueprint import bp
from ._helpers import body, fail

_PREFIXE = "data:image/png;base64,"
_MAX_OCTETS = 10 * 1024 * 1024


def dossier_export():
    """Le dossier Telechargements, ou le dossier personnel a defaut.

    L'image est ecrite par le serveur et non telechargee par la page : dans la
    fenetre Wealfy (pywebview), un lien de telechargement ne fait rien.
    """
    force = current_app.config.get("EXPORT_DIR")
    if force:
        return Path(force)
    telechargements = Path.home() / "Downloads"
    return telechargements if telechargements.is_dir() else Path.home()


@bp.post("/api/export/png")
def exporter_png():
    data = body()
    contenu = data.get("image") or ""
    if not contenu.startswith(_PREFIXE):
        return fail("Image PNG attendue.")
    try:
        octets = base64.b64decode(contenu[len(_PREFIXE):], validate=True)
    except ValueError:
        return fail("Image illisible.")
    if len(octets) > _MAX_OCTETS or not octets.startswith(b"\x89PNG"):
        return fail("Image PNG attendue.")

    # Le nom vient de la page : on n'en garde que des caracteres surs, pour
    # qu'il ne puisse pas sortir du dossier.
    nom = re.sub(r"[^\w\-]+", "-", data.get("nom") or "export").strip("-")[:80] or "export"
    dossier = dossier_export()
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.png"
    n = 2
    while chemin.exists():
        chemin = dossier / f"{nom} ({n}).png"
        n += 1
    chemin.write_bytes(octets)

    if data.get("montrer") and sys.platform == "win32":
        try:
            subprocess.Popen(["explorer", f"/select,{chemin}"])
        except OSError:
            pass
    return jsonify({"ok": True, "chemin": str(chemin), "fichier": chemin.name}), 201
