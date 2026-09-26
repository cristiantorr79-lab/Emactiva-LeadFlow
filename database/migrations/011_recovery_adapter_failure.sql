-- Cierre terminal oficial cuando CRM Adapter falla antes de reconciliar contacto.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('011_recovery_adapter_failure');

CREATE FUNCTION leadflow.record_recovery_crm_adapter_reconciliation(
 p_execution_id text,p_worker_id text,p_contact_id text,p_resolution text,p_retry_count integer
)
RETURNS TABLE(execution_id text,status text,crm_contact_id text,resolution text,retry_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_previous integer;
BEGIN
 SELECT e.retry_count INTO STRICT v_previous FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing'
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp() FOR UPDATE;
 IF nullif(p_contact_id,'') IS NULL OR p_resolution NOT IN ('reused','created')
    OR p_retry_count<v_previous OR p_retry_count>v_previous+2 THEN
  RAISE EXCEPTION 'invalid CRM adapter reconciliation' USING ERRCODE='22023';
 END IF;
 UPDATE leadflow.executions e SET crm_contact_id=p_contact_id,
  crm_action=CASE WHEN p_resolution='created' THEN 'created' ELSE 'updated' END,
  stage=CASE WHEN p_resolution='created' THEN 'crm_create' ELSE 'crm_lookup' END,
  retry_count=p_retry_count,updated_at=clock_timestamp()
 WHERE e.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_code,error_message)
 VALUES(p_execution_id,'processing',CASE WHEN p_resolution='created' THEN 'crm_create' ELSE 'crm_lookup' END,
  p_retry_count+1,'recovery_'||p_resolution,'CRM recovery reconciled through adapter');
 RETURN QUERY SELECT p_execution_id,'processing'::text,p_contact_id,p_resolution,p_retry_count;
END; $$;

CREATE FUNCTION leadflow.fail_recovery_crm(
 p_execution_id text,p_worker_id text,p_retry_count integer,p_error_type text,p_error_code text
)
RETURNS TABLE(execution_id text,status text,retry_count integer,error_type text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_previous integer;
BEGIN
 SELECT e.retry_count INTO STRICT v_previous FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing'
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp() FOR UPDATE;
 IF p_retry_count<v_previous OR p_retry_count>v_previous+2
    OR p_error_type NOT IN ('validation_error','authentication_error','authorization_error',
      'technical_not_found','conflict_error','rate_limit','timeout','network_error',
      'upstream_error','ambiguous_create')
    OR nullif(p_error_code,'') IS NULL THEN
  RAISE EXCEPTION 'invalid recovery CRM outcome' USING ERRCODE='22023';
 END IF;
 UPDATE leadflow.executions e SET status='failed',stage='crm_create',retry_count=p_retry_count,
  error_type=p_error_type,error_code=p_error_code,error_message='Recovery CRM failed',
  finished_at=clock_timestamp(),updated_at=clock_timestamp(),recovery_owner=NULL,recovery_lease_until=NULL
 WHERE e.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,'failed','crm_create',p_retry_count+1,p_error_type,p_error_code,'Recovery CRM failed');
 RETURN QUERY SELECT p_execution_id,'failed'::text,p_retry_count,p_error_type;
END; $$;

CREATE FUNCTION leadflow.complete_recovery_adapter(
 p_execution_id text,p_worker_id text,p_retry_count integer,p_success boolean,
 p_error_type text,p_error_code text,p_failure_stage text
)
RETURNS TABLE(execution_id text,status text,retry_count integer,error_type text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_previous integer; v_status text:=CASE WHEN p_success THEN 'success' ELSE 'failed' END; i integer;
BEGIN
 SELECT e.retry_count INTO STRICT v_previous FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing' AND e.crm_contact_id IS NOT NULL
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp() FOR UPDATE;
 IF p_retry_count<v_previous OR p_retry_count>v_previous+2 OR p_failure_stage NOT IN ('enrichment','crm_enrichment_update')
    OR (p_success AND (p_error_type IS NOT NULL OR p_error_code IS NOT NULL))
    OR (NOT p_success AND (p_error_type NOT IN ('validation_error','authentication_error','authorization_error',
      'technical_not_found','conflict_error','rate_limit','timeout','network_error','upstream_error')
      OR nullif(p_error_code,'') IS NULL)) THEN
  RAISE EXCEPTION 'invalid recovery adapter outcome' USING ERRCODE='22023';
 END IF;
 FOR i IN 1..(p_retry_count-v_previous) LOOP
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number) VALUES(p_execution_id,'retrying','enrichment',v_previous+i);
  INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number) VALUES(p_execution_id,'processing','enrichment',v_previous+i+1);
 END LOOP;
 UPDATE leadflow.executions e SET status=v_status,
  stage=CASE WHEN p_success THEN 'crm_enrichment_update' ELSE p_failure_stage END,
  enrichment_status=CASE WHEN p_success THEN 'success' ELSE 'failed' END,
  retry_count=p_retry_count,error_type=CASE WHEN p_success THEN NULL ELSE p_error_type END,
  error_code=CASE WHEN p_success THEN NULL ELSE p_error_code END,
  error_message=CASE WHEN p_success THEN NULL ELSE 'Recovery adapter failed' END,
  finished_at=clock_timestamp(),updated_at=clock_timestamp(),recovery_owner=NULL,recovery_lease_until=NULL
 WHERE e.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,v_status,CASE WHEN p_success THEN 'crm_enrichment_update' ELSE p_failure_stage END,
  p_retry_count+1,CASE WHEN p_success THEN NULL ELSE p_error_type END,
  CASE WHEN p_success THEN NULL ELSE p_error_code END,
  CASE WHEN p_success THEN NULL ELSE 'Recovery adapter failed' END);
 RETURN QUERY SELECT p_execution_id,v_status,p_retry_count,CASE WHEN p_success THEN NULL::text ELSE p_error_type END;
END; $$;

REVOKE ALL ON FUNCTION leadflow.fail_recovery_crm(text,text,integer,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.record_recovery_crm_adapter_reconciliation(text,text,text,text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.complete_recovery_adapter(text,text,integer,boolean,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.fail_recovery_crm(text,text,integer,text,text) TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.record_recovery_crm_adapter_reconciliation(text,text,text,text,integer) TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.complete_recovery_adapter(text,text,integer,boolean,text,text,text) TO :"app_user";
COMMIT;
