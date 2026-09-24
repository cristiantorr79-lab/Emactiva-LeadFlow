-- Operación oficial para cerrar exitosamente el happy path n8n.
BEGIN;
\getenv app_user POSTGRES_APP_USER

INSERT INTO leadflow.schema_migrations (version) VALUES ('003_n8n_happy_path');

CREATE FUNCTION leadflow.complete_execution_success(
    p_execution_id text,
    p_crm_action text,
    p_crm_contact_id text
)
RETURNS TABLE(execution_id text, status text, crm_action text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, leadflow
AS $$
BEGIN
    IF p_crm_action NOT IN ('created', 'updated') OR nullif(p_crm_contact_id, '') IS NULL THEN
        RAISE EXCEPTION 'invalid CRM completion data' USING ERRCODE = '22023';
    END IF;

    UPDATE leadflow.executions AS e
    SET status = 'success', stage = 'crm_enrichment_update',
        crm_action = p_crm_action, crm_contact_id = p_crm_contact_id,
        enrichment_status = 'success', finished_at = clock_timestamp(),
        updated_at = clock_timestamp()
    WHERE e.execution_id = p_execution_id AND e.status = 'processing'
    RETURNING e.execution_id INTO STRICT p_execution_id;

    INSERT INTO leadflow.execution_events(execution_id, status, stage)
    VALUES (p_execution_id, 'success', 'crm_enrichment_update');

    RETURN QUERY SELECT p_execution_id, 'success'::text, p_crm_action;
END;
$$;

REVOKE ALL ON FUNCTION leadflow.complete_execution_success(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.complete_execution_success(text, text, text) TO :"app_user";
COMMIT;
