#!/bin/bash

set -euo pipefail

# Stream test output to console and save to logs
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORTS_DIR="test_reports"
LATEST_LOG="${REPORTS_DIR}/latest.log"
STAMPED_LOG="${REPORTS_DIR}/test_${TIMESTAMP}.log"

mkdir -p "$REPORTS_DIR"

echo "🧪 Running Django test suite (logging to $LATEST_LOG and $STAMPED_LOG)"

# Ensure dev settings and capture both stdout and stderr
if django-admin test --settings=config.dev.settings 2>&1 | tee "$LATEST_LOG" | tee "$STAMPED_LOG" >/dev/null; then
    echo "✅ Tests passed"
else
    echo "❌ Tests failed (see $LATEST_LOG)"
        exit 1
    fi