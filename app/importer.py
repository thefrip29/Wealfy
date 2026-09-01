"""Parsing des relevés collés (CSV Revolut, texte LCL formaté, TSV...),
déduplication et classification automatique.

Le parseur est volontairement tolérant : il détecte le séparateur, reconnaît
les en-têtes usuels (FR/EN), gère les colonnes débit/crédit séparées et les
montants au format français ou anglo-saxon.
"""
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, timedelta

from .finance import add_months, iso, parse_date

DELIMITERS = [",", ";", "\t", "|"]

DATE_HEADERS = [
    "completed date", "started date", "date operation", "date de l operation",
    "date valeur", "date comptable", "date", "transaction date", "booking date",
]
DESC_HEADERS = [
    "description", "libelle", "libelle operation", "libelle simplifie", "intitule",
    "nature", "detail", "merchant", "payee", "reference", "motif",
]
AMOUNT_HEADERS = [
    "amount", "montant", "montant eur", "montant operation", "valeur", "somme",
]
DEBIT_HEADERS = ["debit", "depense", "retrait", "sortie", "montant debit"]
CREDIT_HEADERS = ["credit", "recette", "depot", "entree", "montant credit"]
FEE_HEADERS = ["fee", "frais", "commission"]
STATE_HEADERS = ["state", "statut", "status"]
CURRENCY_HEADERS = ["currency", "devise"]

# Mots-clés par défaut : ne sert que de filet quand aucune règle utilisateur
# ne correspond. Les règles de la table `rules` restent prioritaires.
#
# Cette liste était strictement française. Mesurée sur un relevé réel de 197
# opérations — un compte utilisé à l'étranger — elle en reconnaissait NEUF.
# Un relevé ordinaire est plein de marchands internationaux et de libellés
# anglais ; les ignorer laissait 95 % des lignes sans catégorie.
DEFAULT_KEYWORDS = {
    "Alimentation": ["carrefour", "leclerc", "lidl", "auchan", "intermarche", "super u",
                     "monoprix", "franprix", "casino", "biocoop", "picard", "aldi",
                     "spar", "coop", "tesco", "mercadona", "delhaize", "colruyt",
                     "migros", "seven eleven", "familymart", "indomaret", "alfamart",
                     "supermarket", "grocery", "epicerie", "primeur",
                     "super mart", "supermart", "mart", "mini market",
                     "minimart", "7 eleven", "convenience store"],
    "Restaurants": ["restaurant", "mcdonald", "burger", "uber eats", "deliveroo",
                    "just eat", "boulangerie", "starbucks", "kebab", "sushi", "brasserie",
                    "grabfood", "foodpanda", "doordash", "glovo", "wolt", "subway",
                    "dominos", "pizza", "bistrot", "taverne", "cafeteria", "coffee",
                    "warung", "trattoria", "creperie", "cafe", "noodle", "bakery",
                    "eatery", "canteen", "grill", "bistro", "resto"],
    "Transport": ["sncf", "ratp", "uber", "total", "totalenergies", "esso", "shell",
                  "bp", "essence", "peage", "vinci autoroute", "blablacar", "parking",
                  "velib", "navigo", "tan", "tcl", "carburant",
                  "grab", "bolt", "gojek", "lyft", "cabify", "freenow", "flixbus",
                  "redbus", "12go", "taxi", "metro", "tramway", "autocar",
                  "sixt", "hertz", "europcar", "trainline", "car rental",
                  "rent a car", "location voiture"],
    "Voyages": ["booking", "airbnb", "ryanair", "easyjet", "air france", "hotel",
                "agoda", "hostelworld", "expedia", "klook", "getyourguide",
                "trip com", "hotels com", "wizz air", "transavia", "vueling",
                "emirates", "qatar airways", "airasia", "vietjet", "hostel",
                "resort", "guesthouse", "airport", "aeroport", "duty free",
                "lodge", "auberge"],
    "Abonnements": ["netflix", "spotify", "amazon prime", "disney", "canal+", "youtube",
                    "icloud", "google one", "microsoft", "adobe", "openai", "anthropic",
                    "free mobile", "orange", "sfr", "bouygues", "sosh", "red by sfr",
                    "chatgpt", "claude ai", "notion", "dropbox", "github", "linkedin",
                    "duolingo", "google play", "itunes", "apple com bill", "patreon",
                    "abonnement", "subscription"],
    "Logement": ["loyer", "edf", "engie", "veolia", "suez", "gaz", "electricite",
                 "eau", "syndic", "charges copro", "taxe habitation", "rent",
                 "electricity", "internet box"],
    "Sante": ["pharmacie", "medecin", "docteur", "mutuelle", "harmonie", "laboratoire",
              "dentiste", "opticien", "hopital", "cpam",
              "pharmacy", "clinic", "clinique", "hospital", "dental", "optic",
              "kine", "osteopathe", "vaccination"],
    "Assurances": ["assurance", "axa", "maif", "macif", "matmut", "allianz", "gmf",
                   "groupama", "maaf", "insurance"],
    "Frais bancaires": ["frais bancaire", "cotisation carte", "agios",
                        "commission d intervention", "atm", "cash withdrawal",
                        "retrait dab", "exchange fee", "frais de change",
                        "bank fee", "service charge", "plan fee", "account fee",
                        "card fee", "monthly fee", "annual fee",
                        "membership fee", "frais de tenue"],
    "Impots": ["dgfip", "impot", "tresor public", "urssaf", "taxe fonciere", "tax office"],
    "Loisirs": ["cinema", "fnac", "decathlon", "steam", "salle de sport", "basic fit",
                "fitness park", "musee", "concert", "billetterie",
                "gym", "museum", "cinepolis", "bowling", "escape game", "massage",
                "playstation", "nintendo", "lootcode"],
    "Shopping": ["amazon", "zalando", "vinted", "ikea", "leroy merlin", "action",
                 "zara", "h&m", "uniqlo", "cdiscount",
                 "shopee", "lazada", "aliexpress", "temu", "shein", "ebay", "etsy",
                 "leboncoin", "boutique", "store"],
    "Epargne/Investissement": ["trade republic", "traderepublic", "boursorama invest",
                               "degiro", "binance", "coinbase", "kraken", "bitpanda",
                               "virement livret", "versement pea"],
}

INCOME_KEYWORDS = {
    "Salaire": ["salaire", "paie", "paye", "remuneration", "virement employeur",
                "salary", "payroll", "wage"],
    "Argent parents": ["papa", "maman", "parents"],
    "Revenu locatif": ["loyer recu", "loyer percu", "locataire", "rent received"],
    "Interets": ["interets", "interet crediteur", "interest", "net interest",
                 "dividende", "dividend", "coupon"],
    "Remboursement": ["remboursement", "refund", "cashback", "reimbursement",
                      "avoir", "reverted"],
}


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text or "")
        if not unicodedata.combining(c)
    )


def norm(text: str) -> str:
    """Normalisation pour comparaison : sans accents, minuscules, espaces compactés."""
    text = strip_accents(str(text or "")).lower()
    text = re.sub(r"[^a-z0-9+&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(raw):
    """Convertit '1 234,56 €', '-25.30', '(12,00)' en float. None si illisible."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace(" ", " ").replace(" ", " ")
    text = re.sub(r"[^\d,.\-+]", "", text)
    if not text or text in ("-", "+", ".", ","):
        return None
    if "," in text and "." in text:
        # Le dernier séparateur rencontré est le séparateur décimal.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        text = text.replace(",", "." if len(parts[-1]) in (1, 2) else "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def _match_header(headers, candidates):
    normed = [norm(h) for h in headers]
    for cand in candidates:
        for i, h in enumerate(normed):
            if h == cand:
                return i
    for cand in candidates:
        for i, h in enumerate(normed):
            if h and cand in h:
                return i
    return None


def _sniff_delimiter(sample: str) -> str:
    lines = [l for l in sample.splitlines() if l.strip()][:10]
    best, best_score = ",", -1
    for delim in DELIMITERS:
        counts = [l.count(delim) for l in lines]
        if not counts or max(counts) == 0:
            continue
        # On privilégie le séparateur au nombre d'occurrences le plus stable.
        consistency = sum(1 for c in counts if c == counts[0])
        score = counts[0] * 10 + consistency
        if score > best_score:
            best, best_score = delim, score
    return best


# --- relevés sans séparateur ---------------------------------------------
#
# Un relevé imprimé ou extrait d'un PDF n'a aucun séparateur : ses colonnes sont
# alignées à l'espace. `csv.reader` n'y voit qu'une seule colonne par ligne, et
# renvoyait donc zéro transaction — d'où la consigne « faites convertir votre
# PDF en texte tabulé », qui renvoyait le travail à l'utilisateur.

# Un montant : signe optionnel, puis soit des milliers séparés par une espace
# (y compris les espaces insécables que produisent les extracteurs PDF) ou un
# point, soit une suite de chiffres nue — « 2 450,00 » comme « 2450,00 ». La
# forme groupée est essayée en premier : sans elle, « 2450,00 » ne donnerait
# que sa fin, « 450,00 », et le « 2 » restant passerait pour la fin du libellé.
# Les deux gardes empêchent de commencer ou de finir au milieu d'un nombre.
MONTANT_LIBRE = re.compile(
    r"(?<![\d,.])[-+]?(?:\d{1,3}(?:[ \xa0\u202f.,]\d{3})+|\d+)[,.]\d{2}(?![\d,.])"
)

# Les mois écrits en toutes lettres, français et anglais, avec leurs
# abréviations usuelles. Un relevé imprimé date rarement en chiffres : sans
# cette table, « Aug 1, 2026 » ou « 1 août 2026 » ne présente AUCUNE ligne au
# lecteur, et l'import entier rend zéro transaction.
_MOIS = [
    ("january", "janvier", "jan", "janv"),
    ("february", "fevrier", "feb", "fev", "fevr"),
    ("march", "mars", "mar"),
    ("april", "avril", "apr", "avr"),
    ("may", "mai"),
    ("june", "juin", "jun"),
    ("july", "juillet", "jul", "juil"),
    ("august", "aout", "aug"),
    ("september", "septembre", "sep", "sept"),
    ("october", "octobre", "oct"),
    ("november", "novembre", "nov"),
    ("december", "decembre", "dec"),
]
MOIS_TEXTE = {nom: rang for rang, noms in enumerate(_MOIS, 1) for nom in noms}

# `[^\W\d_]` : une lettre, accentuée ou non. Reconnaître le mot puis le
# chercher dans la table vaut mieux qu'une alternance de cent noms de mois :
# « août » et « aout » y passent par le même chemin.
_MOT = r"([^\W\d_]{3,10})\.?"
_DATES_LIBRES = (
    (re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ama"),
    (re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b"), "jma"),
    (re.compile(r"^\s*" + _MOT + r"\s+(\d{1,2})(?:er)?,?\s+(\d{2,4})\b", re.I), "mja"),
    (re.compile(r"^\s*(\d{1,2})(?:er)?\s+" + _MOT + r"\s+(\d{2,4})\b", re.I), "jmat"),
)

# Lignes de pied de relevé : elles portent une date et un montant, donc rien ne
# les distingue d'une opération sinon leur libellé.
LIBELLES_NON_OPERATION = ("solde", "total", "report", "nouveau solde",
                          "ancien solde", "sous total")

# Un relevé range en annexe les opérations annulées, refusées ou en attente.
# Elles portent une date et un montant comme les autres, et rien dans la ligne
# elle-même ne les en distingue : seul le titre de la section qui les précède
# le dit. Les compter comme des dépenses fausse les totaux — et la banque, elle,
# ne les compte pas dans les siens.
SECTIONS_ECARTEES = ("reverted", "declined", "failed", "cancelled", "canceled",
                     "pending", "rejected", "refused", "annul", "rejet",
                     "refus", "echou", "en attente", "non abouti")
SECTIONS_OPERATIONS = ("transaction", "operation", "mouvement", "ecriture")

# Les mots qui composent une ligne d'en-tête de colonnes, FR et EN.
ENTETES_COLONNES = ("date", "description", "libelle", "intitule", "montant",
                    "debit", "credit", "balance", "solde", "money out",
                    "money in", "valeur", "operation")


def _est_entete_colonnes(ligne):
    """La ligne qui nomme les colonnes, juste avant les opérations."""
    if MONTANT_LIBRE.search(ligne):
        return False
    t = norm(ligne)
    return sum(1 for mot in ENTETES_COLONNES if mot in t) >= 2


def _annonce_de_section(textes, i):
    """Une ligne sans date est un titre de section quand un en-tête de colonnes
    la suit de près.

    C'est le squelette commun à tous les relevés — un titre, les noms de
    colonnes, puis les opérations — et non le vocabulaire d'une banque en
    particulier. S'y raccrocher évite de prendre pour un titre la deuxième
    ligne d'un libellé, qui n'a pas de date elle non plus.
    """
    return any(_est_entete_colonnes(textes[j])
               for j in range(i + 1, min(len(textes), i + 3)))


def _annee(brut):
    """Un relevé bancaire ne remonte pas au siècle dernier."""
    n = int(brut)
    return n if n >= 100 else 2000 + n


def _mois(brut):
    return MOIS_TEXTE.get(strip_accents(brut).lower())


def _date_en_tete(ligne):
    """(date, position de fin) si la ligne commence par une date, sinon (None, 0).

    Quatre écritures se rencontrent sur un relevé : l'ISO, la numérique
    française, et le mois en toutes lettres dans les deux ordres — l'anglais
    « Aug 1, 2026 » comme le français « 1 août 2026 ».
    """
    for motif, forme in _DATES_LIBRES:
        m = motif.match(ligne)
        if not m:
            continue
        a, b, c = m.group(1), m.group(2), m.group(3)
        if forme == "ama":
            annee, mois, jour = _annee(a), int(b), int(c)
        elif forme == "jma":
            jour, mois, annee = int(a), int(b), _annee(c)
        elif forme == "mja":
            mois, jour, annee = _mois(a), int(b), _annee(c)
        else:
            jour, mois, annee = int(a), _mois(b), _annee(c)
        if not mois:
            continue
        try:
            return date(annee, mois, jour), m.end()
        except ValueError:
            continue
    return None, 0


def _colonne_solde(brutes, tolerance=0.011):
    """Le dernier montant de chaque ligne est-il un solde courant ?

    Presque tous les relevés impriment un solde APRÈS le montant de
    l'opération. Le prendre pour l'opération — ce que faisait ce lecteur —
    enregistre silencieusement des montants faux.

    Un solde se trahit tout seul : d'une ligne à la suivante, il varie
    exactement du montant de l'opération. C'est de l'arithmétique, donc cela
    vaut pour n'importe quelle banque, dans n'importe quelle langue, sans rien
    savoir de la mise en page.

    Le seuil est une majorité, jamais l'unanimité : un relevé qui enchaîne
    plusieurs comptes repart d'un autre solde à chaque section, et ces ruptures
    ne doivent pas disqualifier la lecture.
    """
    candidats = [b for b in brutes if len(b["valeurs"]) >= 2]
    if len(candidats) < 4:
        return False
    accords = 0
    for prec, cour in zip(candidats, candidats[1:]):
        delta = cour["valeurs"][-1] - prec["valeurs"][-1]
        if any(abs(abs(delta) - abs(v)) <= tolerance for v in cour["valeurs"][:-1]):
            accords += 1
    return accords >= 0.6 * (len(candidats) - 1)


def _parse_lignes_libres(text: str):
    """Lit un relevé aligné à l'espace, une ligne à la fois.

    Trois indices donnent le sens d'une opération, du plus sûr au moins sûr :
    un signe écrit, la variation du solde courant, et enfin la colonne où le
    montant est aligné. Le solde est le plus précieux des trois — c'est le seul
    qui ne dépende ni de la langue du relevé ni de sa mise en page.
    """
    warnings = []
    brutes = []
    textes = text.splitlines()
    n, exclu, ecartees = 0, False, 0
    while n < len(textes):
        ligne = textes[n]
        n += 1
        d, fin_date = _date_en_tete(ligne)
        if d is None:
            if _annonce_de_section(textes, n - 1):
                titre = norm(ligne)
                if any(x in titre for x in SECTIONS_ECARTEES):
                    exclu = True
                elif any(x in titre for x in SECTIONS_OPERATIONS):
                    exclu = False
            continue
        if exclu:
            ecartees += 1
            continue
        reste = ligne[fin_date:]
        # Un libellé long passe à la ligne dans un PDF, et emporte les montants
        # avec lui. La ligne suivante n'a pas de date à elle : c'est la suite de
        # celle-ci, pas une opération. Sans ce raccord, l'opération entière est
        # perdue en silence — vingt-trois sur cent quatre-vingt-dix-sept dans le
        # relevé qui a servi de témoin.
        joint, sauts = False, 0
        while not MONTANT_LIBRE.search(reste) and n < len(textes) and sauts < 2:
            suite = textes[n]
            if not suite.strip() or _date_en_tete(suite)[0] is not None:
                break
            reste = reste.rstrip() + " " + suite.strip()
            n += 1
            sauts += 1
            joint = True
        trouves = [(m, parse_amount(m.group(0)))
                   for m in MONTANT_LIBRE.finditer(reste)]
        trouves = [(m, v) for m, v in trouves if v is not None]
        if not trouves:
            continue
        desc = re.sub(r"\s+", " ", reste[:trouves[0][0].start()])
        # Le symbole monétaire précède le montant : il reste collé à la fin du
        # libellé, où il n'apprend rien à personne.
        desc = desc.strip(" .-\t\u00a0\u20ac$\u00a3\u00a5")
        if norm(desc).startswith(LIBELLES_NON_OPERATION):
            continue
        brutes.append({
            "date": iso(d),
            "description": desc or "(sans libellé)",
            "valeurs": [v for _m, v in trouves],
            "signes": [m.group(0).strip()[0] in "-+" for m, _v in trouves],
            "fins": [fin_date + m.end() for m, _v in trouves],
            "joint": joint,
            "brut": ligne.strip(),
        })

    if not brutes:
        return [], ["Aucune ligne datée suivie d'un montant dans ce contenu."]

    if ecartees:
        warnings.append(
            f"{ecartees} opération(s) annulée(s), refusée(s) ou en attente "
            "écartée(s) : votre banque ne les compte pas non plus."
        )

    solde = _colonne_solde(brutes)

    def rang_operation(b):
        """L'avant-dernier montant quand la dernière colonne est un solde,
        le dernier sinon."""
        return -2 if solde and len(b["valeurs"]) >= 2 else -1

    # L'alignement se mesure sur la colonne de l'OPÉRATION : mesurée sur celle
    # du solde, elle ne dirait rien du sens. Et il se mesure sur les seules
    # lignes d'un seul tenant : une ligne raccordée a perdu son alignement en
    # cours de route, et fausserait la colonne pour toutes les autres.
    entieres = [b for b in brutes if not b["joint"]] or brutes
    coupure = _coupure_colonnes([b["fins"][rang_operation(b)] for b in entieres])
    if solde:
        warnings.append(
            "Colonne de solde reconnue : le montant retenu est celui de "
            "l'opération, et son sens vient de la variation du solde."
        )
    elif coupure is None:
        warnings.append(
            "Une seule colonne de montants : les lignes sans signe sont lues "
            "comme des débits. Vérifiez les montants avant de confirmer."
        )
    else:
        warnings.append(
            "Colonnes débit et crédit reconnues à leur alignement. "
            "Vérifiez quelques lignes avant de confirmer."
        )

    # Premier passage : ce que l'on sait de source sûre, ligne par ligne.
    decisions, precedent = [], None
    for b in brutes:
        i = rang_operation(b)
        delta = None
        if solde and len(b["valeurs"]) >= 2:
            courant = b["valeurs"][-1]
            if precedent is not None:
                delta = round(courant - precedent, 2)
                # Quand la ligne porte plusieurs montants — colonnes débit ET
                # crédit imprimées — celui qui explique la variation est le bon.
                for j, v in enumerate(b["valeurs"][:-1]):
                    if abs(abs(delta) - abs(v)) <= 0.011:
                        i = j
                        break
                else:
                    # Changement de section : le solde repart d'ailleurs et
                    # cette variation-là ne veut rien dire.
                    delta = None
            precedent = courant
        if b["signes"][i]:
            signe = 1 if b["valeurs"][i] > 0 else -1   # un signe écrit fait foi
        elif delta:
            signe = 1 if delta > 0 else -1
        else:
            signe = None
        decisions.append([b, i, signe])

    # Second passage. Le solde vient d'apprendre où se tiennent les débits et où
    # se tiennent les crédits ; les rares lignes qu'il ne tranche pas — la
    # première de chaque section, qui n'a pas de solde avant elle — se rangent
    # dans la colonne la plus proche. C'est mieux qu'un simple partage en deux :
    # ici les colonnes sont observées, pas devinées.
    connues = {1: [], -1: []}
    for b, i, signe in decisions:
        if signe:
            connues[signe].append(b["fins"][i])

    lines = []
    for b, i, signe in decisions:
        if signe is None:
            fin = b["fins"][i]
            if connues[1] and connues[-1]:
                signe = 1 if (abs(fin - _mediane(connues[1]))
                              <= abs(fin - _mediane(connues[-1]))) else -1
            elif coupure is not None:
                signe = 1 if fin >= coupure else -1
            else:
                signe = -1
        lines.append({
            "date": b["date"],
            "description": b["description"],
            "amount": round(signe * abs(b["valeurs"][i]), 2),
            "devise": "EUR",
            "brut": b["brut"],
        })
    return lines, warnings


def _mediane(valeurs):
    ordonnees = sorted(valeurs)
    return ordonnees[len(ordonnees) // 2]


def _coupure_colonnes(fins, ecart_min=4):
    """Position qui sépare la colonne débit de la colonne crédit, ou None.

    On cherche le plus grand trou entre deux fins de montant. En dessous de
    `ecart_min` caractères, il n'y a qu'une colonne : deux montants voisins de
    quelques caractères ne sont pas deux colonnes, seulement deux longueurs.
    """
    uniques = sorted(set(fins))
    if len(uniques) < 2:
        return None
    trou, coupure = 0, None
    for a, b in zip(uniques, uniques[1:]):
        if b - a > trou:
            trou, coupure = b - a, b
    return coupure if trou >= ecart_min else None


def extract_text(data: bytes, filename: str = "") -> str:
    """Texte d'un fichier déposé : PDF extrait page à page, sinon décodé.

    L'entête `%PDF` fait autorité plutôt que l'extension : un relevé
    téléchargé arrive parfois sans extension du tout.
    """
    if not data:
        return ""
    if data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
        except ImportError:  # pragma: no cover - dependance absente
            raise ValueError(
                "Lecture des PDF indisponible : le module pypdf n'est pas installé."
            )
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise ValueError(f"PDF illisible : {exc}")
        texte = "\n".join(pages).strip()
        if not texte:
            raise ValueError(
                "Ce PDF ne contient pas de texte : c'est une image numérisée. "
                "Seuls les relevés téléchargés depuis votre banque sont lisibles."
            )
        return texte
    # Les exports bancaires sortent en UTF-8, en Windows-1252, ou avec un BOM.
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encodage)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_statement(text: str):
    """Renvoie (lignes, avertissements).

    Chaque ligne : {date, description, amount, devise, brut}.
    """
    warnings = []
    text = (text or "").strip("﻿ \n\r\t")
    if not text:
        return [], ["Contenu vide."]

    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw_rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not raw_rows:
        return [], ["Aucune ligne exploitable."]

    header = raw_rows[0]
    idx_date = _match_header(header, DATE_HEADERS)
    idx_desc = _match_header(header, DESC_HEADERS)
    idx_amount = _match_header(header, AMOUNT_HEADERS)
    idx_debit = _match_header(header, DEBIT_HEADERS)
    idx_credit = _match_header(header, CREDIT_HEADERS)
    idx_fee = _match_header(header, FEE_HEADERS)
    idx_state = _match_header(header, STATE_HEADERS)
    idx_currency = _match_header(header, CURRENCY_HEADERS)

    # `len(header) >= 2` : sur un relevé non délimité, la virgule décimale des
    # montants suffit à faire croire à un séparateur. L'en-tête, lui, n'en
    # contient pas et reste d'un seul tenant — un tableau d'une seule colonne
    # n'est pas un tableau, et le reconnaître ici évite de lire tout le relevé
    # de travers.
    has_header = (len(header) >= 2 and idx_date is not None
                  and (idx_amount is not None or idx_debit is not None
                       or idx_credit is not None))
    body = raw_rows[1:] if has_header else raw_rows
    if not has_header:
        warnings.append(
            "En-tête non reconnu : lecture positionnelle (date, libellé, montant)."
        )
        idx_date, idx_desc, idx_amount = 0, 1, 2
        idx_debit = idx_credit = idx_fee = idx_state = idx_currency = None

    lines, skipped = [], 0
    for row in body:
        def cell(i):
            return row[i].strip() if i is not None and i < len(row) and row[i] else ""

        d = parse_date(cell(idx_date))
        if d is None:
            skipped += 1
            continue

        if idx_amount is not None:
            amount = parse_amount(cell(idx_amount))
        else:
            debit = parse_amount(cell(idx_debit)) or 0.0
            credit = parse_amount(cell(idx_credit)) or 0.0
            amount = credit - abs(debit)
        if amount is None:
            skipped += 1
            continue

        fee = parse_amount(cell(idx_fee)) or 0.0
        if fee:
            amount -= abs(fee)

        state = norm(cell(idx_state))
        if state and state in ("reverted", "declined", "failed", "rejete", "annule", "pending"):
            skipped += 1
            continue

        desc = cell(idx_desc)
        if not desc:
            # Reprend la première colonne texte non numérique disponible.
            for i, c in enumerate(row):
                if i in (idx_date, idx_amount) or not c.strip():
                    continue
                if parse_amount(c) is None and parse_date(c) is None:
                    desc = c.strip()
                    break
        lines.append({
            "date": iso(d),
            "description": desc or "(sans libellé)",
            "amount": round(amount, 2),
            "devise": cell(idx_currency) or "EUR",
            "brut": delimiter.join(row),
        })

    # Second essai en lecture alignée, celle d'un relevé imprimé ou extrait d'un
    # PDF. La lecture délimitée garde la main quand elle réussit vraiment :
    # c'est elle qui distingue débit et crédit sans avoir à deviner.
    #
    # Deux cas la déclarent en échec. Aucune ligne, évidemment. Mais aussi des
    # lignes dont le libellé commence lui-même par une date : le découpage n'a
    # alors rien découpé, la ligne entière a atterri dans une seule cellule, et
    # ce qui en sort ressemble à des transactions sans en être.
    if not lines or sum(_date_en_tete(l["description"])[0] is not None
                        for l in lines) * 2 >= len(lines):
        libres, avertissements_libres = _parse_lignes_libres(text)
        if libres:
            return libres, avertissements_libres

    if skipped:
        warnings.append(f"{skipped} ligne(s) ignorée(s) (date ou montant illisible).")
    if not lines:
        warnings.append("Aucune transaction reconnue dans ce contenu.")
    return lines, warnings


# --- déduplication --------------------------------------------------------


def dedup_hash(d, amount, description) -> str:
    key = f"{iso(d)}|{float(amount):.2f}|{norm(description)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def movement_hash(asset_id, d, ticker, quantite, montant) -> str:
    """Empreinte d'un mouvement de titres, pour ne pas l'importer deux fois.

    Un relevé de courtier se réimporte souvent avec un chevauchement de
    période. Sans empreinte, les quantités doubleraient en silence — et une
    quantité fausse fausse toute la valorisation de la ligne.

    La quantité entre dans la clé : deux achats du même ETF le même jour, pour
    des quantités différentes, sont bien deux opérations distinctes.
    """
    q = "" if quantite in (None, "") else f"{float(quantite):.8f}"
    key = f"{asset_id}|{iso(d)}|{norm(ticker)}|{q}|{float(montant or 0):.2f}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


# --- classification -------------------------------------------------------


def _apply_rules(description, rules):
    text = norm(description)
    for rule in sorted(rules, key=lambda r: (r["priorite"], r["pattern"])):
        pattern = norm(rule["pattern"])
        if pattern and pattern in text:
            return rule["valeur"], rule["id"]
    return None, None


def _apply_keywords(description, amount):
    """Le filet intégré, comparé au JETON et non à la sous-chaîne.

    Chercher « bp » n'importe où dans un libellé le trouvait dans « abonnement »
    autant que dans une station-service — d'où les mots-clés écrits « bp » avec
    une espace finale, qui rataient alors les fins de ligne. Comparer des mots
    entiers supprime le bricolage et les faux positifs d'un seul coup.

    Un mot-clé long reste cherché en sous-chaîne : « carrefour » est assez
    spécifique pour être reconnu dans « CARREFOURMARKET », que l'extraction d'un
    PDF colle parfois d'un seul tenant.
    """
    text = norm(description)
    jetons = text.split()
    # Le signe dit quelle table consulter D'ABORD, pas laquelle consulter tout
    # court. Un remboursement « Carrefour » arrive en crédit et reste pourtant de
    # l'alimentation. Et une ligne à 0,00 € — un intérêt arrondi à rien — n'est
    # pas un revenu au sens strict : elle était cherchée parmi les dépenses, où
    # elle ne pouvait rien trouver.
    tables = ([INCOME_KEYWORDS, DEFAULT_KEYWORDS] if amount > 0
              else [DEFAULT_KEYWORDS, INCOME_KEYWORDS])
    for table in tables:
        for category, keywords in table.items():
            for kw in keywords:
                mots = norm(kw).split()
                if not mots:
                    continue
                if len(mots) > 1:
                    n = len(mots)
                    if any(jetons[i:i + n] == mots
                           for i in range(len(jetons) - n + 1)):
                        return category
                elif mots[0] in jetons or (len(mots[0]) >= 6 and mots[0] in text):
                    return category
    return None


def detect_loan_payment(d, amount, liabilities, tolerance=2.0, day_tolerance=6):
    """Retourne le liability_id si le débit correspond à une échéance de prêt.

    On compare le montant prélevé à la mensualité calculée (± tolérance) et la
    date à l'échéance attendue (± quelques jours). Aucune règle textuelle
    n'est nécessaire.
    """
    d = parse_date(d)
    if d is None or amount >= 0:
        return None
    debit = abs(amount)
    best = None
    for liab, summary in liabilities:
        start = parse_date(liab["date_debut"])
        if not start:
            continue
        end = add_months(start, int(liab["duree_mois"] or 0))
        if not (start <= d <= end + timedelta(days=day_tolerance)):
            continue
        for target in (summary["mensualite"], summary["mensualite_avec_assurance"]):
            if target <= 0 or abs(debit - target) > tolerance:
                continue
            # Échéance théorique la plus proche de la date du débit.
            months_elapsed = (d.year - start.year) * 12 + (d.month - start.month)
            for offset in (months_elapsed, months_elapsed + 1):
                if offset < 1 or offset > int(liab["duree_mois"] or 0):
                    continue
                expected = add_months(start, offset)
                gap = abs((d - expected).days)
                if gap <= day_tolerance and (best is None or gap < best[1]):
                    best = (liab["id"], gap)
    return best[0] if best else None


TICKER_HEADERS = ["ticker", "symbole", "symbol", "isin", "instrument", "valeur",
                  "titre", "produit", "name", "nom", "libelle"]
QTY_HEADERS = ["quantite", "quantity", "qty", "nombre", "parts", "shares", "nb"]
PRICE_HEADERS = ["prix unitaire", "prix", "price", "cours", "share price",
                 "prix par part", "unit price"]
SIDE_HEADERS = ["type", "sens", "side", "operation", "transaction type"]
SELL_WORDS = ("vente", "sell", "sale", "retrait", "cession", "withdraw")


def parse_movements(text: str):
    """Parse un relevé de titres collé (Trade Republic, autre courtier).

    Objectif : récupérer date, ticker, quantité, prix unitaire et montant pour
    alimenter `asset_movements` et permettre le calcul du PRU et du TRI réels.
    """
    warnings = []
    text = (text or "").strip("﻿ \n\r\t")
    if not text:
        return [], ["Contenu vide."]

    delimiter = _sniff_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any((c or "").strip() for c in r)]
    if not rows:
        return [], ["Aucune ligne exploitable."]

    header = rows[0]
    idx = {
        "date": _match_header(header, DATE_HEADERS),
        "ticker": _match_header(header, TICKER_HEADERS),
        "qty": _match_header(header, QTY_HEADERS),
        "price": _match_header(header, PRICE_HEADERS),
        "amount": _match_header(header, AMOUNT_HEADERS),
        "side": _match_header(header, SIDE_HEADERS),
    }
    has_header = idx["date"] is not None and (
        idx["qty"] is not None or idx["amount"] is not None
    )
    body_rows = rows[1:] if has_header else rows
    if not has_header:
        warnings.append(
            "En-tête non reconnu : lecture positionnelle "
            "(date, ticker, quantité, prix unitaire)."
        )
        idx = {"date": 0, "ticker": 1, "qty": 2, "price": 3, "amount": 4, "side": None}

    lines, skipped = [], 0
    for row in body_rows:
        def cell(key):
            i = idx.get(key)
            return row[i].strip() if i is not None and i < len(row) and row[i] else ""

        d = parse_date(cell("date"))
        if d is None:
            skipped += 1
            continue
        qty = parse_amount(cell("qty"))
        price = parse_amount(cell("price"))
        amount = parse_amount(cell("amount"))
        if amount is None and qty is not None and price is not None:
            amount = qty * price
        if amount is None and qty is None:
            skipped += 1
            continue
        side = norm(cell("side"))
        is_sell = any(w in side for w in SELL_WORDS) or (amount is not None and amount < 0)
        lines.append({
            "date": iso(d),
            "ticker": cell("ticker") or "",
            "quantite": abs(qty) if qty is not None else None,
            "prix_unitaire": abs(price) if price is not None else None,
            "montant": round(abs(amount), 2) if amount is not None else None,
            "type": "retrait" if is_sell else "versement",
            "ignore": False,
        })
    if skipped:
        warnings.append(f"{skipped} ligne(s) ignorée(s) (date ou montant illisible).")
    if not lines:
        warnings.append("Aucun mouvement reconnu dans le contenu collé.")
    return lines, warnings


def classify(line, rules, liabilities, tolerance=2.0, day_tolerance=6,
             modele=None, seuil=1.0):
    """Renvoie (category, liability_id, origine, confiance).

    Ordre : règles utilisateur, échéance de prêt, modèle appris, mots-clés
    intégrés, défaut. Les règles gardent la priorité : c'est l'utilisateur qui a
    le dernier mot sur sa propre classification, et un modèle ne doit jamais
    passer devant une consigne explicite.

    Le modèle est passé de l'extérieur, avec son seuil. Ce module ne connaît
    donc pas `classifier`, qui le connaît lui — sans quoi les deux s'importeraient
    l'un l'autre. En dessous du seuil, le modèle se tait : une ligne « à
    classer » se voit et se corrige, une ligne mal classée passe inaperçue.

    Il y avait ici une quatrième étape, une liste de mots-clés qui marquaient
    un virement interne. Elle faisait exactement ce qu'une règle fait — chercher
    un texte dans le libellé pour attribuer une catégorie — avec son propre
    écran et son propre vocabulaire. Ces mots sont devenus des règles
    ordinaires (voir `_fondre_mots_cles_dans_les_regles` dans db.py).
    """
    amount = line["amount"]
    value, _rule_id = _apply_rules(line["description"], rules)

    liability_id = detect_loan_payment(
        line["date"], amount, liabilities, tolerance, day_tolerance
    )
    if value:
        return value, liability_id, "regle", 1.0
    if liability_id:
        return "Remboursement pret", liability_id, "pret", 1.0
    if modele is not None:
        appris, confiance = modele.predire(line["description"], amount)
        if appris and confiance >= seuil:
            return appris, None, "modele", confiance
    keyword = _apply_keywords(line["description"], amount)
    if keyword:
        return keyword, None, "mot-cle", 1.0
    return ("Autre revenu" if amount > 0 else "Non categorise"), None, "defaut", 0.0
