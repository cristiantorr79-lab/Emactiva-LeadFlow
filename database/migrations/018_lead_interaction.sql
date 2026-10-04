-- LF-008: interaction separada, recovery estructurado cifrado y checkpoints seguros.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('018_lead_interaction');

ALTER TABLE leadflow.recovery_contexts RENAME COLUMN email_ciphertext TO context_ciphertext;
ALTER TABLE leadflow.executions
 ADD COLUMN interaction_status text NOT NULL DEFAULT 'not_required'
   CHECK (interaction_status IN ('not_required','pending','ambiguous','confirmed')),
 ADD COLUMN crm_interaction_id text;
ALTER TABLE leadflow.executions DROP CONSTRAINT executions_stage_check;
ALTER TABLE leadflow.executions ADD CONSTRAINT executions_stage_check CHECK
 (stage IN ('validation','idempotency','crm_lookup','crm_create','crm_update','crm_interaction','enrichment','crm_enrichment_update','alert'));
ALTER TABLE leadflow.execution_events DROP CONSTRAINT execution_events_stage_check;
ALTER TABLE leadflow.execution_events ADD CONSTRAINT execution_events_stage_check CHECK
 (stage IN ('validation','idempotency','crm_lookup','crm_create','crm_update','crm_interaction','enrichment','crm_enrichment_update','alert'));

DROP FUNCTION leadflow.store_recovery_context(text,text,text);
CREATE FUNCTION leadflow.store_recovery_context(p_execution_id text,p_email text,p_interaction jsonb,p_secret text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,public AS $$
DECLARE v_email text:=lower(btrim(p_email)); v_interaction jsonb; v_context jsonb;
BEGIN
 IF length(p_secret)<32 OR length(v_email)>254 OR v_email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' THEN RAISE EXCEPTION 'invalid recovery context' USING ERRCODE='22023'; END IF;
 IF p_interaction IS NOT NULL AND (jsonb_typeof(p_interaction)<>'object' OR p_interaction-'interest'-'message'<>'{}'::jsonb
    OR (p_interaction ? 'interest' AND (jsonb_typeof(p_interaction->'interest')<>'string' OR length(p_interaction->>'interest') NOT BETWEEN 1 AND 100))
    OR (p_interaction ? 'message' AND (jsonb_typeof(p_interaction->'message')<>'string' OR length(p_interaction->>'message') NOT BETWEEN 1 AND 2000))) THEN
  RAISE EXCEPTION 'invalid recovery interaction' USING ERRCODE='22023';
 END IF;
 v_interaction:=CASE WHEN p_interaction IS NULL OR p_interaction='{}'::jsonb THEN NULL ELSE p_interaction END;
 v_context:=jsonb_build_object('version',1,'email',v_email)||CASE WHEN v_interaction IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('interaction',v_interaction) END;
 IF NOT EXISTS(SELECT 1 FROM leadflow.executions e WHERE e.execution_id=p_execution_id AND e.status='processing' AND e.lead_identifier=encode(public.digest(convert_to(v_email,'UTF8'),'sha256'),'hex')) THEN RAISE EXCEPTION 'recovery context does not match execution' USING ERRCODE='22023'; END IF;
 INSERT INTO leadflow.recovery_contexts(execution_id,context_ciphertext) VALUES(p_execution_id,public.pgp_sym_encrypt(v_context::text,p_secret,'cipher-algo=aes256,compress-algo=0'))
 ON CONFLICT(execution_id) DO UPDATE SET context_ciphertext=excluded.context_ciphertext,created_at=clock_timestamp();
 UPDATE leadflow.executions SET interaction_status=CASE WHEN v_interaction IS NULL THEN 'not_required' ELSE 'pending' END WHERE execution_id=p_execution_id;
 RETURN true;
END; $$;

DROP FUNCTION leadflow.get_recovery_crm_context(text,text,text);
CREATE FUNCTION leadflow.get_recovery_crm_context(p_execution_id text,p_worker_id text,p_secret text)
RETURNS TABLE(execution_id text,idempotency_key text,stage text,crm_contact_id text,retry_count integer,normalized_email text,interaction jsonb,interaction_status text,crm_interaction_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,public AS $$
DECLARE v_plain text; v_context jsonb; v_email text;
BEGIN
 IF length(p_secret)<32 THEN RETURN; END IF;
 BEGIN
  SELECT public.pgp_sym_decrypt(c.context_ciphertext,p_secret) INTO STRICT v_plain FROM leadflow.recovery_contexts c JOIN leadflow.executions e USING(execution_id)
  WHERE e.execution_id=p_execution_id AND e.status='processing' AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp();
  BEGIN v_context:=v_plain::jsonb; EXCEPTION WHEN OTHERS THEN v_context:=jsonb_build_object('version',0,'email',v_plain); END;
  IF jsonb_typeof(v_context)<>'object' OR jsonb_typeof(v_context->'email')<>'string' OR v_context-'version'-'email'-'interaction'<>'{}'::jsonb THEN RETURN; END IF;
  v_email:=v_context->>'email';
  IF v_context ? 'interaction' AND (jsonb_typeof(v_context->'interaction')<>'object' OR v_context->'interaction'-'interest'-'message'<>'{}'::jsonb) THEN RETURN; END IF;
 EXCEPTION WHEN OTHERS THEN RETURN;
 END;
 RETURN QUERY SELECT e.execution_id,e.idempotency_key,e.stage,e.crm_contact_id,e.retry_count,v_email,v_context->'interaction',e.interaction_status,e.crm_interaction_id
 FROM leadflow.executions e WHERE e.execution_id=p_execution_id AND e.lead_identifier=encode(public.digest(convert_to(v_email,'UTF8'),'sha256'),'hex');
END; $$;

CREATE FUNCTION leadflow.record_crm_contact_checkpoint(p_execution_id text,p_crm_action text,p_contact_id text,p_retry_count integer)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF p_crm_action NOT IN ('created','updated') OR nullif(p_contact_id,'') IS NULL OR p_retry_count<0 THEN RAISE EXCEPTION 'invalid CRM checkpoint' USING ERRCODE='22023'; END IF;
 UPDATE leadflow.executions SET crm_action=p_crm_action,crm_contact_id=p_contact_id,retry_count=p_retry_count,stage='crm_interaction',updated_at=clock_timestamp() WHERE execution_id=p_execution_id AND status='processing';
 IF NOT FOUND THEN RAISE EXCEPTION 'execution unavailable' USING ERRCODE='22023'; END IF;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number) VALUES(p_execution_id,'processing','crm_interaction',p_retry_count+1);
 RETURN true;
END; $$;

CREATE FUNCTION leadflow.record_interaction_outcome(p_execution_id text,p_success boolean,p_interaction_id text,p_retry_count integer,p_ambiguous boolean DEFAULT false)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF p_retry_count<0 OR (p_success AND nullif(p_interaction_id,'') IS NULL) THEN RAISE EXCEPTION 'invalid interaction outcome' USING ERRCODE='22023'; END IF;
 UPDATE leadflow.executions SET interaction_status=CASE WHEN p_success THEN 'confirmed' WHEN p_ambiguous THEN 'ambiguous' ELSE 'pending' END,
  crm_interaction_id=CASE WHEN p_success THEN p_interaction_id ELSE crm_interaction_id END,retry_count=p_retry_count,stage='crm_interaction',updated_at=clock_timestamp()
 WHERE execution_id=p_execution_id AND status='processing' AND crm_contact_id IS NOT NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'execution unavailable' USING ERRCODE='22023'; END IF;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code)
 VALUES(p_execution_id,'processing','crm_interaction',p_retry_count+1,CASE WHEN p_ambiguous THEN 'ambiguous_interaction' END,CASE WHEN p_ambiguous THEN 'ambiguous_interaction' END);
 RETURN true;
END; $$;

REVOKE ALL ON FUNCTION leadflow.store_recovery_context(text,text,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.record_crm_contact_checkpoint(text,text,text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.record_interaction_outcome(text,boolean,text,integer,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.store_recovery_context(text,text,jsonb,text),leadflow.get_recovery_crm_context(text,text,text),leadflow.record_crm_contact_checkpoint(text,text,text,integer),leadflow.record_interaction_outcome(text,boolean,text,integer,boolean) TO :"app_user";
COMMIT;
