\getenv migrator_user POSTGRES_USER
\getenv migrator_password POSTGRES_PASSWORD
\getenv app_user POSTGRES_APP_USER
\getenv app_password POSTGRES_APP_PASSWORD

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'migrator_user', :'migrator_password') \gexec
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
    THEN format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
    ELSE format('ALTER ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
END \gexec
