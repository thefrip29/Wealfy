"""Sauvegardes au format CSV.

Une sauvegarde = un dossier horodaté dans `sauvegarde/`, contenant un fichier
par table plus un `resume.csv` lisible tel quel dans un tableur.

Trois partis pris pour que le dossier ne gonfle pas avec le temps :

1. **La table `quotes` n'est pas sauvegardée.** C'est un cache de cours
   re-téléchargeable, et de loin la table qui grossit le plus vite — un cours
   par ligne et par jour. La sauvegarder doublerait la taille du dossier pour
   des données qui se reconstruisent d'un clic.
2. **Rien n'est réécrit si rien n'a changé.** Une empreinte du contenu est
   comparée à la dernière sauvegarde : deux sauvegardes identiques ne prennent
   pas deux fois la place.
3. **Rotation automatique.** Au-delà de `sauvegardes_max`, les plus anciennes
   sont supprimées.

Les fichiers sont écrits en UTF-8 avec BOM et séparateur point-virgule : c'est
ce qu'attend Excel en configuration française, sinon les accents et les colonnes
se mélangent à l'ouverture.
"""
import csv
import hashlib
import io
import json
import os
import shutil
from datetime import date, datetime

from . import finance
from .db import get_db, get_setting, query, rows_to_list
from .paths import data_dir

# Ordre de restauration : les tables référencées d'abord.
TABLES = [
    "assets",
    "liabilities",
    "imports",
    "asset_movements",
    "transactions",
    "rules",
    "securities",
    "settings",
]

# La clé API ne quitte pas la base : l'exporter la recopierait en clair dans
# autant de fichiers que de sauvegardes.
SETTINGS_EXCLUS = {"market_api_key"}

DELIM = ";"
ENCODAGE = "utf-8-sig"      # BOM : sans lui, Excel massacre les accents
HORODATAGE = "%Y-%m-%d_%Hh%M"


def backup_root():
    chemin = os.path.join(data_dir(), "sauvegarde")
    os.makedirs(chemin, exist_ok=True)
    return chemin


# --- lecture des tables ---------------------------------------------------

def _table_content(nom):
    """(entetes, lignes) d'une table, prête à écrire."""
    try:
        lignes = rows_to_list(query(f"SELECT * FROM {nom}"))
    except Exception:
        return [], []
    if nom == "settings":
        lignes = [l for l in lignes if l.get("key") not in SETTINGS_EXCLUS]
    if not lignes:
        return [], []
    entetes = list(lignes[0].keys())
    corps = []
    for ligne in lignes:
        corps.append([
            json.dumps(ligne[c], ensure_ascii=False) if isinstance(ligne[c], (dict, list))
            else ("" if ligne[c] is None else ligne[c])
            for c in entetes
        ])
    return entetes, corps


def _to_csv(entetes, lignes):
    tampon = io.StringIO()
    graveur = csv.writer(tampon, delimiter=DELIM, lineterminator="\n")
    if entetes:
        graveur.writerow(entetes)
    graveur.writerows(lignes)
    return tampon.getvalue()


def _resume_content():
    """Photo lisible de la situation : ce qu'on vient consulter des mois plus
    tard sans vouloir relancer l'application."""
    from . import services
    snap = services.portfolio()
    entetes = ["categorie", "libelle", "type", "valeur_eur", "investi_eur",
               "plus_value_eur", "source_de_la_valeur"]
    lignes = []
    for a in sorted(snap["assets"], key=lambda x: (x["famille"], x["label"])):
        lignes.append([a["famille"], a["label"], a["type"], a["valeur"],
                       a["investi"], a["plus_value"], a.get("valeur_source", "saisie")])
    for l in snap["liabilities"]:
        lignes.append(["Passif", l.get("label") or l["type"], l["type"],
                       -l["capital_restant"], "", "", "calcule"])
    lignes.append([])
    lignes.append(["TOTAL", "Total des actifs", "", snap["total_actif"], "", "", ""])
    lignes.append(["TOTAL", "Capital restant du", "", -snap["total_passif"], "", "", ""])
    lignes.append(["TOTAL", "Patrimoine net", "", snap["patrimoine_net"], "", "", ""])
    return entetes, lignes


# --- empreinte ------------------------------------------------------------

def _fingerprint(fichiers):
    """Empreinte du contenu, hors horodatage : deux sauvegardes identiques
    doivent être reconnues comme telles."""
    empreinte = hashlib.sha1()
    for nom in sorted(fichiers):
        if nom == "manifeste.csv":
            continue
        empreinte.update(nom.encode("utf-8"))
        empreinte.update(fichiers[nom].encode("utf-8"))
    return empreinte.hexdigest()


def _read_manifest(dossier):
    chemin = os.path.join(dossier, "manifeste.csv")
    if not os.path.exists(chemin):
        return {}
    try:
        with open(chemin, "r", encoding=ENCODAGE, newline="") as fh:
            return {r[0]: r[1] for r in csv.reader(fh, delimiter=DELIM) if len(r) >= 2}
    except OSError:
        return {}


# --- création -------------------------------------------------------------

def create_backup(force=False):
    """Écrit une sauvegarde. Ne réécrit rien si le contenu n'a pas bougé."""
    fichiers = {}
    compte = {}
    for table in TABLES:
        entetes, lignes = _table_content(table)
        compte[table] = len(lignes)
        if lignes:
            fichiers[f"{table}.csv"] = _to_csv(entetes, lignes)

    entetes, lignes = _resume_content()
    fichiers["resume.csv"] = _to_csv(entetes, lignes)

    empreinte = _fingerprint(fichiers)
    derniere = (list_backups() or [None])[0]
    if not force and derniere and derniere.get("empreinte") == empreinte:
        return {"ok": True, "inchange": True, "id": derniere["id"],
                "message": "Aucun changement depuis la dernière sauvegarde."}

    from . import services
    snap = services.portfolio()
    horodatage = datetime.now()
    dossier = os.path.join(backup_root(), horodatage.strftime(HORODATAGE))
    suffixe = 1
    while os.path.exists(dossier):
        suffixe += 1
        dossier = os.path.join(backup_root(), f"{horodatage.strftime(HORODATAGE)}-{suffixe}")
    os.makedirs(dossier)

    fichiers["manifeste.csv"] = _to_csv(
        ["cle", "valeur"],
        [["date", horodatage.isoformat(timespec="seconds")],
         ["empreinte", empreinte],
         ["patrimoine_net", snap["patrimoine_net"]],
         ["total_actif", snap["total_actif"]],
         ["total_passif", snap["total_passif"]],
         *[[f"lignes_{t}", compte.get(t, 0)] for t in TABLES]],
    )

    for nom, contenu in fichiers.items():
        with open(os.path.join(dossier, nom), "w", encoding=ENCODAGE, newline="") as fh:
            fh.write(contenu)

    # La taille se mesure AVANT la rotation : la mesurer après supposerait que
    # le dossier existe encore.
    identifiant = os.path.basename(dossier)
    taille = _dir_size(dossier)
    supprimees = _rotate(protege=identifiant)
    return {
        "ok": True, "inchange": False,
        "id": identifiant,
        "chemin": dossier,
        "taille": taille,
        "fichiers": len(fichiers),
        "anciennes_supprimees": supprimees,
    }


def _dir_size(dossier):
    total = 0
    for nom in os.listdir(dossier):
        chemin = os.path.join(dossier, nom)
        if os.path.isfile(chemin):
            total += os.path.getsize(chemin)
    return total


def _rotate(protege=None):
    """Supprime les sauvegardes au-delà du nombre conservé.

    `protege` ne peut jamais être supprimée. Sans cette garantie, deux
    sauvegardes créées dans la même seconde portent la même date : le tri
    devient ambigu et la rotation pouvait effacer celle qu'on venait tout juste
    d'écrire — l'appel suivant échouait alors sur un dossier disparu.
    """
    maxi = int(get_setting("sauvegardes_max", 30) or 30)
    if maxi <= 0:
        return []
    toutes = list_backups()
    a_garder = [b["id"] for b in toutes[:maxi]]
    if protege and protege not in a_garder:
        a_garder = [protege] + a_garder[:maxi - 1]
    trop = [b for b in toutes if b["id"] not in a_garder]
    for item in trop:
        delete_backup(item["id"])
    return [i["id"] for i in trop]


# --- inventaire -----------------------------------------------------------

def list_backups():
    """De la plus récente à la plus ancienne."""
    racine = backup_root()
    out = []
    for nom in os.listdir(racine):
        dossier = os.path.join(racine, nom)
        if not os.path.isdir(dossier):
            continue
        manifeste = _read_manifest(dossier)
        out.append({
            "id": nom,
            "date": manifeste.get("date") or datetime.fromtimestamp(
                os.path.getmtime(dossier)).isoformat(timespec="seconds"),
            "empreinte": manifeste.get("empreinte"),
            "patrimoine_net": _nombre(manifeste.get("patrimoine_net")),
            "taille": _dir_size(dossier),
            "fichiers": len([f for f in os.listdir(dossier) if f.endswith(".csv")]),
        })
    # L'identifiant départage les dates identiques : deux sauvegardes de la
    # même seconde doivent s'ordonner de façon stable, sinon la rotation
    # choisit au hasard laquelle effacer.
    return sorted(out, key=lambda x: (x["date"], x["id"]), reverse=True)


def _nombre(valeur):
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def delete_backup(identifiant):
    dossier = _safe_dir(identifiant)
    if not dossier:
        return False
    shutil.rmtree(dossier, ignore_errors=True)
    return True


def _safe_dir(identifiant):
    """Empêche de sortir du dossier de sauvegarde via un identifiant forgé."""
    if not identifiant or os.path.sep in identifiant or ".." in identifiant:
        return None
    dossier = os.path.join(backup_root(), identifiant)
    if not os.path.isdir(dossier):
        return None
    if os.path.commonpath([os.path.abspath(dossier),
                           os.path.abspath(backup_root())]) != os.path.abspath(backup_root()):
        return None
    return dossier


# --- restauration ---------------------------------------------------------

def restore_backup(identifiant):
    """Remplace le contenu de la base par celui d'une sauvegarde.

    Une sauvegarde de sécurité est prise avant toute chose : une restauration
    est irréversible sans elle.
    """
    dossier = _safe_dir(identifiant)
    if not dossier:
        raise ValueError("Sauvegarde introuvable.")

    securite = create_backup(force=True)

    con = get_db()
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        lignes_par_table = {}
        for table in TABLES:
            chemin = os.path.join(dossier, f"{table}.csv")
            if not os.path.exists(chemin):
                lignes_par_table[table] = ([], [])
                continue
            with open(chemin, "r", encoding=ENCODAGE, newline="") as fh:
                lecteur = list(csv.reader(fh, delimiter=DELIM))
            if not lecteur:
                lignes_par_table[table] = ([], [])
                continue
            lignes_par_table[table] = (lecteur[0], lecteur[1:])

        for table in reversed(TABLES):
            con.execute(f"DELETE FROM {table}")

        total = 0
        for table in TABLES:
            entetes, lignes = lignes_par_table[table]
            if not entetes or not lignes:
                continue
            colonnes = ",".join(entetes)
            marques = ",".join("?" for _ in entetes)
            for ligne in lignes:
                valeurs = [None if v == "" else v for v in ligne]
                valeurs += [None] * (len(entetes) - len(valeurs))
                con.execute(
                    f"INSERT OR REPLACE INTO {table}({colonnes}) VALUES ({marques})",
                    valeurs[:len(entetes)],
                )
                total += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")

    return {"ok": True, "lignes": total, "sauvegarde_de_securite": securite.get("id")}
