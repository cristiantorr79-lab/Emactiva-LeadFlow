BEGIN;
\getenv migrator_user POSTGRES_MIGRATOR_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('024_dsr_restore_evidence');

CREATE TABLE leadflow.dsr_restore_evidence_outbox (
 request_id text PRIMARY KEY REFERENCES leadflow.dsr_requests(request_id) ON DELETE RESTRICT,
 subject_token text NOT NULL CHECK (subject_token ~ '^[0-9a-f]{64}$'),
 disposition text NOT NULL CHECK (disposition IN ('deleted','restricted')),
 effective_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','staged','pending_confirmation','failed')),
 evidence_id text CHECK (evidence_id ~ '^[0-9a-f]{64}$'),
 attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
 result_code text NOT NULL DEFAULT 'awaiting_stage' CHECK (result_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON leadflow.dsr_restore_evidence_outbox FROM PUBLIC;

CREATE FUNCTION leadflow.capture_dsr_restore_evidence_outbox()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_disposition text;
BEGIN
 IF NEW.action IN ('delete','restrict') AND NEW.local_status IN ('completed','not_found') THEN
  v_disposition:=CASE WHEN NEW.action='delete' THEN 'deleted' ELSE 'restricted' END;
  INSERT INTO leadflow.dsr_tombstones(subject_token,disposition) VALUES(NEW.subject_token,v_disposition)
  ON CONFLICT ON CONSTRAINT dsr_tombstones_pkey DO UPDATE SET disposition=CASE WHEN leadflow.dsr_tombstones.disposition='deleted' OR EXCLUDED.disposition='deleted' THEN 'deleted' ELSE 'restricted' END,updated_at=CASE WHEN leadflow.dsr_tombstones.disposition=EXCLUDED.disposition OR leadflow.dsr_tombstones.disposition='deleted' THEN leadflow.dsr_tombstones.updated_at ELSE clock_timestamp() END;
  INSERT INTO leadflow.dsr_restore_evidence_outbox(request_id,subject_token,disposition,effective_at)
  SELECT NEW.request_id,t.subject_token,t.disposition,t.updated_at FROM leadflow.dsr_tombstones t WHERE t.subject_token=NEW.subject_token;
 END IF;
 RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION leadflow.capture_dsr_restore_evidence_outbox() FROM PUBLIC;
CREATE TRIGGER capture_dsr_restore_evidence_outbox AFTER INSERT ON leadflow.dsr_requests FOR EACH ROW EXECUTE FUNCTION leadflow.capture_dsr_restore_evidence_outbox();

INSERT INTO leadflow.dsr_tombstones(subject_token,disposition,created_at,updated_at)
SELECT r.subject_token,CASE WHEN bool_or(r.action='delete') THEN 'deleted' ELSE 'restricted' END,min(r.updated_at),max(r.updated_at) FROM leadflow.dsr_requests r
WHERE r.action IN ('delete','restrict') AND r.local_status IN ('completed','not_found') GROUP BY r.subject_token
ON CONFLICT ON CONSTRAINT dsr_tombstones_pkey DO UPDATE SET disposition=CASE WHEN leadflow.dsr_tombstones.disposition='deleted' OR EXCLUDED.disposition='deleted' THEN 'deleted' ELSE 'restricted' END,created_at=LEAST(leadflow.dsr_tombstones.created_at,EXCLUDED.created_at),updated_at=GREATEST(leadflow.dsr_tombstones.updated_at,EXCLUDED.updated_at);
INSERT INTO leadflow.dsr_restore_evidence_outbox(request_id,subject_token,disposition,effective_at)
SELECT r.request_id,t.subject_token,t.disposition,t.updated_at FROM leadflow.dsr_requests r JOIN leadflow.dsr_tombstones t ON t.subject_token=r.subject_token
WHERE r.action IN ('delete','restrict') AND r.local_status IN ('completed','not_found') ON CONFLICT(request_id) DO NOTHING;

CREATE FUNCTION leadflow.prepare_dsr_restore_evidence(p_request_id text)
RETURNS TABLE(subject_token text,disposition text,effective_at_utc text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_request leadflow.dsr_requests%ROWTYPE; v_disposition text;
BEGIN
 SELECT * INTO v_request FROM leadflow.dsr_requests WHERE request_id=p_request_id FOR UPDATE;
 IF NOT FOUND OR v_request.action NOT IN ('delete','restrict') OR v_request.local_status NOT IN ('completed','not_found') THEN
  RAISE EXCEPTION 'DSR request is not eligible for restore evidence' USING ERRCODE='22023';
 END IF;
 v_disposition:=CASE WHEN v_request.action='delete' THEN 'deleted' ELSE 'restricted' END;
 INSERT INTO leadflow.dsr_tombstones(subject_token,disposition) VALUES(v_request.subject_token,v_disposition)
 ON CONFLICT ON CONSTRAINT dsr_tombstones_pkey DO UPDATE SET
  disposition=CASE WHEN leadflow.dsr_tombstones.disposition='deleted' OR EXCLUDED.disposition='deleted' THEN 'deleted' ELSE 'restricted' END,
  updated_at=CASE WHEN leadflow.dsr_tombstones.disposition=EXCLUDED.disposition OR leadflow.dsr_tombstones.disposition='deleted' THEN leadflow.dsr_tombstones.updated_at ELSE clock_timestamp() END;
 INSERT INTO leadflow.dsr_restore_evidence_outbox(request_id,subject_token,disposition,effective_at)
 SELECT v_request.request_id,t.subject_token,t.disposition,t.updated_at FROM leadflow.dsr_tombstones t WHERE t.subject_token=v_request.subject_token
 ON CONFLICT(request_id) DO NOTHING;
 IF EXISTS(SELECT 1 FROM leadflow.dsr_restore_evidence_outbox o WHERE o.request_id=v_request.request_id AND (o.subject_token<>v_request.subject_token OR o.disposition<>v_disposition AND NOT (o.disposition='deleted' AND v_disposition='restricted'))) THEN
  RAISE EXCEPTION 'DSR restore outbox conflict' USING ERRCODE='23514';
 END IF;
 RETURN QUERY SELECT t.subject_token,t.disposition,to_char(t.updated_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') FROM leadflow.dsr_tombstones t WHERE t.subject_token=v_request.subject_token;
END; $$;
REVOKE ALL ON FUNCTION leadflow.prepare_dsr_restore_evidence(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.prepare_dsr_restore_evidence(text) TO :"migrator_user";

CREATE FUNCTION leadflow.record_dsr_restore_evidence(p_request_id text,p_state text,p_evidence_id text,p_result_code text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF p_state NOT IN ('staged','pending_confirmation','failed') OR p_result_code!~'^[a-z][a-z0-9_-]{0,99}$' OR (p_evidence_id IS NOT NULL AND p_evidence_id!~'^[0-9a-f]{64}$') THEN RAISE EXCEPTION 'invalid DSR restore outbox result' USING ERRCODE='22023'; END IF;
 UPDATE leadflow.dsr_restore_evidence_outbox SET state=p_state,evidence_id=COALESCE(evidence_id,p_evidence_id),attempt_count=attempt_count+1,result_code=p_result_code,updated_at=clock_timestamp()
 WHERE request_id=p_request_id AND (evidence_id IS NULL OR p_evidence_id IS NULL OR evidence_id=p_evidence_id);
 IF NOT FOUND THEN RAISE EXCEPTION 'DSR restore outbox entry missing or conflicting' USING ERRCODE='23514'; END IF;
END; $$;
REVOKE ALL ON FUNCTION leadflow.record_dsr_restore_evidence(text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.record_dsr_restore_evidence(text,text,text,text) TO :"migrator_user";

CREATE FUNCTION leadflow.get_dsr_restore_evidence(p_request_id text)
RETURNS TABLE(subject_token text,disposition text,effective_at_utc text,state text,evidence_id text)
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
 SELECT o.subject_token,o.disposition,to_char(o.effective_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),o.state,o.evidence_id
 FROM leadflow.dsr_restore_evidence_outbox o WHERE o.request_id=p_request_id AND o.state IN ('pending','staged','pending_confirmation','failed');
$$;
REVOKE ALL ON FUNCTION leadflow.get_dsr_restore_evidence(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.get_dsr_restore_evidence(text) TO :"migrator_user";

CREATE FUNCTION leadflow.replay_dsr_restore_evidence(p_events jsonb)
RETURNS TABLE(applied_count integer,verified_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_event jsonb; v_token text; v_disposition text; v_effective timestamptz; v_applied integer:=0; v_verified integer:=0;
BEGIN
 IF jsonb_typeof(p_events)<>'array' OR jsonb_array_length(p_events)>1000000 THEN RAISE EXCEPTION 'invalid DSR restore evidence' USING ERRCODE='22023'; END IF;
 FOR v_event IN SELECT value FROM jsonb_array_elements(p_events) LOOP
  IF jsonb_typeof(v_event)<>'object' OR NOT (v_event ?& ARRAY['version','evidence_id','subject_token','disposition','effective_at_utc']) OR (SELECT count(*) FROM jsonb_object_keys(v_event))<>5 THEN RAISE EXCEPTION 'invalid DSR restore event' USING ERRCODE='22023'; END IF;
  v_token:=v_event->>'subject_token'; v_disposition:=v_event->>'disposition';
  IF v_event->>'version'<>'LF015-DSR-1' OR v_event->>'evidence_id'!~'^[0-9a-f]{64}$' OR v_token!~'^[0-9a-f]{64}$' OR v_disposition NOT IN ('deleted','restricted') THEN RAISE EXCEPTION 'invalid DSR restore event' USING ERRCODE='22023'; END IF;
  BEGIN v_effective:=(v_event->>'effective_at_utc')::timestamptz; EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'invalid DSR restore timestamp' USING ERRCODE='22023'; END;
  IF v_effective>clock_timestamp()+interval '5 minutes' THEN RAISE EXCEPTION 'future DSR restore event' USING ERRCODE='22023'; END IF;
  INSERT INTO leadflow.dsr_tombstones(subject_token,disposition,created_at,updated_at) VALUES(v_token,v_disposition,v_effective,v_effective)
  ON CONFLICT ON CONSTRAINT dsr_tombstones_pkey DO UPDATE SET
   disposition=CASE WHEN leadflow.dsr_tombstones.disposition='deleted' OR EXCLUDED.disposition='deleted' THEN 'deleted' WHEN EXCLUDED.updated_at>=leadflow.dsr_tombstones.updated_at THEN EXCLUDED.disposition ELSE leadflow.dsr_tombstones.disposition END,
   created_at=LEAST(leadflow.dsr_tombstones.created_at,EXCLUDED.created_at),updated_at=GREATEST(leadflow.dsr_tombstones.updated_at,EXCLUDED.updated_at);
  v_applied:=v_applied+1;
 END LOOP;
 SELECT count(*) INTO v_verified FROM jsonb_array_elements(p_events) e
 JOIN leadflow.dsr_tombstones t ON t.subject_token=e->>'subject_token'
 WHERE (e->>'disposition'='restricted' AND t.disposition IN ('restricted','deleted') OR e->>'disposition'='deleted' AND t.disposition='deleted') AND t.updated_at>=(e->>'effective_at_utc')::timestamptz;
 IF v_verified<>jsonb_array_length(p_events) THEN RAISE EXCEPTION 'DSR restore evidence verification failed' USING ERRCODE='23514'; END IF;
 RETURN QUERY SELECT v_applied,v_verified;
END; $$;
REVOKE ALL ON FUNCTION leadflow.replay_dsr_restore_evidence(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.replay_dsr_restore_evidence(jsonb) TO :"migrator_user";

CREATE FUNCTION leadflow.verify_dsr_restore_enforcement(p_events jsonb)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_event jsonb; v_token text; v_index integer:=0; v_blocked boolean;
BEGIN
 IF jsonb_typeof(p_events)<>'array' OR jsonb_array_length(p_events)>1000000 THEN RAISE EXCEPTION 'invalid DSR enforcement evidence' USING ERRCODE='22023'; END IF;
 FOR v_event IN SELECT value FROM jsonb_array_elements(p_events) LOOP
  v_token:=v_event->>'subject_token'; v_blocked:=false;
  IF v_token!~'^[0-9a-f]{64}$' OR v_event->>'disposition' NOT IN ('deleted','restricted') THEN RAISE EXCEPTION 'invalid DSR enforcement event' USING ERRCODE='22023'; END IF;
  BEGIN
   PERFORM * FROM leadflow.claim_event('dsr-restore-check-'||v_index::text,'website','dsr-restore-check-'||v_index::text,leadflow.compute_idempotency_key('website','dsr-restore-check-'||v_index::text),repeat('0',64),v_token);
  EXCEPTION WHEN insufficient_privilege THEN v_blocked:=true;
  END;
  IF NOT v_blocked THEN RAISE EXCEPTION 'DSR enforcement verification failed' USING ERRCODE='23514'; END IF;
  v_index:=v_index+1;
 END LOOP;
 RETURN v_index;
END; $$;
REVOKE ALL ON FUNCTION leadflow.verify_dsr_restore_enforcement(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.verify_dsr_restore_enforcement(jsonb) TO :"migrator_user";
COMMIT;
