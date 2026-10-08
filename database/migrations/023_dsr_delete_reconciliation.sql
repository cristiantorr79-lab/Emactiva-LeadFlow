BEGIN;
INSERT INTO leadflow.schema_migrations(version) VALUES ('023_dsr_delete_reconciliation');

CREATE FUNCTION leadflow.reconcile_dsr_delete_absent(p_request_id text,p_technical_reference text)
RETURNS TABLE(request_id text,status text,result_code text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
DECLARE v_overall text;
BEGIN
 IF p_technical_reference!~'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$' THEN RAISE EXCEPTION 'invalid provider result' USING ERRCODE='22023'; END IF;
 UPDATE leadflow.dsr_provider_actions a SET status='completed',technical_reference=p_technical_reference,result_code='reconciled_absent',updated_at=clock_timestamp()
 WHERE a.request_id=p_request_id AND a.provider='hubspot' AND a.action='delete' AND a.status='failed' AND a.result_code='contact_deletion_ambiguous'
  AND EXISTS(SELECT 1 FROM leadflow.dsr_requests r WHERE r.request_id=p_request_id AND r.action='delete' AND r.approver_id IS NOT NULL AND r.approver_id<>r.operator_id);
 IF NOT FOUND THEN RAISE EXCEPTION 'provider action is not safely reconcilable' USING ERRCODE='22023'; END IF;
 SELECT CASE WHEN bool_and(a.status IN ('completed','not_applicable')) THEN 'completed' ELSE 'partial' END INTO v_overall FROM leadflow.dsr_provider_actions a WHERE a.request_id=p_request_id;
 UPDATE leadflow.dsr_requests r SET status=v_overall,updated_at=clock_timestamp() WHERE r.request_id=p_request_id;
 RETURN QUERY SELECT p_request_id,v_overall,'reconciled_absent'::text;
END; $$;

REVOKE ALL ON FUNCTION leadflow.reconcile_dsr_delete_absent(text,text) FROM PUBLIC;
COMMIT;
