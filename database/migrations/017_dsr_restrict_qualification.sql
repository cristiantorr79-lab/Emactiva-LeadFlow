BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('017_dsr_restrict_qualification');

CREATE OR REPLACE FUNCTION leadflow.execute_dsr_request(p_request_id text,p_action text,p_lead_identifier text,p_subject_token text,p_operator_id text,p_approver_id text DEFAULT NULL,p_annotation_code text DEFAULT NULL)
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


COMMIT;
