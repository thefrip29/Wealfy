"""Construit Wealfy.exe puis l'installateur Windows.

    python build_exe.py              exe + installateur
    python build_exe.py --exe-seul   exe uniquement (iteration rapide)

Fait quatre choses :
  1. genere l'icone .ico multi-tailles a partir du symbole de la marque ;
  2. ecrit le fichier de version lu par Windows (proprietes du fichier) ;
  3. lance PyInstaller en mode --onefile --noconsole ;
  4. compile installer.iss avec Inno Setup -> dist/Setup_Wealfy.exe.

A relancer apres chaque modification du code : l'exe embarque une copie figee
de l'application.

Inno Setup est un prerequis, a installer une seule fois :
    winget install JRSoftware.InnoSetup
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.version import APP_NAME, DESCRIPTION, PUBLISHER, VERSION  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ROOT, "app", "static", "img", "icon.ico")
VERSION_FILE = os.path.join(ROOT, "build", "version_info.txt")
ISS_PATH = os.path.join(ROOT, "installer.iss")

# Geometrie du symbole, dans le repere 378x289 de logo-symbole.svg : le W trace
# d'un seul trait, en quatre courbes de Bezier cubiques enchainees, puis le
# point qui marque le sommet.
#
# Les memes coordonnees et les memes couleurs se retrouvent dans
# app/static/img/logo-symbole.svg, icon.svg, splash.html et templates/index.html.
# Toute retouche du logo se repercute donc ici.
COURBES = [
    ((28, 33), (21, 143), (33, 263), (88, 263)),
    ((88, 263), (138, 263), (153, 158), (178, 158)),
    ((178, 158), (205, 158), (221, 248), (258, 248)),
    ((258, 248), (295, 248), (309, 143), (328, 53)),
]
TRAIT_LARGEUR = 44
TRAIT_COULEUR = "#7D9440"
DOT = (332, 46, 42, "#DD8C10")
# Cadrage repris de icon.svg : symbole ramene a 100 de large, centre dans 128.
SYMBOLE_ECHELLE = .2646
SYMBOLE_OFFSET = (14, 25.75)
# Anthracite de la barre de navigation, hsl(210 8% 15%) : l'icone du Bureau et
# du menu Demarrer porte la meme couleur que l'application elle-meme.
BACKGROUND = "#232629"
BACKGROUND_STROKE = "#33383C"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

# Emplacements standards d'Inno Setup ; PATH teste en dernier.
ISCC_CANDIDATS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    # Installation par utilisateur : celle que pose `winget` sans elevation.
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
]


def _bezier(p0, p1, p2, p3, pas):
    """Points d'une courbe de Bezier cubique, echantillonnee regulierement."""
    for i in range(pas + 1):
        t = i / pas
        u = 1 - t
        yield (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
               u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def build_icon(size=512, supersample=4):
    """Dessine l'icone applicative : symbole de la marque sur anthracite.

    Meme anthracite que la barre de navigation de l'application : l'icone
    annonce ce qu'on va ouvrir.

    Le trait est obtenu en TAMPONNANT un disque le long de la courbe, et non
    avec un `draw.line` : Pillow ne sait pas dessiner un trace epais a bouts et
    jointures arrondis, or ce sont eux qui donnent au W son geste continu. Un
    disque a chaque point echantillonne produit exactement un `stroke-linecap:
    round` et un `stroke-linejoin: round`.

    Pillow ne lisse pas les bords : on dessine donc a `supersample` fois la
    taille demandee, puis on reduit. C'est le lissage, sans quoi les courbes
    seraient en escalier — visible des 32 px.
    """
    from PIL import Image, ImageDraw

    grand = size * supersample
    image = Image.new("RGBA", (grand, grand), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, grand - 1, grand - 1], radius=int(.22 * grand),
                           fill=BACKGROUND, outline=BACKGROUND_STROKE,
                           width=max(1, grand // 128))

    unit = grand / 128.0
    echelle = SYMBOLE_ECHELLE * unit
    off_x, off_y = SYMBOLE_OFFSET[0] * unit, SYMBOLE_OFFSET[1] * unit

    def place(x, y):
        return off_x + x * echelle, off_y + y * echelle

    def disque(centre, rayon, couleur):
        cx, cy = centre
        draw.ellipse([cx - rayon, cy - rayon, cx + rayon, cy + rayon], fill=couleur)

    rayon = TRAIT_LARGEUR / 2 * echelle
    # Assez de points pour que les disques se chevauchent largement : un pas
    # superieur au rayon laisserait le trait feston.
    for courbe in COURBES:
        for point in _bezier(*courbe, pas=320):
            disque(place(*point), rayon, TRAIT_COULEUR)

    cx, cy, r, couleur = DOT
    disque(place(cx, cy), r * echelle, couleur)

    image = image.resize((size, size), Image.LANCZOS)
    os.makedirs(os.path.dirname(ICON_PATH), exist_ok=True)
    image.save(ICON_PATH, format="ICO", sizes=[(s, s) for s in ICON_SIZES])
    print(f"Icone generee : {ICON_PATH}")


def build_version_file():
    """Metadonnees affichees par Windows dans les proprietes du .exe.

    Sans elles, l'onglet Details reste vide et l'executable a l'air anonyme —
    exactement ce qui declenche la mefiance de SmartScreen et de l'utilisateur.
    """
    majeur, mineur, correctif = (int(n) for n in VERSION.split("."))
    contenu = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({majeur}, {mineur}, {correctif}, 0),
    prodvers=({majeur}, {mineur}, {correctif}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040C04B0', [
        StringStruct('CompanyName', {PUBLISHER!r}),
        StringStruct('FileDescription', {DESCRIPTION!r}),
        StringStruct('FileVersion', {VERSION!r}),
        StringStruct('InternalName', {APP_NAME!r}),
        StringStruct('OriginalFilename', {APP_NAME + '.exe'!r}),
        StringStruct('ProductName', {APP_NAME!r}),
        StringStruct('ProductVersion', {VERSION!r}),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)
"""
    os.makedirs(os.path.dirname(VERSION_FILE), exist_ok=True)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"Version {VERSION} : {VERSION_FILE}")


def build_exe():
    sep = ";" if os.name == "nt" else ":"
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        # Plus de fenetre console noire derriere l'application.
        "--noconsole",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--version-file", VERSION_FILE,
        # Ressources embarquees : destinations alignees sur app/paths.py.
        "--add-data", f"{os.path.join('app', 'templates')}{sep}{os.path.join('app', 'templates')}",
        "--add-data", f"{os.path.join('app', 'static')}{sep}{os.path.join('app', 'static')}",
        "--add-data", f"{os.path.join('app', 'schema.sql')}{sep}app",
        # PyInstaller ne voit pas ces imports : waitress est charge par nom,
        # et pywebview choisit son moteur d'affichage a l'execution.
        "--hidden-import", "waitress",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "webview.platforms.winforms",
        "--collect-all", "webview",
        "run.py",
    ]
    print("PyInstaller :", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def trouver_iscc():
    for chemin in ISCC_CANDIDATS:
        if os.path.exists(chemin):
            return chemin
    return shutil.which("ISCC")


def build_installer():
    iscc = trouver_iscc()
    if not iscc:
        print("\nInno Setup introuvable : l'installateur n'a pas ete construit.")
        print("  winget install JRSoftware.InnoSetup")
        print(f"L'executable seul reste disponible : dist/{APP_NAME}.exe")
        return None

    subprocess.run([iscc, f"/DMyAppVersion={VERSION}", ISS_PATH],
                   cwd=ROOT, check=True)
    setup = os.path.join(ROOT, "dist", f"Setup_{APP_NAME}.exe")
    if os.path.exists(setup):
        taille = os.path.getsize(setup) / (1024 * 1024)
        print(f"\nInstallateur : {setup} ({taille:.1f} Mo)")
    return setup


if __name__ == "__main__":
    build_icon()
    build_version_file()
    build_exe()

    exe = os.path.join(ROOT, "dist", f"{APP_NAME}.exe")
    if not os.path.exists(exe):
        raise SystemExit(f"Executable introuvable : {exe}")
    print(f"Executable : {exe} ({os.path.getsize(exe) / (1024 * 1024):.1f} Mo)")

    if "--exe-seul" not in sys.argv:
        build_installer()
