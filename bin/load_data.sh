#!/bin/bash

# Load database dump into local overslot database
psql -h localhost -p 5432 -U overslot -d overslot < dump.sql
