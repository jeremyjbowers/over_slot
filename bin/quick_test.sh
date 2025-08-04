#!/bin/bash

# Quick Test Runner - Just runs all tests without detailed reporting
# Use this for fast feedback during development

set -e

echo "🚀 Quick Test Run"
echo "=================="
echo ""

# Run all tests
echo "Running all tests..."
django-admin test --settings=config.dev.settings --verbosity=2

echo ""
echo "✅ Quick test run complete!"