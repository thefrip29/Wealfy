"""Point d'entree unique : python run.py (ou double-clic sur Wealfy.exe).

L'application s'ouvre dans sa propre fenetre : un serveur waitress tourne sur
127.0.0.1 dans un thread de fond, et une vue WebView2 (le moteur d'Edge, deja
present sur Windows) l'affiche. L'utilisateur ne voit ni console, ni navigateur,
ni adresse — un logiciel, pas un site.

Aucune donnee ne sort de la machine : le serveur n'ecoute que sur la boucle
locale. Le seul acces reseau possible est le rafraichissement des cours de
marche, desactive par defaut.

Options :
    --browser    ouvre dans le navigateur par defaut au lieu de la fenetre
    --debug      serveur de developpement Flask, rechargement automatique
    --no-browser ne rien ouvrir du tout (tests, lancement manuel)
"""
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser

from app import create_app
from app.paths import data_dir, is_frozen, resource_path
from app.version import APP_NAME, VERSION

HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PATRIMOINE_PORT", "5000"))

# Au-dela, on considere que le serveur ne demarrera pas : mieux vaut un message
# clair qu'une fenetre blanche indefinie.
DEMARRAGE_TIMEOUT = 20.0

# Taille souhaitee, jamais imposee : elle est ramenee a ce que l'ecran peut
# afficher (voir geometrie_fenetre).
FENETRE = {"largeur": 1400, "hauteur": 900, "largeur_min": 1024, "hauteur_min": 700}
MARGE_ECRAN = 60          # air autour de la fenetre quand l'ecran est juste

# La duree de l'animation d'ouverture n'est PAS ecrite ici : splash.html expose
# `resteAnimation()`, qui lit ses propres animations CSS et repond combien de
# temps il lui reste. Une constante ici mentirait de toute facon, faute de
# savoir quand la premiere image a ete peinte.
#
# Ces deux plafonds ne sont que des securites : si la page ne repond pas (script
# casse, moteur recalcitrant), mieux vaut ouvrir l'application avec une
# animation tronquee que rester bloque sur le logo. Ils sont volontairement
# GENEREUX : une machine lente met plusieurs secondes a afficher sa premiere
# image, et c'est justement celle qu'il ne faut pas prendre de vitesse. Un
# plafond serre redeviendrait la contrainte, et l'animation serait coupee la ou
# elle l'etait deja.
SPLASH_ATTENTE_PAGE = 15.0   # delai maximal avant que la page sache repondre
SPLASH_SANS_PROGRES = 3.0    # abandon apres ce delai sans la moindre avancee
SPLASH_SONDAGE = 0.4         # on revient demander au moins tous les ...

# Fondu de sortie du splash. Doit valoir --t-fondu dans splash.html : on pose la
# classe, on laisse le fondu se jouer, puis seulement on charge l'application.
FONDU_SORTIE = 0.32


def zone_de_travail():
    """(x, y, largeur, hauteur) de l'ecran, barre des taches exclue.

    None si on ne sait pas — auquel cas on laisse pywebview se debrouiller.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wt
        rect = wt.RECT()
        # SPI_GETWORKAREA : l'ecran moins la barre des taches. Utiliser l'ecran
        # entier placerait le bas de la fenetre derriere elle.
        if not ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return None
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return None


def geometrie_fenetre():
    """Taille et position de depart : au centre, et jamais plus grand que l'ecran.

    Une fenetre plus large que l'ecran ne peut pas etre centree : Windows la
    laisse deborder, elle parait collee en haut a gauche. La taille souhaitee
    est donc bornee a la zone de travail avant tout calcul de centrage — y
    compris la taille minimale, qui sinon reimposerait le debordement.
    """
    largeur, hauteur = FENETRE["largeur"], FENETRE["hauteur"]
    mini = (FENETRE["largeur_min"], FENETRE["hauteur_min"])

    zone = zone_de_travail()
    if not zone:
        return largeur, hauteur, None, None, mini

    zx, zy, zl, zh = zone
    largeur = min(largeur, max(640, zl - MARGE_ECRAN))
    hauteur = min(hauteur, max(480, zh - MARGE_ECRAN))
    mini = (min(mini[0], largeur), min(mini[1], hauteur))
    x = zx + (zl - largeur) // 2
    y = zy + (zh - hauteur) // 2
    return largeur, hauteur, x, y, mini


class _Muet:
    """Flux de secours quand il n'y a pas de console.

    En mode --noconsole, PyInstaller met `sys.stdout` et `sys.stderr` a None :
    le moindre `print()`, y compris a l'interieur d'une bibliotheque, leve une
    AttributeError qui tue silencieusement le thread ou elle survient. Le bug
    est invisible — la fenetre reste blanche, sans le moindre message.
    """

    def write(self, _texte):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


def sorties_sures():
    if sys.stdout is None:
        sys.stdout = _Muet()
    if sys.stderr is None:
        sys.stderr = _Muet()


def journal(titre, exc):
    """Ecrit une erreur a cote de la base : sans console, c'est la seule trace."""
    try:
        chemin = os.path.join(data_dir(), "erreur.log")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} — {titre}\n")
            f.write("".join(traceback.format_exception(exc)))
        return chemin
    except OSError:
        return None


def port_occupe(port):
    """Quelqu'un ecoute-t-il deja sur ce port ?

    On teste en se CONNECTANT, jamais en se liant : sous Windows, un bind avec
    SO_REUSEADDR reussit meme sur un port deja pris — deux serveurs se
    retrouvent alors sur la meme adresse, et les requetes partent au hasard de
    l'un ou de l'autre. Avec une base SQLite unique derriere, c'est une
    corruption qui attend son heure.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(.25)
        return probe.connect_ex((HOST, port)) == 0


def free_port(preferred):
    """Renvoie le premier port reellement libre a partir du port souhaite."""
    for port in range(preferred, preferred + 20):
        if not port_occupe(port):
            return port
    return preferred


def instance_existante(port):
    """L'application tourne-t-elle deja sur ce port ? Renvoie son URL, ou None.

    On interroge /api/meta : un port occupe ne suffit pas, encore faut-il que
    ce soit bien Wealfy en face et non un autre logiciel.
    """
    if not port_occupe(port):
        return None
    import json
    import urllib.request
    url = f"http://{HOST}:{port}"
    try:
        with urllib.request.urlopen(f"{url}/api/meta", timeout=2) as reponse:
            if "asset_types" in json.loads(reponse.read().decode("utf-8")):
                return url
    except Exception:
        pass
    return None


def attendre_serveur(port, timeout=DEMARRAGE_TIMEOUT):
    """Bloque jusqu'a ce que le port accepte une connexion. True si c'est bon.

    On teste la connexion plutot que d'attendre un delai fixe : sur une machine
    lente le delai serait trop court, sur une machine rapide on ferait patienter
    pour rien.
    """
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(.25)
            if probe.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(.05)
    return False


def servir(app, port):
    """Lance waitress — serveur de production, contrairement a app.run()."""
    try:
        from waitress import serve
        # Mono-utilisateur : quelques fils suffisent, mais il en faut plus d'un,
        # sinon un import long fige toute l'interface.
        serve(app, host=HOST, port=port, threads=8)
    except Exception as exc:      # le thread meurt sans bruit : on garde la trace
        journal("Demarrage du serveur", exc)


def attendre_fin_animation(fenetre):
    """Laisse la sequence d'ouverture du splash aller a son terme.

    On INTERROGE la page — « combien de temps te reste-t-il ? » — au lieu de
    compter depuis le lancement du programme. Entre les deux il y a la creation
    de la fenetre et l'initialisation de WebView2 : souvent plus d'une seconde a
    froid, et autant d'animation coupee. C'est precisement ce que faisait la
    version precedente, avec un delai fixe qui commencait trop tot.

    La page repond `null` tant que son script n'est pas en place (trop tot pour
    savoir), un nombre de millisecondes ensuite — zero compris, cas d'un systeme
    regle sur animations reduites ou il n'y a rien a attendre.

    RIEN ICI NE DEPEND DE LA VITESSE DE LA MACHINE. Le chronometre de
    l'animation ne demarre qu'une fois la page capable de repondre : que sa
    premiere image arrive au bout d'une seconde ou de cinq, la sequence dispose
    du meme temps. Et comme on redemande apres avoir attendu, une machine qui
    aurait bloque en cours de route se voit accorder le complement.
    """
    limite_page = time.monotonic() + SPLASH_ATTENTE_PAGE
    fenetre.events.loaded.wait(SPLASH_ATTENTE_PAGE)

    reste = None
    while reste is None:
        if time.monotonic() > limite_page:
            return
        try:
            reste = fenetre.evaluate_js(
                "window.resteAnimation ? window.resteAnimation() : null")
        except Exception:
            reste = None
        if reste is None:
            time.sleep(.05)

    # On surveille la PROGRESSION, pas la duree totale. Un plafond sur la duree
    # redeviendrait la contrainte des qu'une machine peine : c'est exactement le
    # defaut qu'on vient de corriger, sous une autre forme. Tant que la page
    # annonce qu'elle avance, on l'attend, aussi longtemps qu'il faut ; on
    # n'abandonne que si plus rien ne bouge, signe d'une page figee.
    meilleur = reste
    dernier_progres = time.monotonic()
    while reste > 0:
        if time.monotonic() - dernier_progres > SPLASH_SANS_PROGRES:
            return
        # Une marge d'une image : on prefere laisser respirer la derniere image
        # plutot que de basculer pile dessus. Le sondage est borne pour repasser
        # regulierement : si la machine bloque pendant qu'on dort, il faut s'en
        # apercevoir et lui accorder le complement.
        time.sleep(min(reste / 1000 + .02, SPLASH_SONDAGE))
        try:
            reste = fenetre.evaluate_js("window.resteAnimation()")
        except Exception:
            return
        if reste is None:
            return
        if reste < meilleur - 1:          # une milliseconde de marge : le temps
            meilleur = reste             # ne recule pas, mais les flottants si
            dernier_progres = time.monotonic()


def ouvrir_fenetre(url, port):
    """Fenetre native. Renvoie False si le composant n'est pas disponible."""
    try:
        import webview
    except ImportError:
        return False

    splash = resource_path("app", "static", "splash.html")
    depart = f"file:///{splash.replace(os.sep, '/')}" if os.path.exists(splash) else url

    largeur, hauteur, x, y, mini = geometrie_fenetre()
    place = {} if x is None else {"x": x, "y": y}

    fenetre = webview.create_window(
        APP_NAME,
        depart,
        width=largeur, height=hauteur, min_size=mini,
        text_select=True,          # les montants doivent pouvoir etre copies
        **place,
    )

    def basculer():
        # Le splash reste affiche tant que le serveur ne repond pas ; des qu'il
        # repond, la fenetre charge l'application a sa place.
        if attendre_serveur(port):
            # Le serveur repond presque toujours avant que le logo ait fini de
            # se construire. Basculer a cet instant couperait l'animation en
            # plein mouvement — pire qu'une absence d'animation. On laisse la
            # sequence aller a son terme, jamais plus.
            attendre_fin_animation(fenetre)

            # Fondu de sortie : le logo s'efface avant que l'application ne
            # prenne la place, au lieu d'etre remplace d'un coup. Le fond de la
            # page reste, donc l'ecran se vide sans passer par un blanc.
            # Si evaluate_js echoue (page pas encore prete), on enchaine
            # directement : mieux vaut une bascule seche qu'un plantage.
            try:
                fenetre.evaluate_js("document.body.classList.add('sortie')")
                time.sleep(FONDU_SORTIE)
            except Exception:
                pass
            fenetre.load_url(url)
        else:
            log = os.path.join(data_dir(), "erreur.log")
            fenetre.load_html(
                "<body style='font:14px system-ui;padding:40px;line-height:1.6'>"
                "<h2>Le serveur local n'a pas démarré</h2>"
                "<p>Relancez l'application. Si le problème persiste, le détail "
                f"de l'erreur se trouve dans&nbsp;:<br><code>{log}</code></p>"
                "</body>")

    threading.Thread(target=basculer, daemon=True).start()

    icone = resource_path("app", "static", "img", "icon.ico")
    webview.start(icon=icone if os.path.exists(icone) else None)
    return True


def main():
    sorties_sures()
    debug = "--debug" in sys.argv

    # Instance unique. Deux copies du logiciel ecrivant dans la meme base
    # SQLite finissent par se marcher dessus ; on ouvre plutot une fenetre sur
    # celle qui tourne deja. En --debug on n'y touche pas : on veut justement
    # pouvoir lancer une seconde copie a cote pour comparer.
    if not debug:
        deja = instance_existante(DEFAULT_PORT)
        if deja and "--no-browser" not in sys.argv:
            if "--browser" in sys.argv or not ouvrir_fenetre(deja, DEFAULT_PORT):
                webbrowser.open(deja)
            return

    app = create_app()
    port = free_port(DEFAULT_PORT)
    url = f"http://{HOST}:{port}"

    if debug:
        # Developpement : serveur Flask au premier plan, rechargement a chaud.
        print(f"{APP_NAME} {VERSION} — debug — {url}")
        print(f"Base : {app.config['DATABASE']}")
        if "--no-browser" not in sys.argv and not os.environ.get("WERKZEUG_RUN_MAIN"):
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        app.run(host=HOST, port=port, debug=True, use_reloader=True)
        return

    threading.Thread(target=servir, args=(app, port), daemon=True).start()

    if "--no-browser" in sys.argv:
        # Aucune interface : on garde le serveur vivant au premier plan.
        print(f"{APP_NAME} {VERSION} — {url}")
        print(f"Base : {app.config['DATABASE']}")
        attendre_serveur(port)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    # Fenetre native, sauf demande explicite du navigateur. Si le composant
    # manque (installation partielle), on retombe sur le navigateur plutot que
    # de laisser l'utilisateur devant rien.
    if "--browser" in sys.argv or not ouvrir_fenetre(url, port):
        if not attendre_serveur(port):
            message = "Le serveur local n'a pas demarre."
            print(message)
            if is_frozen():
                input("Appuyez sur Entree pour fermer...")
            raise SystemExit(1)
        print(f"{APP_NAME} {VERSION} — {url}")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass

    # La fermeture de la fenetre rend la main ici : le thread du serveur est un
    # thread demon, il meurt avec le processus.


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        # Sans console, une exception au demarrage ferait disparaitre l'exe
        # sans un mot. On laisse au moins une trace sur le disque.
        chemin = journal("Demarrage de l'application", exc)
        if is_frozen():
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"{APP_NAME} n'a pas pu demarrer.\n\nDetail : {chemin}",
                    APP_NAME, 0x10)
            except Exception:
                pass
        raise
