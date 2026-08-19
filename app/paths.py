"""Resolution des chemins, en execution normale comme en .exe PyInstaller.

Distinction essentielle :

- **Ressources embarquees** (templates, static, schema.sql) : dans un .exe
  --onefile, elles sont extraites dans un dossier temporaire (`sys._MEIPASS`)
  **efface a la fermeture**.
- **Donnees persistantes** (patrimoine.db, sauvegardes) : elles ne doivent
  surtout PAS atterrir dans ce dossier temporaire, sinon la base disparait a
  chaque fermeture.

En .exe, la base va par defaut dans le dossier de donnees de l'utilisateur
(%LOCALAPPDATA%\\Patrimoine, ~/Library/Application Support/Wealfy,
~/.local/share/wealfy), ou elle survit aux mises a jour et aux desinstallations.

Le mode **portable**, ou la base vit a cote de l'executable pour tout deplacer
ensemble sur une cle USB, se DEMANDE en posant un fichier `portable.txt` a cote
de l'exe. Il ne se declenche plus tout seul : voir MARQUEUR_PORTABLE.
"""
import os
import sys

# Le logiciel s'appelle desormais Wealfy, mais le dossier de donnees garde son
# nom d'origine SOUS WINDOWS : le renommer rendrait invisible la base d'une
# installation existante (%LOCALAPPDATA%\Patrimoine). Un nom de dossier n'est
# pas une marque, et il ne se voit nulle part dans l'interface — le changer ne
# gagnerait rien et couterait les donnees deja en place.
APP_DIR_NAME = "Patrimoine"

# macOS et Linux n'ont aucune installation existante a menager : le nom actuel
# du logiciel y est donc utilise directement.
APP_DIR_NAME_UNIX = "Wealfy"

# Fichier temoin qui reclame le mode portable : la base vit alors a cote de
# l'executable, et tout se deplace ensemble sur une cle USB.
#
# Il FAUT le demander. Auparavant le mode portable se declenchait tout seul des
# que le dossier de l'exe etait inscriptible, ce qui est le cas du dossier des
# telechargements : la base atterrissait la, et la version suivante lancee
# depuis un autre dossier repartait d'une base vide. L'utilisateur y voyait une
# perte de ses reglages, alors que ses donnees etaient intactes quelques
# dossiers plus loin.
#
# Le filet %LOCALAPPDATA% n'aidait pas : il n'est consulte que si une base s'y
# trouve deja, or en mode portable il ne s'en cree jamais.
MARQUEUR_PORTABLE = "portable.txt"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts) -> str:
    """Chemin d'une ressource embarquee (lecture seule)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def appdata_dir() -> str:
    """Dossier de donnees de l'utilisateur, selon l'usage de chaque systeme.

    Chaque plateforme a sa convention, et s'en ecarter donne un dossier que
    l'utilisateur ne trouvera pas et que les outils de sauvegarde du systeme
    n'iront pas chercher. Sur macOS, se rabattre sur `~` comme le faisait la
    version precedente deposerait un dossier nu dans le repertoire personnel.
    """
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", APP_DIR_NAME_UNIX)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(root, APP_DIR_NAME)
    # Linux et le reste : specification XDG.
    root = (os.environ.get("XDG_DATA_HOME")
            or os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(root, APP_DIR_NAME_UNIX.lower())


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
        # Le mode PORTABLE est propre a Windows, ou l'executable est un fichier
        # qu'on pose ou l'on veut. Ailleurs, l'application est un bundle
        # (Wealfy.app/Contents/MacOS/) ou un paquet installe : « a cote de
        # l'executable » designe l'interieur du bundle. Y ecrire invaliderait
        # sa signature, et les donnees disparaitraient a la mise a jour
        # suivante, quand le bundle entier est remplace.
        if sys.platform != "win32":
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
        elif os.path.exists(os.path.join(pres_de_l_exe, MARQUEUR_PORTABLE)):
            # Mode portable DEMANDE : un fichier temoin pose a cote de l'exe.
            path = pres_de_l_exe
        else:
            path = appdata
    else:
        path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(path, exist_ok=True)
    return path


def database_path() -> str:
    return os.environ.get("PATRIMOINE_DB") or os.path.join(data_dir(), "patrimoine.db")
