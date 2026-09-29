-- Retención controlada: holds específicos y evidencia minimizada por ejecución de purga.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('014_retention_purge');

CREATE TABLE leadflow.retention_holds (
 hold_id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
 execution_id text REFERENCES leadflow.executions(execution_id) ON DELETE SET NULL,
 reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
 owner_id text NOT NULL CHECK (owner_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 approved_by text NOT NULL CHECK (approved_by ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 starts_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 review_at timestamptz NOT NULL,
 released_at timestamptz,
 CHECK (execution_id IS NOT NULL OR released_at IS NOT NULL),
 CHECK (review_at > starts_at),
 CHECK (review_at <= starts_at + interval '366 days'),
 CHECK (released_at IS NULL OR released_at >= starts_at)
);
CREATE INDEX retention_holds_active_idx ON leadflow.retention_holds(execution_id,review_at) WHERE released_at IS NULL;

CREATE TABLE leadflow.retention_purge_runs (
 run_id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
 completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 processing_terminalized integer NOT NULL CHECK (processing_terminalized >= 0),
 execution_events_deleted integer NOT NULL CHECK (execution_events_deleted >= 0),
 recovery_contexts_deleted integer NOT NULL CHECK (recovery_contexts_deleted >= 0),
 executions_deleted integer NOT NULL CHECK (executions_deleted >= 0),
 evidence_rows_pruned integer NOT NULL CHECK (evidence_rows_pruned >= 0)
);

REVOKE ALL ON leadflow.retention_holds,leadflow.retention_purge_runs FROM PUBLIC;

CREATE FUNCTION leadflow.purge_retained_data(
 p_success_days integer DEFAULT 90,
 p_failed_days integer DEFAULT 180,
 p_processing_days integer DEFAULT 7,
 p_batch_size integer DEFAULT 1000
)
RETURNS TABLE(
 run_id uuid,processing_terminalized integer,execution_events_deleted integer,
 recovery_contexts_deleted integer,executions_deleted integer,evidence_rows_pruned integer
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow,pg_temp AS $$
DECLARE
 v_run_id uuid:=public.gen_random_uuid();
 v_processing integer:=0; v_events integer:=0; v_contexts integer:=0;
 v_executions integer:=0; v_evidence integer:=0;
BEGIN
 IF p_success_days<30 OR p_success_days>3650
    OR p_failed_days<p_success_days OR p_failed_days>3650
    OR p_processing_days<1 OR p_processing_days>7
    OR p_batch_size<1 OR p_batch_size>10000 THEN
  RAISE EXCEPTION 'invalid retention policy' USING ERRCODE='22023';
 END IF;

 WITH stale AS (
  SELECT e.execution_id,e.stage,e.retry_count
  FROM leadflow.executions e
  WHERE e.status='processing'
    AND (e.updated_at<=clock_timestamp()-make_interval(days=>p_processing_days)
      OR EXISTS(SELECT 1 FROM leadflow.recovery_contexts c WHERE c.execution_id=e.execution_id AND c.created_at<=clock_timestamp()-make_interval(days=>p_processing_days)))
    AND NOT EXISTS(SELECT 1 FROM leadflow.retention_holds h WHERE h.execution_id=e.execution_id AND h.released_at IS NULL AND h.starts_at<=clock_timestamp() AND h.review_at>clock_timestamp())
  ORDER BY e.updated_at,e.execution_id FOR UPDATE SKIP LOCKED LIMIT p_batch_size
 ), updated AS (
  UPDATE leadflow.executions e SET status='failed',error_type='timeout',error_code='retention_processing_expired',
   error_message='Processing retention age exceeded',finished_at=clock_timestamp(),updated_at=clock_timestamp(),
   recovery_owner=NULL,recovery_lease_until=NULL
  FROM stale s WHERE e.execution_id=s.execution_id RETURNING e.execution_id,e.stage,e.retry_count
 )
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 SELECT execution_id,'failed',stage,retry_count+1,'timeout','retention_processing_expired','Processing retention age exceeded' FROM updated;
 GET DIAGNOSTICS v_processing=ROW_COUNT;

 DROP TABLE IF EXISTS pg_temp.retention_purge_targets;
 CREATE TEMP TABLE retention_purge_targets(execution_id text PRIMARY KEY) ON COMMIT DROP;
 INSERT INTO retention_purge_targets(execution_id)
 SELECT e.execution_id FROM leadflow.executions e
 WHERE e.status IN ('success','duplicate','failed') AND e.finished_at IS NOT NULL
   AND ((e.status IN ('success','duplicate') AND e.finished_at<=clock_timestamp()-make_interval(days=>p_success_days))
     OR (e.status='failed' AND e.finished_at<=clock_timestamp()-make_interval(days=>p_failed_days)))
   AND NOT EXISTS(SELECT 1 FROM leadflow.retention_holds h WHERE h.execution_id=e.execution_id AND h.released_at IS NULL AND h.starts_at<=clock_timestamp() AND h.review_at>clock_timestamp())
 ORDER BY CASE WHEN e.status='duplicate' THEN 0 ELSE 1 END,e.finished_at,e.execution_id
 LIMIT p_batch_size;

 DELETE FROM retention_purge_targets t
 WHERE EXISTS(SELECT 1 FROM leadflow.executions child WHERE child.duplicate_of=t.execution_id
   AND NOT EXISTS(SELECT 1 FROM retention_purge_targets selected WHERE selected.execution_id=child.execution_id));

 DELETE FROM leadflow.execution_events ev USING retention_purge_targets t WHERE ev.execution_id=t.execution_id;
 GET DIAGNOSTICS v_events=ROW_COUNT;
 DELETE FROM leadflow.recovery_contexts c USING retention_purge_targets t WHERE c.execution_id=t.execution_id;
 GET DIAGNOSTICS v_contexts=ROW_COUNT;
 DELETE FROM leadflow.executions e USING retention_purge_targets t WHERE e.execution_id=t.execution_id;
 GET DIAGNOSTICS v_executions=ROW_COUNT;

 DELETE FROM leadflow.retention_purge_runs r WHERE r.completed_at<clock_timestamp()-interval '180 days';
 GET DIAGNOSTICS v_evidence=ROW_COUNT;
 INSERT INTO leadflow.retention_purge_runs(run_id,processing_terminalized,execution_events_deleted,recovery_contexts_deleted,executions_deleted,evidence_rows_pruned)
 VALUES(v_run_id,v_processing,v_events,v_contexts,v_executions,v_evidence);
 RETURN QUERY SELECT v_run_id,v_processing,v_events,v_contexts,v_executions,v_evidence;
END; $$;

REVOKE ALL ON FUNCTION leadflow.purge_retained_data(integer,integer,integer,integer) FROM PUBLIC;
COMMIT;
