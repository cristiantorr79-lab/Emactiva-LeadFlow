-- Terminalización acotada de la ejecución recovery invocada cuando supera el máximo técnico.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('012_recovery_expiration');

CREATE FUNCTION leadflow.expire_stale_recovery(
 p_execution_id text,p_worker_id text,p_max_age_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_retry_count integer; v_stage text;
BEGIN
 IF nullif(btrim(p_worker_id),'') IS NULL OR length(p_worker_id)>100
    OR p_max_age_seconds<60 OR p_max_age_seconds>604800 THEN
  RAISE EXCEPTION 'invalid recovery expiration parameters' USING ERRCODE='22023';
 END IF;
 SELECT e.retry_count,e.stage INTO v_retry_count,v_stage
 FROM leadflow.executions e
 WHERE e.execution_id=p_execution_id AND e.status='processing'
   AND e.recovery_owner=p_worker_id AND e.recovery_lease_until>clock_timestamp()
   AND e.updated_at<=clock_timestamp()-make_interval(secs=>p_max_age_seconds)
 FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE leadflow.executions e SET status='failed',
  error_type='timeout',error_code='recovery_expired',error_message='Recovery processing age exceeded',
  finished_at=clock_timestamp(),updated_at=clock_timestamp(),
  recovery_owner=NULL,recovery_lease_until=NULL
 WHERE e.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,'failed',v_stage,v_retry_count+1,'timeout','recovery_expired','Recovery processing age exceeded');
 RETURN true;
END; $$;

REVOKE ALL ON FUNCTION leadflow.expire_stale_recovery(text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.expire_stale_recovery(text,text,integer) TO :"app_user";
COMMIT;
