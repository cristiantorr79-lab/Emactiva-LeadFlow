-- Persistencia oficial del resultado y transiciones de retries de enrichment.
BEGIN;
\getenv app_user POSTGRES_APP_USER

INSERT INTO leadflow.schema_migrations (version) VALUES ('004_enrichment_retries');

CREATE FUNCTION leadflow.record_enrichment_outcome(
    p_execution_id text,
    p_crm_action text,
    p_crm_contact_id text,
    p_retry_count integer,
    p_success boolean,
    p_error_type text,
    p_error_code text
)
RETURNS TABLE(execution_id text, status text, crm_action text, error_type text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, leadflow
AS $$
DECLARE
    v_retry integer;
    v_status text := CASE WHEN p_success THEN 'success' ELSE 'failed' END;
BEGIN
    IF p_crm_action NOT IN ('created', 'updated') OR nullif(p_crm_contact_id, '') IS NULL
       OR p_retry_count NOT BETWEEN 0 AND 2
       OR (p_success AND (p_error_type IS NOT NULL OR p_error_code IS NOT NULL))
       OR (NOT p_success AND p_error_type NOT IN ('validation_error','authentication_error','rate_limit','timeout','upstream_error')) THEN
        RAISE EXCEPTION 'invalid enrichment outcome' USING ERRCODE = '22023';
    END IF;

    FOR v_retry IN 1..p_retry_count LOOP
        INSERT INTO leadflow.execution_events(execution_id, status, stage, attempt_number)
        VALUES (p_execution_id, 'retrying', 'enrichment', v_retry);
        INSERT INTO leadflow.execution_events(execution_id, status, stage, attempt_number)
        VALUES (p_execution_id, 'processing', 'enrichment', v_retry + 1);
    END LOOP;

    UPDATE leadflow.executions AS e
    SET status = v_status, stage = CASE WHEN p_success THEN 'crm_enrichment_update' ELSE 'enrichment' END, crm_action = p_crm_action,
        crm_contact_id = p_crm_contact_id, retry_count = p_retry_count,
        enrichment_status = CASE WHEN p_success THEN 'success' ELSE 'failed' END,
        error_type = CASE WHEN p_success THEN NULL ELSE p_error_type END,
        error_code = CASE WHEN p_success THEN NULL ELSE p_error_code END,
        error_message = CASE WHEN p_success THEN NULL ELSE 'Enrichment request failed' END,
        finished_at = clock_timestamp(), updated_at = clock_timestamp()
    WHERE e.execution_id = p_execution_id AND e.status = 'processing'
    RETURNING e.execution_id INTO STRICT p_execution_id;

    INSERT INTO leadflow.execution_events(execution_id, status, stage, attempt_number, error_type, error_code, error_message)
    VALUES (p_execution_id, v_status, CASE WHEN p_success THEN 'crm_enrichment_update' ELSE 'enrichment' END, p_retry_count + 1,
            CASE WHEN p_success THEN NULL ELSE p_error_type END,
            CASE WHEN p_success THEN NULL ELSE p_error_code END,
            CASE WHEN p_success THEN NULL ELSE 'Enrichment request failed' END);

    RETURN QUERY SELECT p_execution_id, v_status, p_crm_action,
        CASE WHEN p_success THEN NULL::text ELSE p_error_type END;
END;
$$;

REVOKE ALL ON FUNCTION leadflow.record_enrichment_outcome(text, text, text, integer, boolean, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.record_enrichment_outcome(text, text, text, integer, boolean, text, text) TO :"app_user";
COMMIT;
