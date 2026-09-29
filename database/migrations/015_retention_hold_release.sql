-- Conserva la evidencia mínima de holds vencidos/liberados al eliminar su ejecución.
BEGIN;
INSERT INTO leadflow.schema_migrations(version) VALUES ('015_retention_hold_release');

CREATE FUNCTION leadflow.release_retention_holds_on_execution_delete()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,leadflow AS $$
BEGIN
 UPDATE leadflow.retention_holds h
 SET released_at=coalesce(h.released_at,clock_timestamp())
 WHERE h.execution_id=OLD.execution_id;
 RETURN OLD;
END; $$;

CREATE TRIGGER release_retention_holds_before_execution_delete
 BEFORE DELETE ON leadflow.executions FOR EACH ROW
 EXECUTE FUNCTION leadflow.release_retention_holds_on_execution_delete();

REVOKE ALL ON FUNCTION leadflow.release_retention_holds_on_execution_delete() FROM PUBLIC;
COMMIT;
