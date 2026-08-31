"""Coeur de calcul, sans dependance a Flask ni a la base.

Tout est recalcule a la volee : aucun de ces resultats n'est destine a etre
stocke en base (cf. cahier des charges, section 6 et 9).
"""
import calendar
from datetime import date, datetime, timedelta

# --- utilitaires de dates -------------------------------------------------


def parse_date(value):
    """Accepte date, datetime, 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def iso(d) -> str:
    d = parse_date(d)
    return d.isoformat() if d else ""


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_bounds(year: int, month: int):
    """(premier_jour, dernier_jour) du mois."""
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_key(d) -> str:
    d = parse_date(d)
    return f"{d.year:04d}-{d.month:02d}" if d else ""


def months_between(start: date, end: date):
    """Liste des cles 'YYYY-MM' de start a end inclus."""
    out, cur = [], date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cur <= last:
        out.append(f"{cur.year:04d}-{cur.month:02d}")
        cur = add_months(cur, 1)
    return out


# --- prets ----------------------------------------------------------------


def monthly_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    """Mensualite d'un pret a taux fixe (hors assurance)."""
    if months <= 0:
        return 0.0
    r = (annual_rate_pct or 0.0) / 12.0 / 100.0
    if abs(r) < 1e-12:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


def amortization_schedule(principal, annual_rate_pct, months, start_date, insurance=0.0):
    """Tableau d'amortissement standard.

    L'echeance n tombe a start_date + n mois. La derniere echeance solde
    exactement le capital restant (absorbe les arrondis).
    """
    start_date = parse_date(start_date)
    months = int(months or 0)
    if not start_date or months <= 0 or principal <= 0:
        return []
    r = (annual_rate_pct or 0.0) / 12.0 / 100.0
    base = monthly_payment(principal, annual_rate_pct, months)
    remaining = float(principal)
    rows = []
    for n in range(1, months + 1):
        interest = remaining * r
        capital = base - interest
        if n == months or capital > remaining:
            capital = remaining
        payment = capital + interest
        remaining = max(0.0, remaining - capital)
        rows.append({
            "n": n,
            "date": iso(add_months(start_date, n)),
            "mensualite": round(payment, 2),
            "interets": round(interest, 2),
            "capital": round(capital, 2),
            "assurance": round(insurance or 0.0, 2),
            "total_preleve": round(payment + (insurance or 0.0), 2),
            "capital_restant": round(remaining, 2),
        })
        if remaining <= 0:
            break
    return rows


def remaining_principal(liability, at_date=None) -> float:
    """Capital restant du a une date donnee. Jamais stocke, toujours recalcule."""
    at_date = parse_date(at_date) or date.today()
    start = parse_date(liability["date_debut"])
    principal = float(liability["montant_emprunte"] or 0)
    if not start or at_date < start:
        return 0.0 if not start else principal
    sched = amortization_schedule(
        principal, liability["taux_annuel"], liability["duree_mois"], start
    )
    remaining = principal
    for row in sched:
        if parse_date(row["date"]) <= at_date:
            remaining = row["capital_restant"]
        else:
            break
    return round(remaining, 2)


def liability_summary(liability, at_date=None, schedule=None):
    """Synthese d'un pret a une date.

    `schedule` permet de passer le tableau d'amortissement deja calcule : il ne
    depend pas de la date, et le recalculer pour chaque mois d'un historique
    coute cher (240 echeances par pret et par mois).
    """
    at_date = parse_date(at_date) or date.today()
    start = parse_date(liability["date_debut"])
    principal = float(liability["montant_emprunte"] or 0)
    duree = int(liability["duree_mois"] or 0)
    insurance = float(liability["assurance_mensuelle"] or 0)
    pmt = monthly_payment(principal, liability["taux_annuel"], duree)
    sched = schedule if schedule is not None else amortization_schedule(
        principal, liability["taux_annuel"], duree, start, insurance)
    paid = [r for r in sched if parse_date(r["date"]) <= at_date]
    crd = paid[-1]["capital_restant"] if paid else principal
    return {
        "mensualite": round(pmt, 2),
        "mensualite_avec_assurance": round(pmt + insurance, 2),
        "capital_restant": round(crd, 2),
        "echeances_payees": len(paid),
        "echeances_totales": len(sched),
        "date_fin": sched[-1]["date"] if sched else None,
        "interets_totaux": round(sum(r["interets"] for r in sched), 2),
        "interets_payes": round(sum(r["interets"] for r in paid), 2),
        "cout_total": round(sum(r["total_preleve"] for r in sched), 2),
        "prochaine_echeance": next(
            (r for r in sched if parse_date(r["date"]) > at_date), None
        ),
    }


# --- valorisation d'un actif ---------------------------------------------


def asset_value_at(asset, movements, at_date=None, use_manual_current=True) -> float:
    """Valeur d'un actif a une date donnee, reconstituee depuis les mouvements.

    Regle : on part de la derniere `valorisation` connue a cette date (ou de la
    valeur d'acquisition), puis on ajoute les versements/retraits posterieurs.
    Pour la date du jour, `valeur_actuelle` (saisie manuelle) fait autorite si
    elle est renseignee.
    """
    at_date = parse_date(at_date) or date.today()
    acq = parse_date(asset["date_acquisition"])
    if acq and at_date < acq:
        return 0.0

    if use_manual_current and at_date >= date.today() and asset["valeur_actuelle"] is not None:
        return float(asset["valeur_actuelle"])

    base = float(asset["valeur_acquisition"] or 0)
    base_date = acq or at_date
    ordered = sorted(movements, key=lambda m: (parse_date(m["date"]) or date.min, m["type"]))
    for mv in ordered:
        d = parse_date(mv["date"])
        if d and d <= at_date and mv["type"] == "valorisation":
            base = float(mv["montant"] or 0)
            base_date = d
    flows = 0.0
    for mv in ordered:
        d = parse_date(mv["date"])
        # `frais` compris : l'argent d'un frais autonome quitte reellement le
        # produit, sa valeur doit baisser d'autant.
        if d and base_date < d <= at_date and mv["type"] in ("versement", "retrait", "frais"):
            flows += float(mv["montant"] or 0)
    return round(base + flows, 2)


# --- livrets reglementes --------------------------------------------------
#
# Les livrets ne se cotent pas : leurs interets se calculent, selon la regle
# francaise des quinzaines. Un versement porte interet a partir du 1er ou du 16
# qui suit ; un retrait cesse d'en produire a partir du 1er ou du 16 qui
# precede ; les interets sont capitalises a la date de credit (le 31 decembre
# pour tous les produits reglementes).
#
# Le solde renvoye est le CAPITAL, celui du releve bancaire : les interets de
# l'exercice en cours ne sont pas encore credites et n'y figurent donc pas.
# `interets_prevus` dit separement ce qui tombera a la prochaine echeance.

CREDIT_PAR_DEFAUT = "12-31"


def _quinzaine(d: date) -> int:
    """Numero de quinzaine absolu (24 par an), pour ordonner les evenements."""
    return d.year * 24 + (d.month - 1) * 2 + (0 if d.day <= 15 else 1)


def _quinzaine_revolue(d: date) -> bool:
    """Vrai si `d` est le dernier jour de sa quinzaine (le 15, ou fin de mois).

    Une quinzaine ne paie qu'une fois ecoulee. Sans ce controle, la quinzaine
    en cours etait creditee d'avance : un livret declare le jour meme affichait
    aussitot une quinzaine d'interets, soit +0,1 % au taux du Livret A, et une
    plus-value sortie de nulle part.
    """
    return d.day == 15 or d.day == calendar.monthrange(d.year, d.month)[1]


def _jour_credit(credit):
    """'MM-JJ' -> (mois, jour). Retombe sur le 31 decembre si illisible."""
    try:
        mois, jour = str(credit or CREDIT_PAR_DEFAUT).split("-")
        mois, jour = int(mois), int(jour)
        date(2000, mois, min(jour, calendar.monthrange(2000, mois)[1]))
        return mois, jour
    except (ValueError, TypeError):
        return 12, 31


def _quinzaine_credit(annee_quinzaine, mois, jour):
    """Quinzaine ou tombe la capitalisation, pour une annee donnee."""
    jour = min(jour, calendar.monthrange(annee_quinzaine, mois)[1])
    return _quinzaine(date(annee_quinzaine, mois, jour))


def _debut_millesime(d, mois, jour):
    """Lendemain de la derniere capitalisation a la date `d`.

    C'est la que demarre l'annee d'interets en cours. Les interets courus
    depuis cette date sont dus : la banque les versera a la prochaine echeance,
    quoi qu'il arrive entre-temps.
    """
    echeance = date(d.year, mois, min(jour, calendar.monthrange(d.year, mois)[1]))
    if echeance >= d:
        an = d.year - 1
        echeance = date(an, mois, min(jour, calendar.monthrange(an, mois)[1]))
    return echeance + timedelta(days=1)


def valeur_livret(asset, movements, taux_annuel, at_date=None, credit=None) -> float:
    """Capital d'un livret a une date donnee, interets deja credites inclus.

    Calcul pur, sans reseau, recalcule a chaque appel : une correction sur un
    versement passe se repercute immediatement.

    Ce que la fonction ne renvoie PAS : les interets de l'exercice en cours.
    Ils ne sont pas encore acquis, la banque ne les affiche pas non plus, et les
    ajouter faisait diverger l'application du releve toute l'annee. Voir
    `interets_prevus`.
    """
    at_date = parse_date(at_date) or date.today()
    acq = parse_date(asset["date_acquisition"])
    if not acq or at_date < acq:
        return 0.0

    # Point de depart : derniere valorisation connue, sinon l'acquisition.
    base_date, base = acq, float(asset["valeur_acquisition"] or 0)
    connu = False
    valorisations = False
    for mv in sorted(movements, key=lambda m: parse_date(m["date"]) or date.min):
        d = parse_date(mv["date"])
        if not d or mv["type"] != "valorisation":
            continue
        valorisations = True
        if d <= at_date:
            base_date, base, connu = d, float(mv["montant"] or 0), True

    # AUCUN solde connu a cette date, alors qu'il en existe un plus tard.
    #
    # C'est la signature d'un produit deja constitue : on l'a declare avec son
    # solde DU JOUR, sous sa date d'OUVERTURE. Composer les interets depuis
    # cette ouverture les fait courir sur des annees ou rien ne dit que
    # l'argent etait la. Un Livret A ouvert en 2003 et declare 3 985 EUR en
    # 2026 « valait » ainsi 5 798 EUR au 31 decembre precedent — 1 813 EUR que
    # la banque n'a jamais verses. Le retour au solde reel se lisait ensuite
    # comme une perte de 1 813 EUR sur l'annee.
    #
    # Avant le premier solde connu, on ne sait rien. Le montant declare est
    # donc reporte tel quel, corrige des seuls mouvements reels. C'est plat, et
    # c'est le seul choix qui n'invente pas de passe.
    #
    # Sans AUCUNE valorisation, en revanche, la valeur d'acquisition est bien
    # ce qu'elle dit : un depot a cette date, dont les interets sont dus.
    if not connu and valorisations:
        total = base
        for mv in movements:
            d = parse_date(mv["date"])
            if d and d <= at_date and mv["type"] in ("versement", "retrait", "frais"):
                total += float(mv["montant"] or 0)
        return round(total, 2)

    mois_credit, jour_credit = _jour_credit(credit)
    rate = (taux_annuel or 0.0) / 100.0 / 24.0

    # L'annee d'interets court depuis la derniere capitalisation, PAS depuis la
    # derniere valorisation. Une valorisation dit COMBIEN il y a sur le livret,
    # pas depuis quand : le solde d'un livret ne contient jamais les interets de
    # l'annee en cours, puisqu'ils ne sont verses qu'a l'echeance. Repartir de sa
    # date les effacait — recaler son Livret Jeune fin aout sur le meme montant
    # faisait tomber la projection de 48 EUR a 18 EUR.
    #
    # Le solde declare est donc suppose avoir ete la depuis le debut du
    # millesime. C'est une approximation, la meme que celle qu'on fait de tete en
    # multipliant son solde par son taux, et elle vaut mieux que de supposer
    # l'argent apparu le jour de la saisie. Deux garde-fous : on ne remonte
    # jamais avant l'ouverture du livret (`acq`), ni avant une valorisation plus
    # ancienne, dont les millesimes suivants doivent etre rejoues pour capitaliser.
    debut_millesime = max(acq, _debut_millesime(base_date, mois_credit, jour_credit))
    start_q = min(_quinzaine(base_date), _quinzaine(debut_millesime))
    end_q = _quinzaine(at_date)

    # Le solde de base entre au debut du millesime, et non a la date de la
    # valorisation : c'est ce report qui lui rend les quinzaines deja courues.
    events = [(start_q, base)]
    for mv in movements:
        d = parse_date(mv["date"])
        if not d or not (base_date < d <= at_date):
            continue
        montant = float(mv["montant"] or 0)
        if mv["type"] == "versement":
            events.append((_quinzaine(d) + 1, abs(montant)))
        elif mv["type"] in ("retrait", "frais"):
            # Un retrait comme un frais quittent le livret a la quinzaine
            # PRECEDENTE : la reglementation ne fait pas de cadeau sur la
            # quinzaine entamee.
            events.append((_quinzaine(d) - 1, -abs(montant)))
    events.sort()
    # La quinzaine en cours n'entre dans le calcul que le jour ou elle s'acheve.
    borne = end_q + 1 if _quinzaine_revolue(at_date) else end_q
    balance = accrued = 0.0
    i = 0
    for q in range(start_q, borne):
        while i < len(events) and events[i][0] <= q:
            balance += events[i][1]
            i += 1
        accrued += max(balance, 0.0) * rate
        if q == _quinzaine_credit(q // 24, mois_credit, jour_credit):
            balance += accrued
            accrued = 0.0
    while i < len(events):  # evenements posterieurs a la derniere quinzaine
        balance += events[i][1]
        i += 1
    return round(balance, 2)


def interets_prevus(asset, movements, taux_annuel, at_date=None, credit=None):
    """Interets qui seront credités a la prochaine echeance, a solde constant.

    Repond a « combien la banque me versera au 31 decembre ». C'est la
    difference entre le capital a cette echeance et le capital d'aujourd'hui :
    le moteur de `valeur_livret` sert deux fois plutot que d'etre reecrit.
    """
    at_date = parse_date(at_date) or date.today()
    if not taux_annuel:
        return 0.0
    mois, jour = _jour_credit(credit)
    echeance = date(at_date.year, mois, min(jour, calendar.monthrange(at_date.year, mois)[1]))
    if echeance < at_date:
        # L'echeance de l'annee est passee : la prochaine est l'an prochain.
        an = at_date.year + 1
        echeance = date(an, mois, min(jour, calendar.monthrange(an, mois)[1]))
    futur = valeur_livret(asset, movements, taux_annuel, echeance, credit)
    actuel = valeur_livret(asset, movements, taux_annuel, at_date, credit)
    return round(max(futur - actuel, 0.0), 2)


def valeur_capitalisee(flux, taux_annuel, at_date=None):
    """Capital place a taux fixe, interets credites en fin d'exercice.

    C'est le rythme d'un fonds euro : la participation aux benefices tombe une
    fois l'an, au 31 decembre. Un livret reglemente, lui, compte par quinzaines
    — d'ou deux fonctions et non une seule (cf. `valeur_livret`).

    `flux` est une liste de (date, montant), le montant signe : positif pour un
    versement, negatif pour un rachat. Calcul pur, sans reseau.
    """
    flux = sorted((d, m) for d, m in ((parse_date(d), float(m or 0)) for d, m in flux) if d)
    if not flux:
        return None
    at_date = parse_date(at_date) or date.today()
    if at_date < flux[0][0]:
        return 0.0

    taux = (taux_annuel or 0.0) / 100.0
    solde = 0.0
    curseur = flux[0][0]
    i = 0
    while curseur <= at_date:
        # Un exercice va jusqu'au 31 decembre, ou jusqu'a la date demandee si
        # elle tombe avant : le dernier exercice est alors partiel.
        fin = min(date(curseur.year, 12, 31), at_date)
        # Prorata temporis : un versement de novembre ne rapporte pas une annee
        # pleine. Le « +1 » compte le jour du versement lui-meme.
        base = solde * ((fin - curseur).days + 1)
        while i < len(flux) and flux[i][0] <= fin:
            jour, montant = flux[i]
            solde += montant
            base += montant * ((fin - max(jour, curseur)).days + 1)
            i += 1
        solde += taux * base / 365.0
        curseur = fin + timedelta(days=1)
    return round(solde, 2)


def frais_de(mv) -> float:
    """Frais portes par un mouvement. Zero si la colonne n'existe pas encore.

    Une base creee avant l'ajout de la colonne renvoie des lignes qui ne la
    portent pas : la migration la pose, mais un objet deja lu en memoire, non.
    """
    try:
        return abs(float(mv["frais"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        return 0.0


def invested_amount(asset, movements, at_date=None) -> float:
    """Capital net reellement investi (acquisition + versements - retraits).

    `at_date` borne les mouvements pris en compte, comme le fait
    `asset_value_at` pour la valeur. Sans cette borne, les deux fonctions ne
    parlaient pas de la meme date : la valeur d'octobre etait comparee a un
    capital investi qui incluait deja les versements de decembre, et la
    plus-value d'une date passee sortait fausse.

    Par defaut, aucune borne : le comportement d'origine, pour les appelants
    qui veulent le total sur toute la vie du produit.
    """
    at_date = parse_date(at_date)
    total = float(asset["valeur_acquisition"] or 0)
    for mv in movements:
        if at_date is not None:
            d = parse_date(mv["date"])
            if d is None or d > at_date:
                continue
        # Un frais d'acquisition fait partie du prix de revient : 1 000 EUR
        # d'achat plus 5 EUR de courtage, c'est 1 005 EUR sortis de votre poche.
        # Sur une cession, meme logique en sens inverse : vous avez recu 5 EUR
        # de moins, donc recupere moins de capital.
        if mv["type"] in ("versement", "retrait"):
            total += float(mv["montant"] or 0) + frais_de(mv)
        # Un frais AUTONOME (gestion, droits de garde) est deja pris en compte
        # par la baisse de valeur qu'il provoque. Compter aussi son montant ici
        # l'annulerait purement et simplement.
    return round(total, 2)


# --- PEA / titres ---------------------------------------------------------


def pru(movements):
    """Prix de revient moyen sur les mouvements d'achat (type versement)."""
    cost = qty = 0.0
    for mv in movements:
        if mv["type"] != "versement":
            continue
        q, p = mv["quantite"], mv["prix_unitaire"]
        if q in (None, 0) or p is None:
            continue
        # Le courtage fait partie du prix paye : l'exclure donnerait un PRU
        # plus bas que celui du releve de courtier.
        cost += float(q) * float(p) + frais_de(mv)
        qty += float(q)
    if qty <= 0:
        return None
    return round(cost / qty, 4)


def quantity_held(movements):
    qty = 0.0
    seen = False
    for mv in movements:
        if mv["quantite"] in (None, ""):
            continue
        seen = True
        q = float(mv["quantite"])
        qty += q if mv["type"] == "versement" else -abs(q)
    return round(qty, 6) if seen else None


def pru_par_ligne(movements):
    """PRU, quantite et montant investi ligne par ligne (ticker)."""
    lignes = {}
    for mv in movements:
        # `frais` compris : des frais de reseau sont preleves EN crypto, ils
        # font donc sortir des jetons. Les ignorer laissait la quantite detenue
        # au-dessus du portefeuille reel.
        #
        # Mais SEULEMENT s'ils nomment une ligne. Des frais de gestion en euros
        # ne designent aucun support : les faire entrer ici leur fabriquait une
        # ligne « (sans ticker) », a zero part, dans la liste des positions.
        if mv["type"] == "frais" and not (mv["ticker"] or "").strip():
            continue
        if mv["type"] not in ("versement", "retrait", "frais"):
            continue
        ticker = (mv["ticker"] or "").strip() or "(sans ticker)"
        lg = lignes.setdefault(ticker, {"ticker": ticker, "cost": 0.0, "qty": 0.0, "invest": 0.0})
        q = float(mv["quantite"] or 0)
        p = float(mv["prix_unitaire"] or 0)
        lg["invest"] += float(mv["montant"] or 0) + frais_de(mv)
        if mv["type"] == "versement":
            lg["cost"] += q * p + frais_de(mv)
            lg["qty"] += q
        else:
            # Vente ou frais preleves en nature : le PRU ne bouge pas, le prix
            # de revient total baisse au prorata des parts sorties (convention
            # francaise).
            sold = min(abs(q), lg["qty"]) if lg["qty"] > 0 else abs(q)
            if lg["qty"] > 0:
                lg["cost"] -= lg["cost"] * sold / lg["qty"]
            lg["qty"] -= abs(q)
    out = []
    for lg in lignes.values():
        out.append({
            "ticker": lg["ticker"],
            "quantite": round(lg["qty"], 6),
            "pru": round(lg["cost"] / lg["qty"], 4) if lg["qty"] > 0 else None,
            "investi": round(lg["invest"], 2),
        })
    return sorted(out, key=lambda x: -abs(x["investi"]))


# --- TRI / XIRR -----------------------------------------------------------


def xnpv(rate: float, flows) -> float:
    """flows = [(date, montant)] ; montant negatif = sortie de tresorerie."""
    t0 = flows[0][0]
    total = 0.0
    for d, amount in flows:
        years = (d - t0).days / 365.0
        total += amount / (1.0 + rate) ** years
    return total


def xirr(flows, lo=-0.9999, hi=10.0, tol=1e-7, max_iter=200):
    """TRI sur flux dates, par bissection (pas de dependance scipy).

    Retourne None si les flux ne permettent pas d'encadrer une racine
    (par exemple : que des versements, ou que des retraits).
    """
    flows = sorted(((parse_date(d), float(a)) for d, a in flows), key=lambda x: x[0])
    flows = [f for f in flows if f[0] is not None and abs(f[1]) > 1e-9]
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None

    f_lo, f_hi = xnpv(lo, flows), xnpv(hi, flows)
    if f_lo * f_hi > 0:
        # Elargit la borne haute avant d'abandonner.
        for candidate in (50.0, 200.0, 1000.0):
            f_hi = xnpv(candidate, flows)
            if f_lo * f_hi <= 0:
                hi = candidate
                break
        else:
            return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = xnpv(mid, flows)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return round(mid, 6)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2.0, 6)


def asset_xirr(asset, movements, current_value, at_date=None):
    """TRI d'un actif : versements en negatif, valeur actuelle en positif."""
    at_date = parse_date(at_date) or date.today()
    flows = []
    acq = parse_date(asset["date_acquisition"])
    if acq and float(asset["valeur_acquisition"] or 0) > 0:
        flows.append((acq, -float(asset["valeur_acquisition"])))
    for mv in movements:
        if mv["type"] in ("versement", "retrait"):
            flows.append((parse_date(mv["date"]),
                          -float(mv["montant"] or 0) - frais_de(mv)))
        elif mv["type"] == "frais":
            # L'argent est sorti sans rien acheter : c'est un versement a fonds
            # perdu du point de vue du rendement.
            flows.append((parse_date(mv["date"]), -abs(float(mv["montant"] or 0))))
    if not flows:
        return None
    flows.append((at_date, float(current_value or 0)))
    return xirr(flows)


# --- rendement locatif ----------------------------------------------------


def rendement_locatif_net(loyers_annuels, charges_annuelles, mensualites_annuelles, valeur_bien):
    if not valeur_bien:
        return None
    return round(
        (loyers_annuels - charges_annuelles - mensualites_annuelles) / valeur_bien, 6
    )
