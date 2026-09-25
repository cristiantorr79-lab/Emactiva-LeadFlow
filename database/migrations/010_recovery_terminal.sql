-- Cierre terminal oficial de recovery tras reconciliación CRM y enrichment.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('010_recovery_terminal');

CREATE FUNCTION leadflow.complete_recovery_enrichment(
 p_execution_id text,p_worker_id text,p_retry_count integer,p_success boolean,p_error_type text,p_error_code text
)
RETURNS TABLE(execution_id text,status text,retry_count integer,error_type text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_previous integer; v_status text:=CASE WHEN p_success THEN 'success' ELSE 'failed' END; i integer;
BEGIN
 SELECT e.retry_count INTO STRICT v_previous FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing' AND e.crm_contact_id IS NOT NULL
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp() FOR UPDATE;
 IF p_retry_count<v_previous OR p_retry_count>v_previous+2
    OR (p_success AND (p_error_type IS NOT NULL OR p_error_code IS NOT NULL))
    OR (NOT p_success AND p_error_type NOT IN ('validation_error','authentication_error','rate_limit','timeout','upstream_error')) THEN
  RAISE EXCEPTION 'invalid recovery enrichment outcome' USING ERRCODE='22023';
 END IF;
 FOR i IN 1..(p_retry_count-v_previous) LOOP
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number)
  VALUES(p_execution_id,'retrying','enrichment',v_previous+i);
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number)
  VALUES(p_execution_id,'processing','enrichment',v_previous+i+1);
 END LOOP;
 UPDATE leadflow.executions e SET status=v_status,
  stage=CASE WHEN p_success THEN 'crm_enrichment_update' ELSE 'enrichment' END,
  enrichment_status=CASE WHEN p_success THEN 'success' ELSE 'failed' END,
  retry_count=p_retry_count,error_type=CASE WHEN p_success THEN NULL ELSE p_error_type END,
  error_code=CASE WHEN p_success THEN NULL ELSE p_error_code END,
  error_message=CASE WHEN p_success THEN NULL ELSE 'Recovery enrichment failed' END,
  finished_at=clock_timestamp(),updated_at=clock_timestamp(),recovery_owner=NULL,recovery_lease_until=NULL
 WHERE e.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,v_status,CASE WHEN p_success THEN 'crm_enrichment_update' ELSE 'enrichment' END,
  p_retry_count+1,CASE WHEN p_success THEN NULL ELSE p_error_type END,
  CASE WHEN p_success THEN NULL ELSE p_error_code END,
  CASE WHEN p_success THEN NULL ELSE 'Recovery enrichment failed' END);
 RETURN QUERY SELECT p_execution_id,v_status,p_retry_count,CASE WHEN p_success THEN NULL::text ELSE p_error_type END;
END; $$;
REVOKE ALL ON FUNCTION leadflow.complete_recovery_enrichment(text,text,integer,boolean,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.complete_recovery_enrichment(text,text,integer,boolean,text,text) TO :"app_user";
COMMIT;
