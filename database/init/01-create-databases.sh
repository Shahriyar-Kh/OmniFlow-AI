#!/usr/bin/env sh
set -eu

required_vars="APP_DB_NAME APP_DB_USER APP_DB_PASSWORD N8N_DB_NAME N8N_DB_USER N8N_DB_PASSWORD"
for variable_name in $required_vars; do
  eval "variable_value=\${$variable_name:-}"
  if [ -z "$variable_value" ]; then
    echo "Required database initialization variable is missing: $variable_name" >&2
    exit 1
  fi
done

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_user="$APP_DB_USER" --set=app_password="$APP_DB_PASSWORD" \
  --set=n8n_user="$N8N_DB_USER" --set=n8n_password="$N8N_DB_PASSWORD" <<-'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'n8n_user', :'n8n_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'n8n_user') \gexec
SQL

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_db="$APP_DB_NAME" --set=app_user="$APP_DB_USER" \
  --set=n8n_db="$N8N_DB_NAME" --set=n8n_user="$N8N_DB_USER" <<-'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'n8n_db', :'n8n_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'n8n_db') \gexec
SQL

