-- LF-008: lookup de recovery sin referencias ambiguas y fail-closed criptográfico acotado.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('019_recovery_context_lookup');

CREATE OR REPLACE FUNCTION leadflow.get_recovery_crm_context(p_execution_id text,p_worker_id text,p_secret text)
RETURNS TABLE(execution_id text,idempotency_key text,stage text,crm_contact_id text,retry_count integer,normalized_email text,interaction jsonb,interaction_status text,crm_interaction_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,public AS $$
DECLARE v_plain text; v_context jsonb; v_email text;
BEGIN
 IF length(p_secret)<32 THEN RETURN; END IF;

 -- Sólo fallos de ciphertext/clave/cast se convierten deliberadamente en ausencia.
 BEGIN
  SELECT public.pgp_sym_decrypt(c.context_ciphertext,p_secret)
  INTO STRICT v_plain
  FROM leadflow.recovery_contexts AS c
  JOIN leadflow.executions AS leased_execution
    ON leased_execution.execution_id=c.execution_id
  WHERE c.execution_id=p_execution_id
    AND leased_execution.status='processing'
    AND leased_execution.recovery_owner=p_worker_id
    AND leased_execution.recovery_lease_until>clock_timestamp();
  BEGIN
   v_context:=v_plain::jsonb;
  EXCEPTION WHEN OTHERS THEN
   -- Compatibilidad de lectura con ciphertext histórico que contenía sólo email.
   v_context:=jsonb_build_object('version',0,'email',v_plain);
  END;
 EXCEPTION
  WHEN no_data_found OR too_many_rows THEN RETURN;
  WHEN OTHERS THEN RETURN;
 END;

 IF jsonb_typeof(v_context)<>'object'
    OR jsonb_typeof(v_context->'email')<>'string'
    OR v_context-'version'-'email'-'interaction'<>'{}'::jsonb THEN RETURN; END IF;
 v_email:=v_context->>'email';
 IF v_context ? 'interaction' AND
    (jsonb_typeof(v_context->'interaction')<>'object'
     OR v_context->'interaction'-'interest'-'message'<>'{}'::jsonb
     OR (v_context->'interaction' ? 'interest' AND (jsonb_typeof(v_context->'interaction'->'interest')<>'string' OR length(v_context->'interaction'->>'interest') NOT BETWEEN 1 AND 100))
     OR (v_context->'interaction' ? 'message' AND (jsonb_typeof(v_context->'interaction'->'message')<>'string' OR length(v_context->'interaction'->>'message') NOT BETWEEN 1 AND 2000))) THEN RETURN; END IF;

 RETURN QUERY
 SELECT current_execution.execution_id,current_execution.idempotency_key,current_execution.stage,
        current_execution.crm_contact_id,current_execution.retry_count,v_email,
        v_context->'interaction',current_execution.interaction_status,current_execution.crm_interaction_id
 FROM leadflow.executions AS current_execution
 WHERE current_execution.execution_id=p_execution_id
   AND current_execution.lead_identifier=encode(public.digest(convert_to(v_email,'UTF8'),'sha256'),'hex');
END; $$;

REVOKE ALL ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) TO :"app_user";
COMMIT;
