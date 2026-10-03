\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv bootstrap_password POSTGRES_BOOTSTRAP_PASSWORD
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv migrator_password POSTGRES_MIGRATOR_PASSWORD
\getenv app_user POSTGRES_APP_USER
\getenv app_password POSTGRES_APP_PASSWORD

-- The PowerShell orchestrator routes immutable OID 10 volumes through the
-- guarded multi-session legacy repair before this normal path is considered.
SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = :'migrator_user' AND oid = 10) AS migrator_is_oid10 \gset
\if :migrator_is_oid10
\echo 'Refusing to demote PostgreSQL bootstrap OID 10; use the guarded legacy repair'
\quit 3
\endif
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'bootstrap_user')
    THEN format('CREATE ROLE %I LOGIN SUPERUSER CREATEDB CREATEROLE NOREPLICATION PASSWORD %L', :'bootstrap_user', :'bootstrap_password')
    ELSE format('ALTER ROLE %I LOGIN SUPERUSER CREATEDB CREATEROLE NOREPLICATION PASSWORD %L', :'bootstrap_user', :'bootstrap_password')
END \gexec

-- Migration 001 uses CREATE EXTENSION IF NOT EXISTS. Install it as bootstrap
-- so the restricted migrator never needs database-wide CREATE or superuser.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_user')
    THEN format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migrator_user', :'migrator_password')
    ELSE format('ALTER ROLE %I LOGIN PASSWORD %L', :'migrator_user', :'migrator_password')
END \gexec
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
    THEN format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_user', :'app_password')
    ELSE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_user', :'app_password')
END \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'migrator_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS leadflow AUTHORIZATION %I', :'migrator_user') \gexec
SELECT format('ALTER SCHEMA leadflow OWNER TO %I', :'migrator_user') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA leadflow TO %I', :'migrator_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA leadflow TO %I', :'app_user') \gexec
SELECT format('REVOKE CREATE ON SCHEMA leadflow FROM %I', :'app_user') \gexec

SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migrator_user', :'migrator_password') \gexec
