-- Claim mínimo de ejecuciones processing antiguas; no reanuda trabajo externo.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('007_recovery_candidates');

ALTER TABLE leadflow.executions
 ADD COLUMN recovery_owner text,
 ADD COLUMN recovery_lease_until timestamptz,
 ADD CONSTRAINT executions_recovery_lease_pair CHECK (
  (recovery_owner IS NULL) = (recovery_lease_until IS NULL)
 );

CREATE INDEX executions_recovery_candidates_idx
 ON leadflow.executions(updated_at, recovery_lease_until)
 WHERE status='processing';

CREATE FUNCTION leadflow.claim_stale_processing_executions(
 p_worker_id text, p_stale_after_seconds integer, p_lease_seconds integer, p_limit integer DEFAULT 1
)
RETURNS TABLE(
 execution_id text, idempotency_key text, stage text, crm_action text,
 crm_contact_id text, retry_count integer, recovery_owner text, recovery_lease_until timestamptz
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF nullif(btrim(p_worker_id),'') IS NULL OR length(p_worker_id)>100
    OR p_stale_after_seconds<60 OR p_stale_after_seconds>604800
    OR p_lease_seconds<30 OR p_lease_seconds>3600 OR p_limit<1 OR p_limit>100 THEN
  RAISE EXCEPTION 'invalid recovery claim parameters' USING ERRCODE='22023';
 END IF;
 RETURN QUERY
 WITH candidates AS (
  SELECT e.execution_id
  FROM leadflow.executions e
  WHERE e.status='processing'
    AND e.idempotency_key IS NOT NULL
    AND e.updated_at <= clock_timestamp()-make_interval(secs=>p_stale_after_seconds)
    AND (e.recovery_lease_until IS NULL OR e.recovery_lease_until<=clock_timestamp())
  ORDER BY e.updated_at,e.execution_id
  FOR UPDATE SKIP LOCKED
  LIMIT p_limit
 )
 UPDATE leadflow.executions e
 SET recovery_owner=p_worker_id,
     recovery_lease_until=clock_timestamp()+make_interval(secs=>p_lease_seconds)
 FROM candidates c
 WHERE e.execution_id=c.execution_id
 RETURNING e.execution_id,e.idempotency_key,e.stage,e.crm_action,
           e.crm_contact_id,e.retry_count,e.recovery_owner,e.recovery_lease_until;
END; $$;

REVOKE ALL ON FUNCTION leadflow.claim_stale_processing_executions(text,integer,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.claim_stale_processing_executions(text,integer,integer,integer) TO :"app_user";
COMMIT;
