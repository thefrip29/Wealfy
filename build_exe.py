"""Construit l'artefact de distribution de la plateforme courante.

    python build_exe.py                    application + installateur
    python build_exe.py --exe-seul         application seule (iteration rapide)

Le script s'adapte au systeme sur lequel il tourne, parce qu'aucun outil ne
sait construire pour un autre : PyInstaller produit du natif, et l'image disque
comme l'installateur reposent sur des outils fournis par chaque systeme. Un
binaire macOS ne peut donc PAS etre fabrique depuis Windows — c'est le role de
l'integration continue, qui lance ce meme script sur un runner de chaque bord.

  Windows -> dist/Wealfy.exe (--onefile) puis dist/Setup_Wealfy.exe (Inno Setup)
  macOS   -> dist/Wealfy.app (--onedir)  puis dist/Wealfy-<version>-<arch>.dmg

Le dessin de l'icone est commun ; seul le format d'ecriture change (.ico et
.icns). Les metadonnees suivent la meme logique : ressource PE sous Windows,
Info.plist sous macOS.

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
# L'icone macOS n'est PAS versionnee : elle est redessinee a chaque
# construction, et n'a de sens que sur un Mac.
ICNS_PATH = os.path.join(ROOT, "build", "icon.icns")
VERSION_FILE = os.path.join(ROOT, "build", "version_info.txt")
ISS_PATH = os.path.join(ROOT, "installer.iss")
# Identifiant du bundle macOS, en notation DNS inversee. Il identifie
# l'application aupres du systeme (preferences, quarantaine, signature) et ne
# doit plus changer une fois publie.
BUNDLE_ID = "app.wealfy.desktop"

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


def dessiner_icone(size=1024, supersample=4):
    """Dessine l'icone applicative : symbole de la marque sur anthracite.

    Renvoie une image ; l'ECRITURE est laissee aux fonctions ci-dessous. Les
    deux plateformes ont besoin du meme dessin dans deux formats differents, et
    fusionner dessin et enregistrement obligerait a le refaire deux fois.

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

    return image.resize((size, size), Image.LANCZOS)


def ecrire_ico(image):
    """Icone Windows, multi-tailles dans un seul fichier."""
    os.makedirs(os.path.dirname(ICON_PATH), exist_ok=True)
    image.save(ICON_PATH, format="ICO", sizes=[(s, s) for s in ICON_SIZES])
    print(f"Icone Windows : {ICON_PATH}")
    return ICON_PATH


def ecrire_icns(image):
    """Icone macOS, via l'outil d'Apple.

    `iconutil` est fourni avec macOS et valide le jeu d'icones : il signale une
    taille manquante au lieu de produire un fichier silencieusement casse.
    L'ecriture ICNS de Pillow sert de repli, avec une fidelite moindre.

    Les variantes @2x sont les doublons en pixels de la taille au-dessus : un
    unique rendu a 1024 px suffit donc a tout produire par reduction, ce qui
    preserve le lissage que le supersampling a paye.
    """
    from PIL import Image

    os.makedirs(os.path.dirname(ICNS_PATH), exist_ok=True)
    if shutil.which("iconutil"):
        jeu = os.path.join(ROOT, "build", f"{APP_NAME}.iconset")
        shutil.rmtree(jeu, ignore_errors=True)
        os.makedirs(jeu, exist_ok=True)
        for base in (16, 32, 128, 256, 512):
            image.resize((base, base), Image.LANCZOS).save(
                os.path.join(jeu, f"icon_{base}x{base}.png"))
            image.resize((base * 2, base * 2), Image.LANCZOS).save(
                os.path.join(jeu, f"icon_{base}x{base}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", jeu, "-o", ICNS_PATH], check=True)
        shutil.rmtree(jeu, ignore_errors=True)
    else:
        image.save(ICNS_PATH, format="ICNS")
    print(f"Icone macOS : {ICNS_PATH}")
    return ICNS_PATH


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


def _donnees_embarquees():
    """Ressources a embarquer, destinations alignees sur app/paths.py.

    Le separateur source/destination differe : « ; » sous Windows, « : »
    ailleurs, parce que sous Windows « : » apparait deja dans « C: ».
    """
    sep = ";" if os.name == "nt" else ":"
    paires = [
        (os.path.join("app", "templates"), os.path.join("app", "templates")),
        (os.path.join("app", "static"), os.path.join("app", "static")),
        (os.path.join("app", "schema.sql"), "app"),
    ]
    args = []
    for source, destination in paires:
        args += ["--add-data", f"{source}{sep}{destination}"]
    return args


def construire_windows():
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        # Plus de fenetre console noire derriere l'application.
        "--noconsole",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        # Metadonnees PE : une ressource propre a Windows.
        "--version-file", VERSION_FILE,
        *_donnees_embarquees(),
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


def construire_macos():
    """Construit Wealfy.app.

    Trois choix qui ne sont pas des preferences :

    - `--onedir` et NON `--onefile`. Une application macOS est une arborescence
      (Contents/MacOS, Contents/Frameworks, Contents/Resources) : c'est la seule
      forme que comprennent Finder, Gatekeeper et les outils de signature. En
      --onefile, PyInstaller produit bien un .app, mais dont le binaire
      redecompresse une soixantaine de mega-octets a CHAQUE lancement, et qu'on
      ne pourra jamais notariser proprement.
    - `--noupx`. UPX modifie les segments Mach-O : la signature devient invalide
      et le chargeur arm64 refuse souvent le binaire.
    - pas de `--version-file`, qui n'ecrit qu'une ressource Windows. Les
      metadonnees macOS vont dans Info.plist, complete juste apres.

    `--windowed` suffit a declencher la creation du bundle : PyInstaller ajoute
    lui-meme l'etape BUNDLE quand la console est desactivee sur darwin. Aucun
    fichier .spec n'est donc necessaire.
    """
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed", "--noupx",
        "--name", APP_NAME,
        "--icon", ICNS_PATH,
        "--osx-bundle-identifier", BUNDLE_ID,
        *_donnees_embarquees(),
        "--hidden-import", "waitress",
        # Cocoa remplace les moteurs Windows. Les inclure ici ferait echouer
        # l'analyse, faute de pythonnet.
        "--hidden-import", "webview.platforms.cocoa",
        "--collect-all", "webview",
        # pyobjc resout ses liaisons a l'execution (objc.loadBundle) : l'analyse
        # statique les manque, et l'application meurt alors au lancement sur un
        # « No module named objc » que personne ne voit, --windowed masquant la
        # sortie d'erreur.
        "--collect-submodules", "objc",
        "--hidden-import", "Foundation",
        "--hidden-import", "AppKit",
        "--hidden-import", "WebKit",
        # Rien de tout cela n'existe sur un Mac : les exclure allege le bundle
        # et evite qu'une dependance fantome fasse echouer l'analyse.
        "--exclude-module", "clr",
        "--exclude-module", "pythonnet",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide6",
        "--exclude-module", "gi",
        "run.py",
    ]
    print("PyInstaller :", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)
    completer_info_plist()


def completer_info_plist():
    """Ajoute a Info.plist ce que la ligne de commande ne sait pas ecrire.

    `NSHighResolutionCapable` est le plus important : sans lui, macOS rend la
    vue web en 1x puis l'agrandit. Toute la typographie devient floue sur un
    ecran Retina, c'est-a-dire sur tous les Mac recents.
    """
    import plistlib

    chemin = os.path.join(ROOT, "dist", f"{APP_NAME}.app", "Contents", "Info.plist")
    if not os.path.exists(chemin):
        print(f"Info.plist introuvable : {chemin}")
        return
    with open(chemin, "rb") as f:
        plist = plistlib.load(f)
    plist.update({
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": f"© {PUBLISHER}",
        "LSApplicationCategoryType": "public.app-category.finance",
    })
    with open(chemin, "wb") as f:
        plistlib.dump(plist, f)
    print(f"Info.plist complete : version {VERSION}, Retina active")


def construire_dmg():
    """Image disque : le .app et un raccourci vers Applications.

    `hdiutil` suffit — pas d'outil tiers. Les scripts qui pilotent le Finder
    pour placer les icones se bloquent sur une machine sans ecran, ce qui est
    exactement le cas d'un runner d'integration continue.

    `cp -R` et non `-r` : le bundle contient quantite de liens symboliques dans
    Contents/Frameworks, et les suivre doublerait la taille tout en cassant
    l'arborescence.
    """
    import platform

    app = os.path.join(ROOT, "dist", f"{APP_NAME}.app")
    if not os.path.exists(app):
        raise SystemExit(f"Bundle introuvable : {app}")

    scene = os.path.join(ROOT, "build", "dmg")
    shutil.rmtree(scene, ignore_errors=True)
    os.makedirs(scene, exist_ok=True)
    subprocess.run(["cp", "-R", app, scene], check=True)
    os.symlink("/Applications", os.path.join(scene, "Applications"))

    dmg = os.path.join(ROOT, "dist", f"{APP_NAME}-{VERSION}-{platform.machine()}.dmg")
    subprocess.run([
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", scene,
        "-ov", "-format", "UDZO",       # compresse, lecture seule
        dmg,
    ], check=True)
    shutil.rmtree(scene, ignore_errors=True)
    taille = os.path.getsize(dmg) / (1024 * 1024)
    print(f"\nImage disque : {dmg} ({taille:.1f} Mo)")
    return dmg


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


def main():
    sans_installateur = "--exe-seul" in sys.argv or "--sans-installateur" in sys.argv
    image = dessiner_icone()

    if sys.platform == "win32":
        ecrire_ico(image)
        build_version_file()
        construire_windows()
        exe = os.path.join(ROOT, "dist", f"{APP_NAME}.exe")
        if not os.path.exists(exe):
            raise SystemExit(f"Executable introuvable : {exe}")
        print(f"Executable : {exe} ({os.path.getsize(exe) / (1024 * 1024):.1f} Mo)")
        if not sans_installateur:
            build_installer()

    elif sys.platform == "darwin":
        ecrire_icns(image)
        construire_macos()
        app = os.path.join(ROOT, "dist", f"{APP_NAME}.app")
        if not os.path.exists(app):
            raise SystemExit(f"Bundle introuvable : {app}")
        print(f"Application : {app}")
        if not sans_installateur:
            construire_dmg()

    else:
        raise SystemExit(
            f"Plateforme non prise en charge pour la construction : {sys.platform}.\n"
            "L'application FONCTIONNE sous Linux (python run.py), mais aucun\n"
            "paquet n'y est produit — il n'existe pas de format unique."
        )


if __name__ == "__main__":
    main()
