#!/bin/bash

# Dump production database to project root
PGPASSWORD=$PROD_PGPASS pg_dump -h $PROD_PGHOST -p $PROD_PGPORT -U $PROD_PGUSER -d $PROD_PGDB > dump.sql
