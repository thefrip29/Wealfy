-- Schema complet du logiciel de gestion patrimoniale.
-- Toutes les dates sont stockees en TEXT ISO 'YYYY-MM-DD'.
-- Aucune valeur derivee n'est stockee (capital restant du, patrimoine net,
-- totaux mensuels...) : tout est recalcule a la volee.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assets (
    id                  TEXT PRIMARY KEY,
    type                TEXT NOT NULL,
    label               TEXT NOT NULL,
    date_acquisition    TEXT NOT NULL,
    valeur_acquisition  REAL NOT NULL DEFAULT 0,
    valeur_actuelle     REAL,
    metadata            TEXT NOT NULL DEFAULT '{}',
    archived            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS liabilities (
    id                TEXT PRIMARY KEY,
    type              TEXT NOT NULL,
    label             TEXT NOT NULL DEFAULT '',
    asset_id          TEXT REFERENCES assets(id) ON DELETE SET NULL,
    montant_emprunte  REAL NOT NULL,
    taux_annuel       REAL NOT NULL DEFAULT 0,
    duree_mois        INTEGER NOT NULL,
    date_debut        TEXT NOT NULL,
    assurance_mensuelle REAL NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS imports (
    id             TEXT PRIMARY KEY,
    date_import    TEXT NOT NULL DEFAULT (datetime('now')),
    source         TEXT NOT NULL,
    periode_debut  TEXT,
    periode_fin    TEXT,
    nombre_lignes  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    date         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    amount       REAL NOT NULL,              -- signe : negatif = depense
    category     TEXT NOT NULL DEFAULT 'Non categorise',
    asset_id     TEXT REFERENCES assets(id) ON DELETE SET NULL,
    liability_id TEXT REFERENCES liabilities(id) ON DELETE SET NULL,
    import_id    TEXT REFERENCES imports(id) ON DELETE SET NULL,
    dedup_hash   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS asset_movements (
    id            TEXT PRIMARY KEY,
    asset_id      TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date          TEXT NOT NULL,
    montant       REAL NOT NULL,             -- signe pour versement/retrait
    type          TEXT NOT NULL,             -- versement | retrait | valorisation
    quantite      REAL,
    prix_unitaire REAL,
    ticker        TEXT,
    note          TEXT,
    -- Empreinte anti-doublon, comme sur transactions : reimporter un releve
    -- qui chevauche le precedent doublerait sinon les quantites en silence.
    -- L'index unique est cree dans db._migrate_columns, apres s'etre assure
    -- que la colonne existe (une base anterieure ne l'a pas).
    dedup_hash    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rules (
    id         TEXT PRIMARY KEY,
    pattern    TEXT NOT NULL,
    cible_type TEXT NOT NULL,                -- categorie_depense | type_revenu
    valeur     TEXT NOT NULL,
    priorite   INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL                      -- JSON
);

-- Correspondance entre la cle utilisee dans asset_movements.ticker (souvent un
-- ISIN) et le symbole attendu par le fournisseur de cours. Porte aussi
-- l'indice de reference de la ligne.
CREATE TABLE IF NOT EXISTS securities (
    id               TEXT PRIMARY KEY,
    ticker           TEXT NOT NULL UNIQUE,
    symbol           TEXT,
    exchange         TEXT,
    currency         TEXT NOT NULL DEFAULT 'EUR',
    isin             TEXT,
    label            TEXT,
    benchmark_symbol TEXT,
    benchmark_label  TEXT,
    kind             TEXT NOT NULL DEFAULT 'titre',  -- titre | crypto
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cache des donnees externes datees. Ce n'est pas une valeur derivee figee
-- (cf. section 9 du cahier des charges) : c'est une observation de marche a
-- une date, au meme titre qu'un mouvement. Elle alimente le recalcul, elle ne
-- le remplace pas.
CREATE TABLE IF NOT EXISTS quotes (
    symbol     TEXT NOT NULL,
    source     TEXT NOT NULL,
    date       TEXT NOT NULL,
    price      REAL NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'EUR',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, source, date)
);

CREATE INDEX IF NOT EXISTS idx_quotes_symbol  ON quotes(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_tx_date        ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_asset       ON transactions(asset_id);
CREATE INDEX IF NOT EXISTS idx_tx_liability   ON transactions(liability_id);
CREATE INDEX IF NOT EXISTS idx_tx_import      ON transactions(import_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_dedup ON transactions(dedup_hash) WHERE dedup_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mv_asset_date  ON asset_movements(asset_id, date);
CREATE INDEX IF NOT EXISTS idx_liab_asset     ON liabilities(asset_id);
