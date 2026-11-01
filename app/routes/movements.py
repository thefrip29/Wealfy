"""Mouvements d'actifs : apports, retraits, valorisations."""
from datetime import date

from flask import jsonify, request

from .. import finance, importer, market, services
from ..db import execute, get_db, new_id, query, row_to_dict
from ._blueprint import bp
from ._helpers import as_date, as_float, body, fail, month_param


@bp.get("/api/assets/<aid>/movements")
def list_movements(aid):
    return jsonify(services.get_movements(aid))


@bp.post("/api/assets/<aid>/movements")
def create_movement(aid):
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    data = body()
    mtype = (data.get("type") or "versement").strip()
    if mtype not in ("versement", "retrait", "valorisation", "frais"):
        return fail("Type de mouvement inconnu.")
    montant = as_float(data.get("montant"))
    if montant is None:
        return fail("Montant invalide.")
    if mtype == "versement":
        montant = abs(montant)
    elif mtype in ("retrait", "frais"):
        # Un frais autonome sort du produit, comme un retrait : c'est la baisse
        # de valeur qu'il provoque qui le fait apparaitre dans les comptes.
        montant = -abs(montant)
    # Frais PORTES par ce mouvement — le courtage d'un achat, les frais de
    # reseau d'un envoi. Ils n'entrent pas dans `montant` : cet argent n'est pas
    # alle dans le produit.
    frais = abs(as_float(data.get("frais"), 0.0) or 0.0)
    mid = new_id()
    execute(
        "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
        "prix_unitaire, ticker, frais, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            mid, aid, as_date(data.get("date"), date.today().isoformat()),
            round(montant, 2), mtype,
            as_float(data.get("quantite"), None), as_float(data.get("prix_unitaire"), None),
            (data.get("ticker") or "").strip() or None,
            round(frais, 2),
            (data.get("note") or "").strip() or None,
        ),
    )
    return jsonify(row_to_dict(
        query("SELECT * FROM asset_movements WHERE id = ?", (mid,), one=True)
    )), 201


@bp.delete("/api/movements/<mid>")
def delete_movement(mid):
    execute("DELETE FROM asset_movements WHERE id = ?", (mid,))
    return jsonify({"ok": True})


@bp.post("/api/assets/<aid>/movements/preview")
def preview_movements(aid):
    """Previsualise un releve de titres colle (Trade Republic, courtier...).

    Marque les lignes deja presentes : un releve se reimporte souvent avec un
    chevauchement de periode, et un doublon fausserait la quantite detenue.
    """
    if not services.get_asset(aid):
        return fail("Actif introuvable.", 404)
    lines, warnings = importer.parse_movements(body().get("text") or "")

    existing = {r["dedup_hash"] for r in query(
        "SELECT dedup_hash FROM asset_movements WHERE dedup_hash IS NOT NULL"
    )}
    securities = market.securities_by_ticker()
    seen, doublons, sans_symbole = set(), 0, set()
    for line in lines:
        montant = line.get("montant")
        if montant is None and line.get("quantite") and line.get("prix_unitaire"):
            montant = line["quantite"] * line["prix_unitaire"]
        h = importer.movement_hash(
            aid, line["date"], line.get("ticker"), line.get("quantite"), montant)
        duplicate = h in existing or h in seen
        seen.add(h)
        if duplicate:
            doublons += 1
        ticker = (line.get("ticker") or "").strip()
        if ticker and not (securities.get(ticker) or {}).get("symbol"):
            sans_symbole.add(ticker)
        line["hash"] = h
        line["doublon"] = duplicate
        line["ignore"] = duplicate

    return jsonify({
        "lignes": lines,
        "avertissements": warnings,
        "total": len(lines),
        "doublons": doublons,
        "tickers_sans_symbole": sorted(sans_symbole),
    })


@bp.post("/api/assets/<aid>/movements/confirm")
def confirm_movements(aid):
    """Enregistre les mouvements d'un releve de titres.

    Les quantites detenues, le PRU et la valorisation des lignes en decoulent
    automatiquement : ils sont recalcules depuis les mouvements a chaque
    affichage, jamais stockes.
    """
    asset = services.get_asset(aid)
    if not asset:
        return fail("Actif introuvable.", 404)
    lines = body().get("lignes") or []
    kind = "crypto" if asset["type"] in market.CRYPTO_ASSET_TYPES else "titre"
    securities = market.securities_by_ticker()

    created, ignores, mappes = 0, 0, []
    for line in lines:
        if line.get("ignore"):
            ignores += 1
            continue
        montant = as_float(line.get("montant"))
        quantite = as_float(line.get("quantite"))
        prix = as_float(line.get("prix_unitaire"))
        if montant is None and quantite is not None and prix is not None:
            montant = quantite * prix
        if montant is None:
            ignores += 1
            continue
        mtype = line.get("type") or ("retrait" if montant < 0 else "versement")
        montant = abs(montant) if mtype == "versement" else -abs(montant)
        ticker = (line.get("ticker") or "").strip() or None
        d = as_date(line.get("date"), date.today().isoformat())

        # Sans correspondance de symbole, une ligne importee reste non cotable
        # et fait retomber tout le compte sur sa valeur saisie. On l'amorce ici
        # avec le ticker du releve ; l'utilisateur l'affine si besoin.
        if ticker and not (securities.get(ticker) or {}).get("symbol"):
            market.upsert_security(ticker, symbol=ticker, kind=kind,
                                   label=(line.get("label") or "").strip() or None)
            securities = market.securities_by_ticker()
            mappes.append(ticker)

        h = line.get("hash") or importer.movement_hash(aid, d, ticker, quantite, montant)
        try:
            execute(
                "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
                "prix_unitaire, ticker, note, dedup_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    new_id(), aid, d, round(montant, 2), mtype, quantite, prix,
                    ticker, (line.get("note") or "").strip() or None, h,
                ),
            )
            created += 1
        except Exception:      # doublon rattrape par l'index unique
            ignores += 1

    return jsonify({
        "ok": True, "crees": created, "ignorees": ignores,
        "symboles_amorces": sorted(set(mappes)),
    })


# Ce qui ne se garnit pas d'un versement mensuel : un bien se valorise, un
# compte courant n'est pas de l'epargne (`services._versements` l'ecarte).
_HORS_VERSEMENTS = {"Immobilier", "SCPI", "Vehicule", "CompteCourant"}


def _supports_du_mois(year, month):
    """Les produits ouverts a la fin du mois, avec ce qui y est deja verse."""
    debut, fin = finance.month_bounds(year, month)
    at = min(fin, date.today())
    ctx = services.market_context(at)
    groupes = services.movements_by_asset()
    supports = []
    for a in services.get_assets(False):
        if a["type"] in _HORS_VERSEMENTS:
            continue
        mvts = groupes.get(a["id"], [])
        deja = sum(
            float(m["montant"] or 0) for m in mvts
            if m["type"] == "versement" and debut.isoformat() <= (m["date"] or "") <= fin.isoformat()
        )
        lignes = [
            {"ticker": l["ticker"], "libelle": l.get("libelle") or l["ticker"],
             "kind": l.get("kind") or "titre", "cours": l.get("cours")}
            for l in market.line_values(mvts, ctx["securities"], ctx["prices"], at)
            if l["ticker"] != "(sans ticker)"
            and ((l["quantite"] or 0) > 0 or l.get("kind") == market.NON_COTE)
        ]
        supports.append({
            "id": a["id"], "label": a["label"], "type": a["type"],
            "deja_verse": round(deja, 2), "lignes": lignes,
        })
    return supports


@bp.get("/api/versements-du-mois")
def versements_du_mois():
    """De quoi saisir en une fois l'epargne d'un mois, support par support.

    Le salaire d'octobre tombe fin octobre et s'investit debut novembre : par
    defaut, c'est le mois ecoule qu'on garnit, et le versement est date de son
    dernier jour pour compter dans l'epargne de ce mois-la.
    """
    year, month = month_param("mois")
    if "mois" not in request.args:
        today = date.today()
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    _, fin = finance.month_bounds(year, month)
    return jsonify({
        "mois": f"{year:04d}-{month:02d}",
        "date": min(fin, date.today()).isoformat(),
        "supports": _supports_du_mois(year, month),
    })


@bp.post("/api/versements-du-mois")
def enregistrer_versements_du_mois():
    """Enregistre plusieurs versements d'un coup, tous ou aucun.

    Sur un produit qui a des lignes (PEA, assurance vie, crypto), le versement
    doit nommer sa ligne : sans ticker, il creait une ligne « (sans ticker) » a
    zero part et faisait retomber tout le compte sur sa valeur saisie. Une
    ligne cotee demande aussi la quantite achetee.
    """
    data = body()
    d = as_date(data.get("date"))
    if not d:
        return fail("Date invalide.")
    supports = {s["id"]: s for s in _supports_du_mois(*map(int, d.split("-")[:2]))}

    a_creer = []
    for v in data.get("versements") or []:
        montant = as_float(v.get("montant"))
        if not montant:
            continue
        s = supports.get(v.get("asset_id"))
        if not s:
            return fail("Produit introuvable ou ferme a cette date.")
        if montant < 0:
            return fail(f"{s['label']} : un versement est un montant positif.")
        ticker = (v.get("ticker") or "").strip() or None
        quantite = prix = None
        if s["lignes"]:
            ligne = next((l for l in s["lignes"] if l["ticker"] == ticker), None)
            if not ligne:
                return fail(f"{s['label']} : choisissez la ligne qui recoit le versement.")
            if ligne["kind"] != market.NON_COTE:
                quantite = as_float(v.get("quantite"))
                if not quantite or quantite <= 0:
                    return fail(f"{s['label']} : indiquez la quantite achetee.")
                prix = round(montant / quantite, 8)
        a_creer.append((s["id"], round(abs(montant), 2), quantite, prix, ticker))

    if not a_creer:
        return fail("Aucun montant saisi.")
    db = get_db()
    for aid, montant, quantite, prix, ticker in a_creer:
        db.execute(
            "INSERT INTO asset_movements(id, asset_id, date, montant, type, quantite, "
            "prix_unitaire, ticker, frais, note) VALUES (?,?,?,?,'versement',?,?,?,0,?)",
            (new_id(), aid, d, montant, quantite, prix, ticker, "Versement du mois"),
        )
    db.commit()
    return jsonify({"ok": True, "crees": len(a_creer),
                    "total": round(sum(x[1] for x in a_creer), 2)}), 201
