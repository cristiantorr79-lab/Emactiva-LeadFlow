BEGIN;
INSERT INTO leadflow.schema_migrations(version) VALUES ('022_dsr_hubspot_nondestructive');

ALTER TABLE leadflow.dsr_requests DROP CONSTRAINT dsr_requests_action_check;
ALTER TABLE leadflow.dsr_requests ADD CONSTRAINT dsr_requests_action_check
 CHECK (action IN ('locate','export','correct','annotate','delete','restrict'));

ALTER FUNCTION leadflow.execute_dsr_request(text,text,text,text,text,text,text)
 RENAME TO execute_dsr_request_legacy;

CREATE FUNCTION leadflow.execute_dsr_request(p_request_id text,p_action text,p_lead_identifier text,p_subject_token text,p_operator_id text,p_approver_id text DEFAULT NULL,p_annotation_code text DEFAULT NULL)
RETURNS TABLE(request_id text,status text,local_status text,result_code text,matched_count integer,deleted_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_count integer; v_deleted integer:=0; v_local text; v_status text; v_code text;
BEGIN
 IF p_action NOT IN ('locate','export','correct','delete','restrict') THEN
  RETURN QUERY SELECT * FROM leadflow.execute_dsr_request_legacy(p_request_id,p_action,p_lead_identifier,p_subject_token,p_operator_id,p_approver_id,p_annotation_code);
  RETURN;
 END IF;
 IF p_action IN ('locate','export','delete','restrict') THEN
  SELECT legacy.status,legacy.local_status,legacy.result_code,legacy.matched_count,legacy.deleted_count
   INTO v_status,v_local,v_code,v_count,v_deleted
   FROM leadflow.execute_dsr_request_legacy(p_request_id,p_action,p_lead_identifier,p_subject_token,p_operator_id,p_approver_id,p_annotation_code) legacy;
  IF v_local='not_found' AND NOT EXISTS(SELECT 1 FROM leadflow.dsr_provider_actions a WHERE a.request_id=p_request_id AND a.provider='hubspot' AND a.action=p_action) THEN
   INSERT INTO leadflow.dsr_provider_actions(request_id,provider,action,status,technical_reference,result_code) VALUES
    (p_request_id,'hubspot',p_action,'pending',p_request_id||':hubspot','provider_action_pending'),
    (p_request_id,'hunter',p_action,'pending',p_request_id||':hunter','capability_not_verified'),
    (p_request_id,'slack','no_action','not_applicable',p_request_id||':slack','no_subject_data');
   v_status:='partial';
   UPDATE leadflow.dsr_requests r SET status=v_status,updated_at=clock_timestamp() WHERE r.request_id=p_request_id;
  END IF;
  IF p_action='restrict' AND v_local IN ('completed','not_found') THEN
   UPDATE leadflow.dsr_provider_actions a SET status='failed',result_code='capability_not_available',updated_at=clock_timestamp()
    WHERE a.request_id=p_request_id AND a.provider='hubspot' AND a.action='restrict';
   v_status:='partial';
   UPDATE leadflow.dsr_requests r SET status=v_status,updated_at=clock_timestamp() WHERE r.request_id=p_request_id;
  END IF;
  RETURN QUERY SELECT p_request_id,v_status,v_local,v_code,v_count,v_deleted; RETURN;
 END IF;
 IF p_request_id!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'
  OR p_lead_identifier!~'^[0-9a-f]{64}$' OR p_subject_token!~'^[0-9a-f]{64}$'
  OR p_operator_id!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$' THEN RAISE EXCEPTION 'invalid DSR request' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id) THEN
  RETURN QUERY SELECT r.request_id,r.status,r.local_status,r.result_code,0,0 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id; RETURN;
 END IF;
 SELECT count(*) INTO v_count FROM leadflow.executions WHERE lead_identifier=p_lead_identifier;
 IF EXISTS(SELECT 1 FROM leadflow.executions e JOIN leadflow.retention_holds h ON h.execution_id=e.execution_id WHERE e.lead_identifier=p_lead_identifier AND h.released_at IS NULL AND h.starts_at<=clock_timestamp() AND h.review_at>clock_timestamp()) THEN
  v_local:='held';v_status:='held';v_code:='retention_hold';
 ELSIF v_count=0 THEN v_local:='not_found';v_status:='partial';v_code:='subject_not_found';
 ELSE v_local:='completed';v_status:='partial';v_code:='local_completed';
 END IF;
 INSERT INTO leadflow.dsr_requests(request_id,action,subject_token,status,local_status,operator_id,approver_id,result_code)
 VALUES(p_request_id,p_action,p_subject_token,v_status,v_local,p_operator_id,p_approver_id,v_code);
 IF v_local IN ('completed','not_found') THEN
  INSERT INTO leadflow.dsr_provider_actions(request_id,provider,action,status,technical_reference,result_code) VALUES
   (p_request_id,'hubspot','correct','pending',p_request_id||':hubspot','provider_action_pending'),
   (p_request_id,'hunter','correct','not_applicable',p_request_id||':hunter','no_correction_contract'),
   (p_request_id,'slack','no_action','not_applicable',p_request_id||':slack','no_subject_data');
 END IF;
 RETURN QUERY SELECT p_request_id,v_status,v_local,v_code,v_count,0;
END; $$;

REVOKE ALL ON FUNCTION leadflow.execute_dsr_request_legacy(text,text,text,text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION leadflow.execute_dsr_request(text,text,text,text,text,text,text) FROM PUBLIC;

COMMIT;
