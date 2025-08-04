#!/bin/bash

# Comprehensive Authentication Test Suite Runner
# This script runs all authentication-related tests to ensure nothing is broken

set -e  # Exit on any error

echo "🔐 Running Comprehensive Authentication Test Suite"
echo "================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to run tests and capture results
run_test_suite() {
    local test_file=$1
    local description=$2
    
    echo -e "${BLUE}📋 Running: $description${NC}"
    echo "   File: $test_file"
    echo ""
    
    if django-admin test $test_file --settings=config.dev.settings --verbosity=2; then
        echo -e "${GREEN}✅ PASSED: $description${NC}"
        return 0
    else
        echo -e "${RED}❌ FAILED: $description${NC}"
        return 1
    fi
}

# Initialize test results
total_suites=0
passed_suites=0
failed_suites=0

echo -e "${YELLOW}🧪 Test Suite Overview:${NC}"
echo "1. Existing Authentication Tests (backwards compatibility)"
echo "2. Secondary Email Model Tests" 
echo "3. Secondary Email Integration Tests"
echo "4. Original Integration Tests (to ensure no regression)"
echo "5. Authentication Security Tests"
echo "6. Email Template and Styling Tests"
echo ""

# Test 1: Original authentication tests (backwards compatibility)
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_original.AuthenticationTestCase" "Original Authentication Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Test 2: Secondary email model and unit tests
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_secondary_email" "Secondary Email Functionality Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Test 3: Secondary email integration tests
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_secondary_email_integration" "Secondary Email Integration Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Test 4: Original integration tests (regression check)
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_integration.AuthenticationIntegrationTestCase" "Original Authentication Integration Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Test 5: Security tests
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_original.SecurityTestCase" "Authentication Security Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Test 6: Email styling tests
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
total_suites=$((total_suites + 1))
if run_test_suite "tests.test_email_styles" "Email Template and Styling Tests"; then
    passed_suites=$((passed_suites + 1))
else
    failed_suites=$((failed_suites + 1))
fi
echo ""

# Final results
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}📊 TEST RESULTS SUMMARY${NC}"
echo "========================"
echo "Total Test Suites: $total_suites"
echo -e "Passed: ${GREEN}$passed_suites${NC}"
echo -e "Failed: ${RED}$failed_suites${NC}"
echo ""

if [ $failed_suites -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED! Your authentication system is working correctly.${NC}"
    echo ""
    echo -e "${GREEN}✅ Primary email authentication: WORKING${NC}"
    echo -e "${GREEN}✅ Secondary email authentication: WORKING${NC}"
    echo -e "${GREEN}✅ Password login: WORKING${NC}"
    echo -e "${GREEN}✅ Magic link login: WORKING${NC}"
    echo -e "${GREEN}✅ Email verification: WORKING${NC}"
    echo -e "${GREEN}✅ Account management: WORKING${NC}"
    echo -e "${GREEN}✅ Security measures: WORKING${NC}"
    echo -e "${GREEN}✅ Email styling consistency: WORKING${NC}"
    echo ""
    echo -e "${BLUE}🚀 Ready for production!${NC}"
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED! Please review the output above.${NC}"
    echo ""
    echo -e "${YELLOW}🔧 Troubleshooting tips:${NC}"
    echo "1. Make sure you've run the migration: python manage.py migrate"
    echo "2. Check that your test database is properly configured"
    echo "3. Verify all new models are properly imported"
    echo "4. Review any error messages in the test output above"
    echo ""
    exit 1
fi