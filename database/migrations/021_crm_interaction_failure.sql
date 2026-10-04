-- LF-008: persistencia compatible y fail-closed de fallos CRM Interaction.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('021_crm_interaction_failure');

CREATE OR REPLACE FUNCTION leadflow.record_crm_failure(
 p_execution_id text, p_stage text, p_retry_count integer,
 p_error_type text, p_error_code text, p_crm_action text, p_crm_contact_id text
)
RETURNS TABLE(execution_id text, status text, error_type text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE i integer;
BEGIN
 IF p_retry_count IS NULL OR p_retry_count NOT BETWEEN 0 AND 2
    OR p_stage NOT IN ('crm_lookup','crm_create','crm_update','crm_interaction')
    OR (
      p_stage IN ('crm_lookup','crm_create','crm_update')
      AND p_error_type NOT IN ('validation_error','authentication_error','authorization_error','technical_not_found','conflict_error','rate_limit','timeout','network_error','upstream_error','ambiguous_create')
    )
    OR (
      p_stage='crm_interaction'
      AND p_error_type NOT IN ('validation_error','authentication_error','authorization_error','technical_not_found','conflict_error','rate_limit','timeout','network_error','upstream_error','ambiguous_interaction')
    ) THEN
  RAISE EXCEPTION 'invalid CRM failure' USING ERRCODE='22023';
 END IF;

 FOR i IN 1..p_retry_count LOOP
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number)
  VALUES(p_execution_id,'retrying',p_stage,i);
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number)
  VALUES(p_execution_id,'processing',p_stage,i+1);
 END LOOP;

 UPDATE leadflow.executions AS e SET
  status='failed',stage=p_stage,retry_count=p_retry_count,
  crm_action=COALESCE(p_crm_action,e.crm_action),
  crm_contact_id=COALESCE(p_crm_contact_id,e.crm_contact_id),
  error_type=p_error_type,error_code=p_error_code,error_message='CRM request failed',
  finished_at=clock_timestamp(),updated_at=clock_timestamp()
 WHERE e.execution_id=p_execution_id AND e.status='processing'
 RETURNING e.execution_id INTO STRICT p_execution_id;

 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,'failed',p_stage,p_retry_count+1,p_error_type,p_error_code,'CRM request failed');
 RETURN QUERY SELECT p_execution_id,'failed'::text,p_error_type;
END; $$;

REVOKE ALL ON FUNCTION leadflow.record_crm_failure(text,text,integer,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.record_crm_failure(text,text,integer,text,text,text,text) TO :"app_user";
COMMIT;
