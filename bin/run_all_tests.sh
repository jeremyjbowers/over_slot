#!/bin/bash

# Comprehensive Test Runner with Detailed Reporting
# Runs all tests and generates reports in multiple formats

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORTS_DIR="test_reports"
JSON_REPORT="${REPORTS_DIR}/test_results_${TIMESTAMP}.json"
CSV_REPORT="${REPORTS_DIR}/test_results_${TIMESTAMP}.csv"
TEXT_REPORT="${REPORTS_DIR}/test_results_${TIMESTAMP}.txt"
DETAILED_LOG="${REPORTS_DIR}/test_detailed_${TIMESTAMP}.log"

echo -e "${BLUE}🧪 Comprehensive Test Runner for Over Slot${NC}"
echo "=============================================="
echo "Timestamp: $(date)"
echo "Reports will be saved to: $REPORTS_DIR/"
echo ""

# Create reports directory
mkdir -p "$REPORTS_DIR"

# Function to run specific test suite and capture results
run_test_suite() {
    local test_path=$1
    local description=$2
    local start_time=$(date +%s)
    
    echo -e "${BLUE}📋 Running: $description${NC}"
    echo "   Test Path: $test_path"
    echo ""
    
    # Run the test and capture both stdout and stderr
         if django-admin test "$test_path" --settings=config.dev.settings --verbosity=2 > "temp_output_${test_path//\./_}.log" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${GREEN}✅ PASSED: $description (${duration}s)${NC}"
        
        # Extract test count from output
        local test_count=$(grep -o "Ran [0-9]* test" "temp_output_${test_path//\./_}.log" | grep -o "[0-9]*" || echo "0")
        
        echo "$test_path,PASSED,$test_count,$duration,$description" >> "$CSV_REPORT.tmp"
        echo "✅ PASSED: $description" >> "$TEXT_REPORT.tmp"
        echo "   Tests run: $test_count, Duration: ${duration}s" >> "$TEXT_REPORT.tmp"
        echo "" >> "$TEXT_REPORT.tmp"
        
        # Append to detailed log
        echo "=== $description ===" >> "$DETAILED_LOG"
        cat "temp_output_${test_path//\./_}.log" >> "$DETAILED_LOG"
        echo "" >> "$DETAILED_LOG"
        
        rm -f "temp_output_${test_path//\./_}.log"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${RED}❌ FAILED: $description (${duration}s)${NC}"
        
        # Extract error information
        local error_info=$(tail -10 "temp_output_${test_path//\./_}.log" | tr '\n' ' ')
        local test_count=$(grep -o "Ran [0-9]* test" "temp_output_${test_path//\./_}.log" | grep -o "[0-9]*" || echo "0")
        
        echo "$test_path,FAILED,$test_count,$duration,$description,\"$error_info\"" >> "$CSV_REPORT.tmp"
        echo "❌ FAILED: $description" >> "$TEXT_REPORT.tmp"
        echo "   Tests run: $test_count, Duration: ${duration}s" >> "$TEXT_REPORT.tmp"
        echo "   Error: $error_info" >> "$TEXT_REPORT.tmp"
        echo "" >> "$TEXT_REPORT.tmp"
        
        # Append to detailed log
        echo "=== $description (FAILED) ===" >> "$DETAILED_LOG"
        cat "temp_output_${test_path//\./_}.log" >> "$DETAILED_LOG"
        echo "" >> "$DETAILED_LOG"
        
        rm -f "temp_output_${test_path//\./_}.log"
        return 1
    fi
}

# Function to run all tests at once
run_all_tests_combined() {
    echo -e "${YELLOW}🚀 Running ALL tests in one go...${NC}"
    local start_time=$(date +%s)
    
         if django-admin test --settings=config.dev.settings --verbosity=2 > "all_tests_output.log" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local test_count=$(grep -o "Ran [0-9]* test" "all_tests_output.log" | grep -o "[0-9]*")
        
        echo -e "${GREEN}✅ ALL TESTS PASSED (${test_count} tests, ${duration}s)${NC}"
        
        # Add to reports
        echo "ALL_TESTS,PASSED,$test_count,$duration,Complete Test Suite" >> "$CSV_REPORT.tmp"
        echo "🎉 ALL TESTS PASSED!" >> "$TEXT_REPORT.tmp"
        echo "   Total tests: $test_count, Duration: ${duration}s" >> "$TEXT_REPORT.tmp"
        echo "" >> "$TEXT_REPORT.tmp"
        
        # Detailed log
        echo "=== COMPLETE TEST SUITE ===" >> "$DETAILED_LOG"
        cat "all_tests_output.log" >> "$DETAILED_LOG"
        
        rm -f "all_tests_output.log"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local test_count=$(grep -o "Ran [0-9]* test" "all_tests_output.log" | grep -o "[0-9]*" || echo "0")
        local failures=$(grep -o "[0-9]* failure" "all_tests_output.log" | grep -o "[0-9]*" || echo "0")
        local errors=$(grep -o "[0-9]* error" "all_tests_output.log" | grep -o "[0-9]*" || echo "0")
        
        echo -e "${RED}❌ SOME TESTS FAILED (${test_count} tests, ${failures} failures, ${errors} errors, ${duration}s)${NC}"
        
        # Add to reports
        echo "ALL_TESTS,FAILED,$test_count,$duration,Complete Test Suite,\"$failures failures $errors errors\"" >> "$CSV_REPORT.tmp"
        echo "❌ SOME TESTS FAILED" >> "$TEXT_REPORT.tmp"
        echo "   Total tests: $test_count, Failures: $failures, Errors: $errors, Duration: ${duration}s" >> "$TEXT_REPORT.tmp"
        echo "" >> "$TEXT_REPORT.tmp"
        
        # Detailed log
        echo "=== COMPLETE TEST SUITE (WITH FAILURES) ===" >> "$DETAILED_LOG"
        cat "all_tests_output.log" >> "$DETAILED_LOG"
        
        rm -f "all_tests_output.log"
        return 1
    fi
}

# Function to generate JSON report
generate_json_report() {
    echo -e "${BLUE}📄 Generating JSON report...${NC}"
    
    # Start JSON structure
    cat > "$JSON_REPORT" << EOF
{
  "test_run": {
    "timestamp": "$(date -Iseconds)",
    "project": "Over Slot",
    "environment": "development",
    "total_suites": $total_suites,
    "passed_suites": $passed_suites,
    "failed_suites": $failed_suites
  },
  "results": [
EOF

    # Process CSV data to JSON
    local first_entry=true
    while IFS=',' read -r test_path status test_count duration description error_info; do
        if [ "$first_entry" = true ]; then
            first_entry=false
        else
            echo "," >> "$JSON_REPORT"
        fi
        
        # Clean up the error_info field if it exists
        if [ -n "$error_info" ]; then
            error_info=$(echo "$error_info" | sed 's/"/\\"/g')
            cat >> "$JSON_REPORT" << EOF
    {
      "test_path": "$test_path",
      "status": "$status",
      "test_count": $test_count,
      "duration_seconds": $duration,
      "description": "$description",
      "error_info": "$error_info"
    }EOF
        else
            cat >> "$JSON_REPORT" << EOF
    {
      "test_path": "$test_path",
      "status": "$status", 
      "test_count": $test_count,
      "duration_seconds": $duration,
      "description": "$description"
    }EOF
        fi
    done < "$CSV_REPORT.tmp"
    
    # Close JSON structure
    cat >> "$JSON_REPORT" << EOF

  ]
}
EOF

    echo -e "${GREEN}✅ JSON report saved: $JSON_REPORT${NC}"
}

# Function to finalize CSV report
finalize_csv_report() {
    echo -e "${BLUE}📊 Generating CSV report...${NC}"
    
    # Add header
    echo "test_path,status,test_count,duration_seconds,description,error_info" > "$CSV_REPORT"
    
    # Add data
    cat "$CSV_REPORT.tmp" >> "$CSV_REPORT"
    rm -f "$CSV_REPORT.tmp"
    
    echo -e "${GREEN}✅ CSV report saved: $CSV_REPORT${NC}"
}

# Function to finalize text report
finalize_text_report() {
    echo -e "${BLUE}📝 Generating text report...${NC}"
    
    # Add header to final report
    cat > "$TEXT_REPORT" << EOF
Over Slot Test Results
======================
Timestamp: $(date)
Total Suites: $total_suites
Passed: $passed_suites
Failed: $failed_suites

DETAILED RESULTS:
$(cat "$TEXT_REPORT.tmp")

SUMMARY:
EOF

    if [ $failed_suites -eq 0 ]; then
        echo "🎉 ALL TESTS PASSED! Your system is working correctly." >> "$TEXT_REPORT"
    else
        echo "⚠️  $failed_suites test suite(s) failed. See details above." >> "$TEXT_REPORT"
        echo "" >> "$TEXT_REPORT"
        echo "FAILED TESTS TO CREATE TICKETS FOR:" >> "$TEXT_REPORT"
        grep "❌ FAILED:" "$TEXT_REPORT.tmp" >> "$TEXT_REPORT"
    fi
    
    rm -f "$TEXT_REPORT.tmp"
    
    echo -e "${GREEN}✅ Text report saved: $TEXT_REPORT${NC}"
}

# Main execution
main() {
    local run_mode="${1:-individual}"  # Default to individual, can be "all" or "individual"
    
    check_environment
    
    # Initialize temporary CSV file
    touch "$CSV_REPORT.tmp"
    touch "$TEXT_REPORT.tmp"
    
    total_suites=0
    passed_suites=0
    failed_suites=0
    
    if [ "$run_mode" = "all" ]; then
        echo -e "${YELLOW}🧪 Running all tests in one command...${NC}"
        echo ""
        
        total_suites=1
        if run_all_tests_combined; then
            passed_suites=1
        else
            failed_suites=1
        fi
    else
        echo -e "${YELLOW}🧪 Running individual test suites...${NC}"
        echo ""
        
        # Define test suites
        test_suites=(
            "tests.test_original.AuthenticationTestCase:Original Authentication Tests (backwards compatibility)"
            "tests.test_secondary_email:Secondary Email Functionality Tests"
            "tests.test_secondary_email_integration:Secondary Email Integration Tests"
            "tests.test_integration.AuthenticationIntegrationTestCase:Original Authentication Integration Tests"
            "tests.test_original.SecurityTestCase:Authentication Security Tests"
            "tests.test_email_styles:Email Template and Styling Tests"
            "tests.test_original.ViewsTestCase:Views and URL Pattern Tests"
            "tests.test_original.SearchTestCase:Search Functionality Tests"
            "tests.test_original.TemplateRenderingTestCase:Template Rendering Tests"
            "tests.test_original.ModelTestCase:Model Functionality Tests"
            "tests.test_original.URLPatternTestCase:URL Pattern Resolution Tests"
        )
        
        # Run each test suite
        for suite in "${test_suites[@]}"; do
            IFS=':' read -r test_path description <<< "$suite"
            total_suites=$((total_suites + 1))
            
            if run_test_suite "$test_path" "$description"; then
                passed_suites=$((passed_suites + 1))
            else
                failed_suites=$((failed_suites + 1))
            fi
            echo ""
        done
    fi
    
    # Generate reports
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}📊 GENERATING REPORTS${NC}"
    echo "========================="
    
    finalize_csv_report
    generate_json_report
    finalize_text_report
    
    echo ""
    echo -e "${BLUE}📁 REPORT FILES GENERATED:${NC}"
    echo "   📊 CSV:     $CSV_REPORT"
    echo "   📄 JSON:    $JSON_REPORT"
    echo "   📝 Text:    $TEXT_REPORT"
    echo "   📋 Detailed: $DETAILED_LOG"
    echo ""
    
    # Final summary
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}📊 FINAL SUMMARY${NC}"
    echo "================"
    echo "Total Test Suites: $total_suites"
    echo -e "Passed: ${GREEN}$passed_suites${NC}"
    echo -e "Failed: ${RED}$failed_suites${NC}"
    echo ""
    
    if [ $failed_suites -eq 0 ]; then
        echo -e "${GREEN}🎉 ALL TESTS PASSED! Your authentication system is working correctly.${NC}"
        echo ""
        echo -e "${GREEN}✅ Ready for production!${NC}"
        exit 0
    else
        echo -e "${RED}⚠️  $failed_suites test suite(s) failed.${NC}"
        echo ""
        echo -e "${YELLOW}📋 TO CREATE TICKETS:${NC}"
        echo "1. Check the detailed reports in: $REPORTS_DIR/"
        echo "2. CSV report has structured data for importing to issue trackers"
        echo "3. JSON report can be processed programmatically"
        echo "4. Text report has human-readable summaries"
        echo ""
        echo -e "${YELLOW}🔧 Next steps:${NC}"
        echo "1. Review failed tests in the detailed log: $DETAILED_LOG"
        echo "2. Check individual error messages in the reports"
        echo "3. Fix issues and re-run tests"
        echo ""
        exit 1
    fi
}

# Parse command line arguments
case "${1:-}" in
    "all")
        main "all"
        ;;
    "individual"|"")
        main "individual"
        ;;
    "--help"|"-h")
        echo "Usage: $0 [all|individual]"
        echo ""
        echo "Options:"
        echo "  all         Run all tests in one command (faster)"
        echo "  individual  Run test suites individually (more detailed)"
        echo "  --help      Show this help message"
        echo ""
        echo "Reports are generated in: test_reports/"
        exit 0
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac