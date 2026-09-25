-- Contexto y persistencia oficial para reconciliación CRM bajo una lease vigente.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('008_recovery_crm_reconciliation');

CREATE FUNCTION leadflow.get_recovery_crm_context(
 p_execution_id text, p_worker_id text, p_lead_identifier text
)
RETURNS TABLE(execution_id text,idempotency_key text,stage text,crm_contact_id text,retry_count integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
 SELECT e.execution_id,e.idempotency_key,e.stage,e.crm_contact_id,e.retry_count
 FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing'
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp()
   AND e.lead_identifier=p_lead_identifier AND e.idempotency_key IS NOT NULL;
$$;

CREATE FUNCTION leadflow.record_recovery_crm_reconciliation(
 p_execution_id text, p_worker_id text, p_contact_id text, p_resolution text
)
RETURNS TABLE(execution_id text,status text,crm_contact_id text,resolution text,retry_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_retry_count integer;
BEGIN
 IF nullif(p_contact_id,'') IS NULL OR p_resolution NOT IN ('reused','created') THEN
  RAISE EXCEPTION 'invalid CRM reconciliation' USING ERRCODE='22023';
 END IF;
 UPDATE leadflow.executions e
 SET crm_contact_id=p_contact_id,
     crm_action=CASE WHEN p_resolution='created' THEN 'created' ELSE 'updated' END,
     stage=CASE WHEN p_resolution='created' THEN 'crm_create' ELSE 'crm_lookup' END,
     updated_at=clock_timestamp()
 WHERE e.execution_id=p_execution_id AND e.status='processing'
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp()
 RETURNING e.retry_count INTO STRICT v_retry_count;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_code,error_message)
 VALUES(p_execution_id,'processing',
  CASE WHEN p_resolution='created' THEN 'crm_create' ELSE 'crm_lookup' END,
  v_retry_count+1,'recovery_'||p_resolution,'CRM recovery reconciled');
 RETURN QUERY SELECT p_execution_id,'processing'::text,p_contact_id,p_resolution,v_retry_count;
END; $$;

REVOKE ALL ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.record_recovery_crm_reconciliation(text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.record_recovery_crm_reconciliation(text,text,text,text) TO :"app_user";
COMMIT;
