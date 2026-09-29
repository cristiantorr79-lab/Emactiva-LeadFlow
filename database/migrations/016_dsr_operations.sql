BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('016_dsr_operations');

ALTER TABLE leadflow.executions ADD COLUMN subject_token text CHECK (subject_token ~ '^[0-9a-f]{64}$');

CREATE TABLE leadflow.dsr_tombstones (
 subject_token text PRIMARY KEY CHECK (subject_token ~ '^[0-9a-f]{64}$'),
 disposition text NOT NULL CHECK (disposition IN ('deleted','restricted')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE leadflow.dsr_requests (
 request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 action text NOT NULL CHECK (action IN ('locate','export','annotate','delete','restrict')),
 subject_token text NOT NULL CHECK (subject_token ~ '^[0-9a-f]{64}$'),
 status text NOT NULL CHECK (status IN ('pending','partial','completed','failed','held','ambiguous')),
 local_status text NOT NULL CHECK (local_status IN ('not_started','completed','held','ambiguous','not_found')),
 operator_id text NOT NULL CHECK (operator_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 approver_id text CHECK (approver_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 result_code text NOT NULL CHECK (result_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE leadflow.dsr_annotations (
 request_id text PRIMARY KEY REFERENCES leadflow.dsr_requests(request_id) ON DELETE CASCADE,
 annotation_code text NOT NULL CHECK (annotation_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE leadflow.dsr_provider_actions (
 request_id text NOT NULL REFERENCES leadflow.dsr_requests(request_id) ON DELETE CASCADE,
 provider text NOT NULL CHECK (provider IN ('hubspot','hunter','slack')),
 action text NOT NULL CHECK (action ~ '^[a-z][a-z0-9_-]{0,99}$'),
 status text NOT NULL CHECK (status IN ('pending','completed','failed','not_applicable')),
 technical_reference text NOT NULL CHECK (technical_reference ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'),
 result_code text NOT NULL CHECK (result_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(request_id,provider,action)
);
REVOKE ALL ON leadflow.dsr_tombstones,leadflow.dsr_requests,leadflow.dsr_annotations,leadflow.dsr_provider_actions FROM PUBLIC;

DROP FUNCTION leadflow.claim_event(text,text,text,text,text);
CREATE FUNCTION leadflow.claim_event(p_execution_id text,p_source text,p_event_id text,p_idempotency_key text,p_lead_identifier text,p_subject_token text)
RETURNS TABLE(claimed boolean,execution_id text,original_execution_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_owner_id text;
BEGIN
 IF p_subject_token!~'^[0-9a-f]{64}$' OR EXISTS(SELECT 1 FROM leadflow.dsr_tombstones t WHERE t.subject_token=p_subject_token) THEN
  RAISE EXCEPTION 'subject processing blocked' USING ERRCODE='42501';
 END IF;
 IF p_idempotency_key<>leadflow.compute_idempotency_key(p_source,p_event_id) THEN RAISE EXCEPTION 'idempotency key does not match technical identity' USING ERRCODE='22023'; END IF;
 INSERT INTO leadflow.executions(execution_id,source,lead_identifier,subject_token) VALUES(p_execution_id,p_source,p_lead_identifier,p_subject_token);
 INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES(p_execution_id,'received','validation');
 BEGIN
  UPDATE leadflow.executions e SET idempotency_key=p_idempotency_key,status='processing',stage='idempotency',updated_at=clock_timestamp() WHERE e.execution_id=p_execution_id;
  INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES(p_execution_id,'processing','idempotency');
  RETURN QUERY SELECT true,p_execution_id,NULL::text; RETURN;
 EXCEPTION WHEN unique_violation THEN
  SELECT e.execution_id INTO STRICT v_owner_id FROM leadflow.executions e WHERE e.idempotency_key=p_idempotency_key;
  UPDATE leadflow.executions e SET status='duplicate',stage='idempotency',duplicate_of=v_owner_id,finished_at=clock_timestamp(),updated_at=clock_timestamp() WHERE e.execution_id=p_execution_id;
  INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES(p_execution_id,'duplicate','idempotency');
  RETURN QUERY SELECT false,p_execution_id,v_owner_id;
 END;
END; $$;
REVOKE ALL ON FUNCTION leadflow.claim_event(text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.claim_event(text,text,text,text,text,text) TO :"app_user";

CREATE FUNCTION leadflow.execute_dsr_request(p_request_id text,p_action text,p_lead_identifier text,p_subject_token text,p_operator_id text,p_approver_id text DEFAULT NULL,p_annotation_code text DEFAULT NULL)
RETURNS TABLE(request_id text,status text,local_status text,result_code text,matched_count integer,deleted_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_count integer; v_crm_count integer; v_deleted integer:=0; v_local text; v_status text; v_code text;
BEGIN
 IF p_request_id!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$' OR p_action NOT IN ('locate','export','annotate','delete','restrict')
  OR p_lead_identifier!~'^[0-9a-f]{64}$' OR p_subject_token!~'^[0-9a-f]{64}$'
  OR p_operator_id!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$' THEN RAISE EXCEPTION 'invalid DSR request' USING ERRCODE='22023'; END IF;
 IF p_action IN ('delete','restrict') AND (p_approver_id IS NULL OR p_approver_id=p_operator_id OR p_approver_id!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$') THEN
  RAISE EXCEPTION 'independent approval required' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id) THEN
  RETURN QUERY SELECT r.request_id,r.status,r.local_status,r.result_code,0,0 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id; RETURN;
 END IF;
 SELECT count(*),count(DISTINCT crm_contact_id) FILTER(WHERE crm_contact_id IS NOT NULL) INTO v_count,v_crm_count FROM leadflow.executions WHERE lead_identifier=p_lead_identifier;
 IF p_action IN ('delete','restrict') AND v_crm_count>1 THEN v_local:='ambiguous';v_status:='ambiguous';v_code:='subject_ambiguous';
 ELSIF EXISTS(SELECT 1 FROM leadflow.executions e JOIN leadflow.retention_holds h ON h.execution_id=e.execution_id WHERE e.lead_identifier=p_lead_identifier AND h.released_at IS NULL AND h.starts_at<=clock_timestamp() AND h.review_at>clock_timestamp()) THEN v_local:='held';v_status:='held';v_code:='retention_hold';
 ELSIF v_count=0 THEN v_local:='not_found';v_status:='completed';v_code:='subject_not_found';
 ELSE
  v_local:='completed';v_status:='partial';v_code:='local_completed';
  IF p_action='annotate' THEN
   IF p_annotation_code IS NULL OR p_annotation_code!~'^[a-z][a-z0-9_-]{0,99}$' THEN RAISE EXCEPTION 'invalid annotation code' USING ERRCODE='22023'; END IF;
  ELSIF p_action='delete' THEN
   INSERT INTO leadflow.dsr_tombstones(subject_token,disposition) VALUES(p_subject_token,'deleted') ON CONFLICT(subject_token) DO UPDATE SET disposition='deleted',updated_at=clock_timestamp();
   DELETE FROM leadflow.execution_events ev USING leadflow.executions e WHERE ev.execution_id=e.execution_id AND e.lead_identifier=p_lead_identifier;
   DELETE FROM leadflow.recovery_contexts c USING leadflow.executions e WHERE c.execution_id=e.execution_id AND e.lead_identifier=p_lead_identifier;
   DELETE FROM leadflow.executions e WHERE e.lead_identifier=p_lead_identifier; GET DIAGNOSTICS v_deleted=ROW_COUNT;
  ELSIF p_action='restrict' THEN
   INSERT INTO leadflow.dsr_tombstones(subject_token,disposition) VALUES(p_subject_token,'restricted') ON CONFLICT(subject_token) DO UPDATE SET disposition='restricted',updated_at=clock_timestamp();
   UPDATE leadflow.executions e SET status='failed',error_type='authorization_error',error_code='subject_restricted',error_message='Subject processing restricted',finished_at=clock_timestamp(),updated_at=clock_timestamp(),recovery_owner=NULL,recovery_lease_until=NULL WHERE e.lead_identifier=p_lead_identifier AND e.status='processing';
  END IF;
 END IF;
 INSERT INTO leadflow.dsr_requests(request_id,action,subject_token,status,local_status,operator_id,approver_id,result_code) VALUES(p_request_id,p_action,p_subject_token,v_status,v_local,p_operator_id,p_approver_id,v_code);
 IF p_action='annotate' AND v_local='completed' THEN INSERT INTO leadflow.dsr_annotations(request_id,annotation_code) VALUES(p_request_id,p_annotation_code); END IF;
 IF v_local='completed' AND p_action IN ('locate','export','annotate','delete','restrict') THEN
  INSERT INTO leadflow.dsr_provider_actions(request_id,provider,action,status,technical_reference,result_code) VALUES
   (p_request_id,'hubspot',p_action,'pending',p_request_id||':hubspot','provider_action_pending'),
   (p_request_id,'hunter',p_action,'pending',p_request_id||':hunter','capability_not_verified'),
   (p_request_id,'slack','no_action','not_applicable',p_request_id||':slack','no_subject_data');
 END IF;
 RETURN QUERY SELECT p_request_id,v_status,v_local,v_code,v_count,v_deleted;
END; $$;
REVOKE ALL ON FUNCTION leadflow.execute_dsr_request(text,text,text,text,text,text,text) FROM PUBLIC;

CREATE FUNCTION leadflow.dsr_export_minimized(p_request_id text,p_lead_identifier text)
RETURNS TABLE(execution_id text,source text,status text,stage text,created_at timestamptz,finished_at timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
 SELECT e.execution_id,e.source,e.status,e.stage,e.created_at,e.finished_at FROM leadflow.executions e
 WHERE e.lead_identifier=p_lead_identifier AND EXISTS(SELECT 1 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id AND r.action='export' AND r.local_status='completed') ORDER BY e.created_at,e.execution_id;
$$;
REVOKE ALL ON FUNCTION leadflow.dsr_export_minimized(text,text) FROM PUBLIC;

CREATE FUNCTION leadflow.record_dsr_provider_result(p_request_id text,p_provider text,p_action text,p_status text,p_technical_reference text,p_result_code text)
RETURNS TABLE(request_id text,status text,result_code text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_code text; v_overall text;
BEGIN
 IF p_provider NOT IN ('hubspot','hunter','slack') OR p_status NOT IN ('pending','completed','failed','not_applicable')
  OR p_technical_reference!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$' THEN RAISE EXCEPTION 'invalid provider result' USING ERRCODE='22023'; END IF;
 v_code:=CASE WHEN p_result_code~'^[a-z][a-z0-9_-]{0,99}$' THEN p_result_code ELSE 'provider_error' END;
 UPDATE leadflow.dsr_provider_actions SET status=p_status,technical_reference=p_technical_reference,result_code=v_code,updated_at=clock_timestamp()
 WHERE dsr_provider_actions.request_id=p_request_id AND provider=p_provider AND action=p_action;
 IF NOT FOUND THEN RAISE EXCEPTION 'provider action not found' USING ERRCODE='22023'; END IF;
 SELECT CASE WHEN bool_and(a.status IN ('completed','not_applicable')) THEN 'completed' ELSE 'partial' END INTO v_overall
 FROM leadflow.dsr_provider_actions a WHERE a.request_id=p_request_id;
 UPDATE leadflow.dsr_requests SET status=v_overall,updated_at=clock_timestamp() WHERE dsr_requests.request_id=p_request_id;
 RETURN QUERY SELECT p_request_id,v_overall,v_code;
END; $$;
REVOKE ALL ON FUNCTION leadflow.record_dsr_provider_result(text,text,text,text,text,text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION leadflow.record_validation_failure(p_execution_id text,p_event_id text,p_source text,p_error_code text)
RETURNS TABLE(execution_id text,status text) LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF p_error_code NOT IN ('content_type','invalid_json','missing_field','invalid_type','invalid_event_id','invalid_source','invalid_email','invalid_optional_field','dsr_configuration') THEN
  RAISE EXCEPTION 'unsupported validation error code' USING ERRCODE='22023';
 END IF;
 INSERT INTO leadflow.executions(execution_id) VALUES(p_execution_id);
 INSERT INTO leadflow.execution_events(execution_id,status,stage) VALUES(p_execution_id,'received','validation');
 UPDATE leadflow.executions SET status='failed',stage='validation',error_type='validation_error',error_code=p_error_code,error_message='Request validation failed',finished_at=clock_timestamp(),updated_at=clock_timestamp() WHERE executions.execution_id=p_execution_id;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,error_type,error_code,error_message) VALUES(p_execution_id,'failed','validation','validation_error',p_error_code,'Request validation failed');
 RETURN QUERY SELECT p_execution_id,'failed'::text;
END; $$;
COMMIT;
