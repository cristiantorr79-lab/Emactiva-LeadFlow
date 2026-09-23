-- Aplicación única mediante ledger transaccional; repetición deliberadamente rechazada.
BEGIN;
CREATE SCHEMA IF NOT EXISTS leadflow;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\getenv app_user POSTGRES_APP_USER
\getenv app_password POSTGRES_APP_PASSWORD
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
    THEN format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
    ELSE format('ALTER ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
END \gexec
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

CREATE FUNCTION leadflow.compute_idempotency_key(p_source text, p_event_id text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    IF p_source !~ '^[A-Za-z0-9_-]{1,100}$' OR length(p_event_id) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'invalid source or event_id' USING ERRCODE = '22023';
    END IF;
    RETURN encode(public.digest(convert_to(p_source || ':' || p_event_id, 'UTF8'), 'sha256'), 'hex');
END;
$$;

CREATE FUNCTION leadflow.claim_event(
    p_execution_id text, p_source text, p_event_id text,
    p_idempotency_key text, p_lead_identifier text
)
RETURNS TABLE(claimed boolean, execution_id text, original_execution_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, leadflow AS $$
DECLARE
    v_owner_id text;
BEGIN
    IF p_idempotency_key <> leadflow.compute_idempotency_key(p_source, p_event_id) THEN
        RAISE EXCEPTION 'idempotency key does not match source and event_id' USING ERRCODE = '22023';
    END IF;

    INSERT INTO leadflow.executions(execution_id, event_id, source, lead_identifier)
    VALUES (p_execution_id, p_event_id, p_source, p_lead_identifier);
    INSERT INTO leadflow.execution_events(execution_id, status, stage)
    VALUES (p_execution_id, 'received', 'validation');

    BEGIN
        UPDATE leadflow.executions AS e
        SET idempotency_key = p_idempotency_key, status = 'processing',
            stage = 'idempotency', updated_at = clock_timestamp()
        WHERE e.execution_id = p_execution_id;
        INSERT INTO leadflow.execution_events(execution_id, status, stage)
        VALUES (p_execution_id, 'processing', 'idempotency');
        RETURN QUERY SELECT true, p_execution_id, NULL::text;
        RETURN;
    EXCEPTION WHEN unique_violation THEN
        SELECT e.execution_id INTO STRICT v_owner_id
        FROM leadflow.executions AS e
        WHERE e.idempotency_key = p_idempotency_key;
        UPDATE leadflow.executions AS e
        SET status = 'duplicate', stage = 'idempotency', duplicate_of = v_owner_id,
            finished_at = clock_timestamp(), updated_at = clock_timestamp()
        WHERE e.execution_id = p_execution_id;
        INSERT INTO leadflow.execution_events(execution_id, status, stage)
        VALUES (p_execution_id, 'duplicate', 'idempotency');
        RETURN QUERY SELECT false, p_execution_id, v_owner_id;
    END;
END;
$$;

REVOKE ALL ON SCHEMA leadflow FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA leadflow FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA leadflow FROM PUBLIC;
GRANT USAGE ON SCHEMA leadflow TO :"app_user";
GRANT SELECT ON leadflow.executions, leadflow.execution_events TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.compute_idempotency_key(text, text) TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.claim_event(text, text, text, text, text) TO :"app_user";
COMMIT;
