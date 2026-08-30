"""Acces SQLite : connexion par requete, initialisation du schema, helpers."""
import json
import sqlite3
import uuid

from flask import current_app, g

from .paths import resource_path

SCHEMA_PATH = resource_path("app", "schema.sql")

DEFAULT_SETTINGS = {
    "categories_depenses": [
        "Alimentation", "Logement", "Transport", "Sante", "Loisirs",
        "Abonnements", "Restaurants", "Shopping", "Voyages", "Impots",
        "Assurances", "Frais bancaires", "Epargne/Investissement",
        "Remboursement pret", "Charges bien immobilier", "Transfert interne",
        "Autre depense",
    ],
    "categories_revenus": [
        "Salaire", "Argent parents", "Revenu locatif", "Interets",
        "Remboursement", "Autre revenu",
    ],
    # Repartition cible : buckets libres, pour pouvoir regrouper plusieurs
    # types d'actifs sous une meme poche (Livret = Livret + LDDS + LEP).
    "repartition_cible": [
        {"label": "PEA", "types": ["PEA"], "pct": 50},
        {"label": "Livret", "types": ["Livret", "LDDS", "LEP"], "pct": 30},
        {"label": "Depot a terme", "types": ["DepotTerme"], "pct": 20},
    ],
    "frais_annuels": {},
    "types_actifs_custom": [],
    # Categories qui ne comptent pas comme une depense mais comme de l'epargne
    # (virement vers un livret, versement programme sur le PEA...).
    "categories_non_depense": ["Epargne/Investissement"],
    # Categories totalement neutres : un virement LCL -> Revolut n'est ni une
    # depense, ni un revenu, ni de l'epargne. L'argent change de poche, c'est
    # tout. Exclues des DEUX cotes, sinon le meme euro serait compte en depense
    # sur un compte et en revenu sur l'autre.
    "categories_transfert": ["Transfert interne"],
    # Montant mensuel vise par categorie de depense, {categorie: montant}.
    # Le patrimoine avait ses cibles (`repartition_cible`) et l'ecart etait
    # affiche ; les depenses n'avaient rien. Vide par defaut : un budget qu'on
    # n'a pas choisi ne veut rien dire.
    "budgets_categories": {},
    # Tolerance de rapprochement automatique des paires de virements.
    "transfert_jours_tolerance": 4,
    "tolerance_mensualite": 2.0,
    "tolerance_jours_echeance": 6,
    # Nombre de sauvegardes CSV conservees ; les plus anciennes sont effacees
    # au-dela. A 30, le dossier reste de l'ordre de quelques megaoctets.
    "sauvegardes_max": 30,

    # --- Suivi patrimonial -------------------------------------------------
    # Plafonds legaux, en euros. Ils sont ici et non en dur dans le code parce
    # qu'ils changent par decret : il faut pouvoir les corriger sans toucher au
    # code. Valeurs en vigueur a la mise en place ; a verifier periodiquement.
    "plafonds_produits": {
        "Livret": 22950,
        "LDDS": 12000,
        "LEP": 10000,
        "LivretJeune": 1600,
        "PEL": 61200,
        "CEL": 15300,
        "PEA": 150000,      # plafond de VERSEMENTS, pas de valorisation
    },
    # Depenses qui tombent tous les mois quoi qu'il arrive : ce qui reste apres
    # elles est le vrai reste a vivre.
    "categories_charges_fixes": [
        "Logement", "Assurances", "Abonnements", "Remboursement pret", "Impots",
    ],
    # Jour de capitalisation des produits a taux, au format 'MM-JJ'. Le 31
    # decembre pour le Livret A, le LDDS, le LEP, le Livret Jeune, le PEL et le
    # CEL. Reglable parce qu'un depot a terme peut crediter a sa date
    # anniversaire, et parce qu'un decret peut toujours changer la regle.
    "date_credit_interets": "12-31",
    "mois_precaution_cible": 4,      # mois de depenses couverts par les livrets
    "seuil_concentration": 40,       # % des actifs financiers sur une seule ligne
    "seuil_crypto": 10,              # % du patrimoine net
    "seuil_endettement": 35,         # % des revenus (reference HCSF)

    # --- Cours de marche (V2) ---------------------------------------------
    # Desactive par defaut : tant que market_enabled est faux, l'application
    # ne fait AUCUN appel reseau et se comporte exactement comme avant.
    "market_enabled": False,
    "market_provider": "twelvedata",
    "market_api_key": "",
    "market_auto_refresh": True,
    "market_cache_ttl_hours": 24,
    "market_last_refresh": None,
    "market_last_result": None,
}

# Types d'actifs predefinis, avec leur famille pour les agregats.
ASSET_TYPES = {
    "CompteCourant": "Liquidites",
    "Livret": "Epargne reglementee",
    "LDDS": "Epargne reglementee",
    "LEP": "Epargne reglementee",
    "LivretJeune": "Epargne reglementee",
    "PEL": "Epargne reglementee",
    "CEL": "Epargne reglementee",
    "DepotTerme": "Epargne reglementee",
    "PEA": "Marches financiers",
    "CTO": "Marches financiers",
    "AssuranceVie": "Marches financiers",
    "PER": "Marches financiers",
    "SCPI": "Immobilier",
    "Immobilier": "Immobilier",
    "Crypto": "Crypto",
    "Vehicule": "Biens",
    "MaterielPro": "Biens",
    "Custom": "Autre",
}

LIABILITY_TYPES = ["PretImmobilier", "PretVehicule", "PretConso", "Autre"]


def new_id() -> str:
    return uuid.uuid4().hex


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], detect_types=0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def init_db(app):
    """Cree le schema s'il n'existe pas et injecte les settings par defaut."""
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        con.executescript(fh.read())
    existing = {r["key"] for r in con.execute("SELECT key FROM settings")}
    base_neuve = not existing
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            con.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
    # Uniquement a la toute premiere creation : une base existante recoit ses
    # regles de virement par conversion (voir `_fondre_mots_cles_dans_les_regles`),
    # et un utilisateur qui a supprime les siennes ne doit pas les voir revenir.
    if base_neuve:
        _regles_de_virement(con)
    _migrate_settings(con)
    _migrate_columns(con)
    con.commit()
    con.close()


def _migrate_columns(con):
    """Ajoute les colonnes apparues apres la creation de la base.

    `CREATE TABLE IF NOT EXISTS` ne touche pas une table deja presente : une
    colonne ajoutee au schema doit donc etre appliquee explicitement.
    """
    wanted = {
        "securities": [("kind", "TEXT NOT NULL DEFAULT 'titre'"),
                       ("taux_annuel", "REAL")],
        "asset_movements": [("dedup_hash", "TEXT")],
    }
    for table, columns in wanted.items():
        try:
            existing = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if not existing:
            continue
        for name, definition in columns:
            if name not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    # Index unique cree ici et non dans schema.sql : sur une base anterieure,
    # le script s'executerait avant l'ajout de la colonne et echouerait.
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dedup "
        "ON asset_movements(dedup_hash) WHERE dedup_hash IS NOT NULL"
    )


def _read_setting(con, key):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return None


# Motifs qui trahissent un mouvement entre les comptes de l'utilisateur.
#
# C'etait un reglage cache, `mots_cles_transfert`, avec son propre ecran et son
# propre vocabulaire — alors qu'une regle de classification fait exactement
# cela : chercher un texte dans un libelle pour attribuer une categorie. Ils
# sont donc poses comme des REGLES ordinaires, sur une base neuve : visibles
# dans le tableau des regles, modifiables et supprimables comme les autres.
MOTIFS_VIREMENT = [
    "revolut", "virement interne", "vir interne", "transfert compte",
    "topup", "top-up", "vers mon compte", "compte a compte",
]

# Priorite des regles de virement. Volontairement au-dessus de 100, la valeur
# par defaut : elles passent APRES les regles ecrites a la main, comme les
# mots-cles passaient apres elles.
PRIORITE_VIREMENT = 200


def _regles_de_virement(con):
    """Motifs de virement, en regles. Rendus vers une categorie marquee
    « virement interne » dans le tableau des roles."""
    categories = _read_setting(con, "categories_transfert")
    cible = (categories or ["Transfert interne"])[0]
    for motif in MOTIFS_VIREMENT:
        con.execute(
            "INSERT INTO rules(id, pattern, cible_type, valeur, priorite) "
            "VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, motif, "categorie_depense", cible, PRIORITE_VIREMENT),
        )


def _migrate_settings(con):
    """Ajustements sur une base creee avant l'ajout d'un reglage.

    `init_db` n'insere que les cles absentes : une liste deja stockee, elle,
    n'est jamais remplacee (on ecraserait les choix de l'utilisateur). Il faut
    donc completer explicitement ce qui doit exister.
    """
    # Toute categorie referencee ailleurs doit figurer dans la liste des
    # categories, sinon elle n'apparait pas dans les menus deroulants.
    categories = _read_setting(con, "categories_depenses")
    if not isinstance(categories, list):
        return
    manquantes = []
    for cle in ("categories_transfert", "categories_charges_fixes"):
        referencees = _read_setting(con, cle)
        if isinstance(referencees, list):
            manquantes += [c for c in referencees
                           if c not in categories and c not in manquantes]
    if manquantes:
        con.execute(
            "UPDATE settings SET value = ? WHERE key = 'categories_depenses'",
            (json.dumps(categories + manquantes, ensure_ascii=False),),
        )
    _fondre_mots_cles_dans_les_regles(con)


def _fondre_mots_cles_dans_les_regles(con):
    """Convertit `mots_cles_transfert` en regles de classification.

    Deux mecanismes cherchaient un texte dans le libelle d'une operation : les
    regles, qui attribuent une categorie, et ces mots-cles, qui marquaient un
    virement interne. Or une regle sait deja attribuer une categorie de
    virement : le second n'etait qu'un cas particulier du premier, avec son
    propre ecran et son propre vocabulaire.

    La conversion est faite une seule fois : la presence de la cle en base est
    ce qui la declenche, sa suppression ce qui l'arrete. Le reglage a donc ete
    retire de `DEFAULT_SETTINGS`, sinon `get_setting` le ressusciterait.

    Un mot deja couvert par une regle n'est pas duplique.
    """
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'mots_cles_transfert'"
    ).fetchone()
    if row is None:
        return
    try:
        mots = json.loads(row["value"])
    except (ValueError, TypeError):
        mots = []

    categories = _read_setting(con, "categories_transfert")
    cible = (categories or ["Transfert interne"])[0]
    existants = {
        (r["pattern"] or "").strip().lower()
        for r in con.execute("SELECT pattern FROM rules")
    }
    for mot in mots if isinstance(mots, list) else []:
        motif = str(mot or "").strip()
        if not motif or motif.lower() in existants:
            continue
        con.execute(
            "INSERT INTO rules(id, pattern, cible_type, valeur, priorite) "
            "VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, motif, "categorie_depense", cible,
             PRIORITE_VIREMENT),
        )
        existants.add(motif.lower())
    con.execute("DELETE FROM settings WHERE key = 'mots_cles_transfert'")


# --- settings -------------------------------------------------------------

def get_setting(key, default=None):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return DEFAULT_SETTINGS.get(key, default)


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def all_asset_types():
    """Types predefinis + types personnalises ajoutes par l'utilisateur."""
    types = [{"type": t, "famille": f, "custom": False} for t, f in ASSET_TYPES.items()]
    for custom in get_setting("types_actifs_custom", []) or []:
        if isinstance(custom, str):
            custom = {"type": custom, "famille": "Autre"}
        if custom.get("type") in ASSET_TYPES:
            continue
        types.append({
            "type": custom.get("type"),
            "famille": custom.get("famille") or "Autre",
            "custom": True,
        })
    return types


def famille_of(asset_type: str) -> str:
    if asset_type in ASSET_TYPES:
        return ASSET_TYPES[asset_type]
    for custom in get_setting("types_actifs_custom", []) or []:
        if isinstance(custom, dict) and custom.get("type") == asset_type:
            return custom.get("famille") or "Autre"
    return "Autre"


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if "metadata" in d and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (ValueError, TypeError):
            d["metadata"] = {}
    return d


def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]
