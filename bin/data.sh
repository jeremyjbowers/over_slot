#!/bin/bash

# Dump production database to dump.sql
# Uses production environment variables: PROD_PGPASS, PROD_PGUSER, PROD_PGHOST, PROD_PGPORT, PROD_PGDB

set -e

echo "Dumping production database..."

if [ -z "$PROD_PGUSER" ] || [ -z "$PROD_PGHOST" ] || [ -z "$PROD_PGDB" ]; then
    echo "Error: Required environment variables not set"
    echo "Please set: PROD_PGUSER, PROD_PGHOST, PROD_PGDB"
    echo "Optional: PROD_PGPORT (defaults to 5432), PROD_PGPASS"
    exit 1
fi

# Set defaults
PROD_PGPORT=${PROD_PGPORT:-5432}

# Set password if provided
if [ -n "$PROD_PGPASS" ]; then
    export PGPASSWORD="$PROD_PGPASS"
fi

# Dump the database
pg_dump \
    --host="$PROD_PGHOST" \
    --port="$PROD_PGPORT" \
    --username="$PROD_PGUSER" \
    --dbname="$PROD_PGDB" \
    --no-password \
    --verbose \
    --clean \
    --if-exists \
    --create \
    --format=plain \
    --file=dump.sql

echo "Database dump completed: dump.sql" 