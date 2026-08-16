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
DEFAULT_KEYWORDS = {
    "Alimentation": ["carrefour", "leclerc", "lidl", "auchan", "intermarche", "super u",
                     "monoprix", "franprix", "casino", "biocoop", "picard", "aldi"],
    "Restaurants": ["restaurant", "mcdonald", "burger", "uber eats", "deliveroo",
                    "just eat", "boulangerie", "starbucks", "kebab", "sushi", "brasserie"],
    "Transport": ["sncf", "ratp", "uber", "total", "totalenergies", "esso", "shell",
                  "bp ", "essence", "peage", "vinci autoroute", "blablacar", "parking",
                  "velib", "navigo", "tan ", "tcl ", "carburant"],
    "Abonnements": ["netflix", "spotify", "amazon prime", "disney", "canal+", "youtube",
                    "icloud", "google one", "microsoft", "adobe", "openai", "anthropic",
                    "free mobile", "orange", "sfr", "bouygues", "sosh", "red by sfr"],
    "Logement": ["loyer", "edf", "engie", "veolia", "suez", "gaz", "electricite",
                 "eau ", "syndic", "charges copro", "taxe habitation"],
    "Sante": ["pharmacie", "medecin", "docteur", "mutuelle", "harmonie", "laboratoire",
              "dentiste", "opticien", "hopital", "cpam"],
    "Assurances": ["assurance", "axa", "maif", "macif", "matmut", "allianz", "gmf",
                   "groupama", "maaf"],
    "Frais bancaires": ["frais bancaire", "cotisation carte", "agios", "commission d intervention"],
    "Impots": ["dgfip", "impot", "tresor public", "urssaf", "taxe fonciere"],
    "Loisirs": ["cinema", "fnac", "decathlon", "steam", "salle de sport", "basic fit",
                "fitness park", "musee", "concert", "billetterie"],
    "Shopping": ["amazon", "zalando", "vinted", "ikea", "leroy merlin", "action ",
                 "zara", "h&m", "uniqlo", "cdiscount"],
    "Voyages": ["booking", "airbnb", "ryanair", "easyjet", "air france", "hotel"],
    "Epargne/Investissement": ["trade republic", "traderepublic", "boursorama invest",
                               "degiro", "binance", "coinbase", "kraken", "bitpanda",
                               "virement livret", "versement pea"],
}

INCOME_KEYWORDS = {
    "Salaire": ["salaire", "paie", "paye", "remuneration", "virement employeur"],
    "Argent parents": ["papa", "maman", "parents"],
    "Revenu locatif": ["loyer recu", "loyer percu", "locataire"],
    "Interets": ["interets", "interet crediteur"],
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

    has_header = idx_date is not None and (idx_amount is not None or idx_debit is not None
                                           or idx_credit is not None)
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

    if skipped:
        warnings.append(f"{skipped} ligne(s) ignorée(s) (date ou montant illisible).")
    if not lines:
        warnings.append("Aucune transaction reconnue dans le contenu collé.")
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
    text = norm(description)
    table = INCOME_KEYWORDS if amount > 0 else DEFAULT_KEYWORDS
    for category, keywords in table.items():
        for kw in keywords:
            if norm(kw) in text:
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


def looks_like_transfer(description, keywords) -> bool:
    """Vrai si le libellé trahit un mouvement entre comptes de l'utilisateur.

    Vaut pour les deux sens : le débit côté LCL comme le crédit côté Revolut.
    """
    text = norm(description)
    return any(norm(kw) and norm(kw) in text for kw in (keywords or []))


def classify(line, rules, liabilities, tolerance=2.0, day_tolerance=6,
             transfer_keywords=None, transfer_category="Transfert interne"):
    """Renvoie (category, liability_id, origine).

    Ordre : règles utilisateur, puis échéance de prêt, puis virement interne,
    puis mots-clés intégrés. Les règles gardent la priorité : c'est
    l'utilisateur qui a le dernier mot sur sa propre classification.
    """
    amount = line["amount"]
    value, _rule_id = _apply_rules(line["description"], rules)

    liability_id = detect_loan_payment(
        line["date"], amount, liabilities, tolerance, day_tolerance
    )
    if value:
        return value, liability_id, "regle"
    if liability_id:
        return "Remboursement pret", liability_id, "pret"
    if looks_like_transfer(line["description"], transfer_keywords):
        return transfer_category, None, "transfert"
    keyword = _apply_keywords(line["description"], amount)
    if keyword:
        return keyword, None, "mot-cle"
    return ("Autre revenu" if amount > 0 else "Non categorise"), None, "defaut"
