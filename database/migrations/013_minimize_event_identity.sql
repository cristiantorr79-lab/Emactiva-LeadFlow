-- Minimiza event_id: se usa para derivar la clave y no se persiste en el ledger.
BEGIN;
\getenv app_user POSTGRES_APP_USER

INSERT INTO leadflow.schema_migrations(version) VALUES ('013_minimize_event_identity');

ALTER TABLE leadflow.executions DROP COLUMN event_id;

CREATE OR REPLACE FUNCTION leadflow.compute_idempotency_key(p_source text, p_event_id text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    IF p_source !~ '^[a-z][a-z0-9_-]{0,63}$'
       OR p_event_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR p_event_id !~ '[0-9._:-]'
       OR p_event_id ~ '^[0-9]{7,15}$' THEN
        RAISE EXCEPTION 'invalid technical event identity' USING ERRCODE = '22023';
    END IF;
    RETURN encode(public.digest(convert_to(p_source || ':' || p_event_id, 'UTF8'), 'sha256'), 'hex');
END;
$$;

CREATE OR REPLACE FUNCTION leadflow.claim_event(
    p_execution_id text, p_source text, p_event_id text,
    p_idempotency_key text, p_lead_identifier text
)
RETURNS TABLE(claimed boolean, execution_id text, original_execution_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, leadflow AS $$
DECLARE
    v_owner_id text;
BEGIN
    IF p_idempotency_key <> leadflow.compute_idempotency_key(p_source, p_event_id) THEN
        RAISE EXCEPTION 'idempotency key does not match technical identity' USING ERRCODE = '22023';
    END IF;

    INSERT INTO leadflow.executions(execution_id, source, lead_identifier)
    VALUES (p_execution_id, p_source, p_lead_identifier);
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

CREATE OR REPLACE FUNCTION leadflow.record_validation_failure(
    p_execution_id text, p_event_id text, p_source text, p_error_code text
)
RETURNS TABLE(execution_id text, status text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, leadflow AS $$
BEGIN
    IF p_error_code NOT IN (
        'content_type', 'invalid_json', 'missing_field', 'invalid_type',
        'invalid_event_id', 'invalid_source', 'invalid_email', 'invalid_optional_field'
    ) THEN
        RAISE EXCEPTION 'unsupported validation error code' USING ERRCODE = '22023';
    END IF;

    INSERT INTO leadflow.executions(execution_id) VALUES (p_execution_id);
    INSERT INTO leadflow.execution_events(execution_id, status, stage)
    VALUES (p_execution_id, 'received', 'validation');
    UPDATE leadflow.executions AS e
    SET status = 'failed', stage = 'validation',
        error_type = 'validation_error', error_code = p_error_code,
        error_message = 'Request validation failed',
        finished_at = clock_timestamp(), updated_at = clock_timestamp()
    WHERE e.execution_id = p_execution_id;
    INSERT INTO leadflow.execution_events(execution_id, status, stage, error_type, error_code, error_message)
    VALUES (p_execution_id, 'failed', 'validation', 'validation_error', p_error_code, 'Request validation failed');
    RETURN QUERY SELECT p_execution_id, 'failed'::text;
END;
$$;

COMMIT;
