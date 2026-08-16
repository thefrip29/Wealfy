"""Resolution des chemins, en execution normale comme en .exe PyInstaller.

Distinction essentielle :

- **Ressources embarquees** (templates, static, schema.sql) : dans un .exe
  --onefile, elles sont extraites dans un dossier temporaire (`sys._MEIPASS`)
  **efface a la fermeture**.
- **Donnees persistantes** (patrimoine.db, sauvegardes) : elles ne doivent
  surtout PAS atterrir dans ce dossier temporaire, sinon la base disparait a
  chaque fermeture.

En .exe, deux situations se presentent :

- **portable** — l'exe est pose dans un dossier inscriptible (Bureau, cle USB,
  dossier synchronise) : la base vit a cote de lui, tout se deplace ensemble ;
- **installe** — l'exe est dans Program Files, non inscriptible sans droits
  admin : la base va dans %LOCALAPPDATA%\\Patrimoine, ou elle survit aux
  mises a jour et aux desinstallations.

Le choix est automatique : on teste reellement l'ecriture plutot que de deviner
d'apres le chemin, car les droits Windows ne se lisent pas dans un nom de
dossier.
"""
import os
import sys

# Le logiciel s'appelle desormais Wealfy, mais le dossier de donnees garde son
# nom d'origine : le renommer rendrait invisible la base d'une installation
# existante (%LOCALAPPDATA%\Patrimoine). Un nom de dossier n'est pas une marque,
# et il ne se voit nulle part dans l'interface — le changer ne gagnerait rien et
# couterait les donnees deja en place.
APP_DIR_NAME = "Patrimoine"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts) -> str:
    """Chemin d'une ressource embarquee (lecture seule)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _is_writable(path) -> bool:
    """Le dossier accepte-t-il reellement une ecriture ?

    `os.access(..., W_OK)` ment sous Windows (UAC, virtualisation) : on ecrit
    un fichier temoin, puis on l'efface.
    """
    temoin = os.path.join(path, ".ecriture_test")
    try:
        with open(temoin, "w") as f:
            f.write("")
        os.remove(temoin)
        return True
    except OSError:
        return False


def appdata_dir() -> str:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, APP_DIR_NAME)


def data_dir() -> str:
    """Dossier des donnees persistantes. Cree s'il n'existe pas."""
    if is_frozen():
        appdata = appdata_dir()
        # `sys._MEIPASS` n'existe que dans un vrai bundle PyInstaller. Le
        # tester evite de prendre le dossier de l'interpreteur pour celui de
        # l'application quand `sys.frozen` est simule (tests).
        if not getattr(sys, "_MEIPASS", None):
            os.makedirs(appdata, exist_ok=True)
            return appdata
        pres_de_l_exe = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(os.path.join(pres_de_l_exe, "patrimoine.db")):
            # Une base est deja posee a cote de l'exe : usage portable assume.
            path = pres_de_l_exe
        elif os.path.exists(os.path.join(appdata, "patrimoine.db")):
            # Base historique : on ne repart jamais d'une base vide alors que
            # les donnees de l'utilisateur existent ailleurs.
            path = appdata
        elif _is_writable(pres_de_l_exe):
            # Premiere ouverture dans un dossier inscriptible : mode portable.
            path = pres_de_l_exe
        else:
            path = appdata
    else:
        path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(path, exist_ok=True)
    return path


def database_path() -> str:
    return os.environ.get("PATRIMOINE_DB") or os.path.join(data_dir(), "patrimoine.db")
