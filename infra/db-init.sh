#!/bin/sh
set -eu
# psql reads passwords from files via \getenv; no passwords in process argv or logs.
GOLD_OWNER_PASSWORD="$(cat /run/secrets/db_owner_password)"
GOLD_READER_PASSWORD="$(cat /run/secrets/db_reader_password)"
GOLD_INGESTOR_PASSWORD="$(cat /run/secrets/db_ingestor_password)"
export GOLD_OWNER_PASSWORD GOLD_READER_PASSWORD GOLD_INGESTOR_PASSWORD
psql --username "$POSTGRES_USER" --dbname gold --set ON_ERROR_STOP=1 <<'SQL'
\getenv owner_password GOLD_OWNER_PASSWORD
\getenv reader_password GOLD_READER_PASSWORD
\getenv ingestor_password GOLD_INGESTOR_PASSWORD
CREATE ROLE gold_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
CREATE ROLE gold_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'reader_password';
CREATE ROLE gold_ingestor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'ingestor_password';
REVOKE ALL ON DATABASE gold FROM PUBLIC;
GRANT CONNECT ON DATABASE gold TO gold_owner, gold_reader, gold_ingestor;
ALTER SCHEMA public OWNER TO gold_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO gold_reader, gold_ingestor;
ALTER DEFAULT PRIVILEGES FOR ROLE gold_owner IN SCHEMA public GRANT SELECT ON TABLES TO gold_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE gold_owner IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO gold_ingestor;
ALTER DEFAULT PRIVILEGES FOR ROLE gold_owner IN SCHEMA public GRANT USAGE ON SEQUENCES TO gold_ingestor;
ALTER ROLE gold_reader SET statement_timeout = '5000ms';
ALTER ROLE gold_reader SET default_transaction_read_only = on;
ALTER ROLE gold_ingestor SET statement_timeout = '30000ms';
SQL
