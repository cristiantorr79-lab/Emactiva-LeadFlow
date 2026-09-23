-- Aplicación única mediante ledger transaccional; repetición deliberadamente rechazada.
BEGIN;
CREATE SCHEMA IF NOT EXISTS leadflow;
CREATE TABLE IF NOT EXISTS leadflow.schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
-- La PK impide aplicar nuevamente o concurrentemente esta versión.
INSERT INTO leadflow.schema_migrations (version) VALUES ('001_initial');

CREATE TABLE leadflow.executions (
    execution_id text PRIMARY KEY CHECK (length(execution_id) > 0),
    idempotency_key text UNIQUE CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    event_id varchar(200),
    source varchar(100),
    lead_identifier text CHECK (lead_identifier ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'received'
        CHECK (status IN ('received','processing','duplicate','retrying','success','failed')),
    stage text NOT NULL DEFAULT 'validation'
        CHECK (stage IN ('validation','idempotency','crm_lookup','crm_create','crm_update','enrichment','crm_enrichment_update','alert')),
    crm_action text CHECK (crm_action IN ('created','updated')),
    crm_contact_id text,
    enrichment_status text NOT NULL DEFAULT 'not_started'
        CHECK (enrichment_status IN ('not_started','processing','success','failed')),
    retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    error_type text,
    error_code text,
    error_message varchar(500),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    duplicate_of text REFERENCES leadflow.executions(execution_id),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK ((status IN ('success','failed','duplicate')) = (finished_at IS NOT NULL)),
    CHECK (idempotency_key IS NULL OR (event_id IS NOT NULL AND source IS NOT NULL AND lead_identifier IS NOT NULL)),
    CHECK (status NOT IN ('processing','retrying','success') OR idempotency_key IS NOT NULL),
    CHECK ((status = 'duplicate') = (duplicate_of IS NOT NULL)),
    CHECK (duplicate_of IS NULL OR (duplicate_of <> execution_id AND idempotency_key IS NULL)),
    CHECK (status <> 'success' OR (crm_contact_id IS NOT NULL AND crm_action IS NOT NULL AND enrichment_status = 'success'))
);

-- Historial compacto de intentos y alertas, sin payload del proveedor.
CREATE TABLE leadflow.execution_events (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES leadflow.executions(execution_id),
    status text NOT NULL CHECK (status IN ('received','processing','duplicate','retrying','success','failed')),
    stage text NOT NULL CHECK (stage IN ('validation','idempotency','crm_lookup','crm_create','crm_update','enrichment','crm_enrichment_update','alert')),
    attempt_number integer NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    error_type text,
    error_code text,
    error_message varchar(500),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX execution_events_execution_idx ON leadflow.execution_events (execution_id, created_at);
COMMIT;
