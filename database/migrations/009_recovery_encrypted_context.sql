-- Contexto mínimo cifrado para recovery; la clave vive únicamente en entorno.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('009_recovery_encrypted_context');

CREATE TABLE leadflow.recovery_contexts (
 execution_id text PRIMARY KEY REFERENCES leadflow.executions(execution_id) ON DELETE CASCADE,
 email_ciphertext bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON leadflow.recovery_contexts FROM PUBLIC;

CREATE FUNCTION leadflow.store_recovery_context(p_execution_id text,p_email text,p_secret text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,public AS $$
DECLARE v_email text:=lower(btrim(p_email));
BEGIN
 IF length(p_secret)<32 OR length(v_email)>254 OR v_email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' THEN
  RAISE EXCEPTION 'invalid recovery context' USING ERRCODE='22023';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM leadflow.executions e WHERE e.execution_id=p_execution_id
   AND e.status='processing' AND e.lead_identifier=encode(public.digest(convert_to(v_email,'UTF8'),'sha256'),'hex')) THEN
  RAISE EXCEPTION 'recovery context does not match execution' USING ERRCODE='22023';
 END IF;
 INSERT INTO leadflow.recovery_contexts(execution_id,email_ciphertext)
 VALUES(p_execution_id,public.pgp_sym_encrypt(v_email,p_secret,'cipher-algo=aes256,compress-algo=0'))
 ON CONFLICT(execution_id) DO UPDATE SET email_ciphertext=excluded.email_ciphertext,created_at=clock_timestamp();
 RETURN true;
END; $$;

DROP FUNCTION leadflow.get_recovery_crm_context(text,text,text);
CREATE FUNCTION leadflow.get_recovery_crm_context(p_execution_id text,p_worker_id text,p_secret text)
RETURNS TABLE(execution_id text,idempotency_key text,stage text,crm_contact_id text,retry_count integer,normalized_email text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,public AS $$
DECLARE v_email text;
BEGIN
 IF length(p_secret)<32 THEN RETURN; END IF;
 BEGIN
  SELECT public.pgp_sym_decrypt(c.email_ciphertext,p_secret) INTO STRICT v_email
  FROM leadflow.recovery_contexts c JOIN leadflow.executions e USING(execution_id)
  WHERE e.execution_id=p_execution_id AND e.status='processing'
    AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp();
 EXCEPTION WHEN OTHERS THEN RETURN;
 END;
 RETURN QUERY SELECT e.execution_id,e.idempotency_key,e.stage,e.crm_contact_id,e.retry_count,v_email
 FROM leadflow.executions e WHERE e.execution_id=p_execution_id
   AND e.lead_identifier=encode(public.digest(convert_to(v_email,'UTF8'),'sha256'),'hex');
END; $$;

CREATE FUNCTION leadflow.cleanup_recovery_context_on_terminal()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF NEW.status IN ('success','failed','duplicate') AND OLD.status IS DISTINCT FROM NEW.status THEN
  DELETE FROM leadflow.recovery_contexts c WHERE c.execution_id=NEW.execution_id;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER cleanup_recovery_context_terminal
 AFTER UPDATE OF status ON leadflow.executions FOR EACH ROW
 EXECUTE FUNCTION leadflow.cleanup_recovery_context_on_terminal();

REVOKE ALL ON FUNCTION leadflow.store_recovery_context(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.store_recovery_context(text,text,text) TO :"app_user";
GRANT EXECUTE ON FUNCTION leadflow.get_recovery_crm_context(text,text,text) TO :"app_user";
COMMIT;
