-- Registro oficial de entrega de alertas sin alterar el fallo principal.
BEGIN;
\getenv app_user POSTGRES_APP_USER
INSERT INTO leadflow.schema_migrations(version) VALUES ('006_alert_events');

CREATE FUNCTION leadflow.record_alert_result(
 p_execution_id text, p_delivered boolean, p_error_code text
)
RETURNS TABLE(execution_id text, execution_status text, error_type text, alert_delivered boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM leadflow.executions e WHERE e.execution_id=p_execution_id AND e.status='failed') THEN
  RAISE EXCEPTION 'execution must already be failed' USING ERRCODE='22023';
 END IF;
 INSERT INTO leadflow.execution_events(execution_id,status,stage,attempt_number,error_type,error_code,error_message)
 VALUES(p_execution_id,'failed','alert',1,
  CASE WHEN p_delivered THEN NULL ELSE 'upstream_error' END,
  CASE WHEN p_delivered THEN NULL ELSE coalesce(p_error_code,'slack_delivery_failed') END,
  CASE WHEN p_delivered THEN 'Failure alert delivered' ELSE 'Failure alert delivery failed' END);
 RETURN QUERY SELECT p_execution_id,'failed'::text,e.error_type,p_delivered
 FROM leadflow.executions e WHERE e.execution_id=p_execution_id;
END; $$;
REVOKE ALL ON FUNCTION leadflow.record_alert_result(text,boolean,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION leadflow.record_alert_result(text,boolean,text) TO :"app_user";
COMMIT;
