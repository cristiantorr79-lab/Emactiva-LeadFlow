-- Operación oficial para persistir fallos de validación del núcleo n8n.
BEGIN;
\getenv app_user POSTGRES_APP_USER

INSERT INTO leadflow.schema_migrations (version) VALUES ('002_n8n_core');

CREATE FUNCTION leadflow.record_validation_failure(
    p_execution_id text,
    p_event_id text,
    p_source text,
    p_error_code text
)
RETURNS TABLE(execution_id text, status text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, leadflow
AS $$
BEGIN
    IF p_error_code NOT IN (
        'content_type', 'invalid_json', 'missing_field', 'invalid_type',
        'invalid_event_id', 'invalid_source', 'invalid_email', 'invalid_optional_field'
    ) THEN
        RAISE EXCEPTION 'unsupported validation error code' USING ERRCODE = '22023';
    END IF;

    INSERT INTO leadflow.executions(execution_id, event_id, source)
    VALUES (p_execution_id, left(p_event_id, 200), left(p_source, 100));
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

REVOKE ALL ON FUNCTION leadflow.record_validation_failure(text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.record_validation_failure(text, text, text, text) TO :"app_user";
COMMIT;
