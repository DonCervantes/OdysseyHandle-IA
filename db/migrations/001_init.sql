-- KAVAK AUTOGUARD AI — esquema inicial (Postgres / Supabase). Datos SIMULADOS.
-- Equivalente a autoguard/db/models.py (SQLAlchemy crea el mismo esquema en SQLite).
-- Aplicar: psql "$DATABASE_URL" -f db/migrations/001_init.sql   (o el SQL editor de Supabase)

BEGIN;

CREATE TABLE IF NOT EXISTS vehicles (
    id           VARCHAR(64) PRIMARY KEY,
    perfil_json  JSONB       NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id              VARCHAR(64) PRIMARY KEY,
    vehicle_id      VARCHAR(64),
    tipo            VARCHAR(32) NOT NULL,
    storage_url     TEXT,                  -- bucket privado; servir con URLs firmadas
    extracted_json  JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_documents_vehicle_id ON documents (vehicle_id);

-- Sin FK a vehicles: el simulador cotiza autos cuyo perfil no se persiste.
CREATE TABLE IF NOT EXISTS predictions (
    id             VARCHAR(64)      PRIMARY KEY,
    vehicle_id     VARCHAR(64)      NOT NULL,
    agent          VARCHAR(32)      NOT NULL DEFAULT 'cotizador',
    agent_version  VARCHAR(64)      NOT NULL,
    input_hash     VARCHAR(128)     NOT NULL,
    prima          DOUBLE PRECISION NOT NULL,
    output_json    JSONB            NOT NULL,
    created_at     TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_predictions_vehicle_id ON predictions (vehicle_id);
CREATE INDEX IF NOT EXISTS ix_predictions_agent_version ON predictions (agent_version);

CREATE TABLE IF NOT EXISTS outcomes (
    id             VARCHAR(64) PRIMARY KEY,
    prediction_id  VARCHAR(64) NOT NULL,
    fuente         VARCHAR(32) NOT NULL CHECK (fuente IN ('taller', 'venta', 'siniestro', 'simulador')),
    valor_json     JSONB       NOT NULL,
    observed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_outcomes_prediction_id ON outcomes (prediction_id);

CREATE TABLE IF NOT EXISTS errors (
    id             SERIAL           PRIMARY KEY,
    prediction_id  VARCHAR(64)      NOT NULL,
    metrica        VARCHAR(32)      NOT NULL,
    valor          DOUBLE PRECISION NOT NULL,
    segmento       JSONB,
    created_at     TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_errors_prediction_id ON errors (prediction_id);

CREATE TABLE IF NOT EXISTS agent_versions (
    id            VARCHAR(64) PRIMARY KEY,
    agent         VARCHAR(32) NOT NULL,
    parent_id     VARCHAR(64) REFERENCES agent_versions (id),
    git_sha       VARCHAR(64) NOT NULL,
    estado        VARCHAR(16) NOT NULL CHECK (estado IN ('campeon', 'retador', 'sombra', 'retirado')),
    metrics_json  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_versions_agent ON agent_versions (agent);

CREATE TABLE IF NOT EXISTS patches (
    id                VARCHAR(64) PRIMARY KEY,
    generation        INTEGER     NOT NULL,
    agent             VARCHAR(32) NOT NULL DEFAULT 'cotizador',
    tipo              VARCHAR(32) NOT NULL,
    nivel             VARCHAR(16) NOT NULL,
    hipotesis         TEXT        NOT NULL DEFAULT '',
    segmento          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    cambios           JSONB       NOT NULL DEFAULT '[]'::jsonb,
    diff              TEXT        NOT NULL DEFAULT '',
    metrica_objetivo  VARCHAR(64) NOT NULL DEFAULT 'loss_asimetrica',
    veredicto         VARCHAR(16) CHECK (veredicto IN ('aceptado', 'rechazado', 'invalido')),
    metrics_before    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    metrics_after     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    razon             TEXT        NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_patches_generation ON patches (generation);
CREATE INDEX IF NOT EXISTS ix_patches_veredicto ON patches (veredicto);

CREATE TABLE IF NOT EXISTS meta_strategy (
    id               SERIAL           PRIMARY KEY,
    generation       INTEGER          NOT NULL,
    estrategia_json  JSONB            NOT NULL,   -- {"arms": {brazo: [alpha, beta]}, "lecciones": "..."}
    tasa_aceptacion  DOUBLE PRECISION NOT NULL DEFAULT 0,
    ganancia_media   DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meta_strategy_generation ON meta_strategy (generation);

-- Supabase: RLS activado sin políticas => solo service_role (backend) accede. Almacenamiento privado.
ALTER TABLE vehicles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents      ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE errors         ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE patches        ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_strategy  ENABLE ROW LEVEL SECURITY;

COMMIT;
