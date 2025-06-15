#!/bin/bash

# Test runner script for Over Slot

echo "🧪 Over Slot Test Suite"
echo "======================="

# Set Django settings
export DJANGO_SETTINGS_MODULE=config.dev.settings

# Function to run tests with proper formatting
run_test_suite() {
    local test_name="$1"
    local test_path="$2"
    
    echo ""
    echo "📋 Running $test_name..."
    echo "----------------------------------------"
    
    python manage.py test $test_path --verbosity=2
    
    if [ $? -eq 0 ]; then
        echo "✅ $test_name completed successfully"
    else
        echo "❌ $test_name failed"
        exit 1
    fi
}

# Parse command line arguments
case "$1" in
    "auth")
        echo "Running authentication tests only..."
        run_test_suite "Authentication Tests" "overslot.tests.AuthenticationTestCase"
        ;;
    "views")
        echo "Running view/UI tests only..."
        run_test_suite "Views Tests" "overslot.tests.ViewsTestCase"
        run_test_suite "Template Tests" "overslot.tests.TemplateRenderingTestCase"
        ;;
    "search")
        echo "Running search tests only..."
        run_test_suite "Search Tests" "overslot.tests.SearchTestCase"
        ;;
    "integration")
        echo "Running integration tests only..."
        run_test_suite "Integration Tests" "overslot.test_integration"
        ;;
    "models")
        echo "Running model tests only..."
        run_test_suite "Model Tests" "overslot.tests.ModelTestCase"
        ;;
    "security")
        echo "Running security tests only..."
        run_test_suite "Security Tests" "overslot.tests.SecurityTestCase"
        ;;
    "quick")
        echo "Running quick test suite (unit tests only)..."
        run_test_suite "Authentication Tests" "overslot.tests.AuthenticationTestCase"
        run_test_suite "Views Tests" "overslot.tests.ViewsTestCase"
        run_test_suite "Search Tests" "overslot.tests.SearchTestCase"
        ;;
    "full" | "")
        echo "Running full test suite..."
        run_test_suite "Unit Tests" "overslot.tests"
        run_test_suite "Integration Tests" "overslot.test_integration"
        ;;
    "help" | "-h" | "--help")
        echo "Usage: ./bin/run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  auth         - Run authentication tests only"
        echo "  views        - Run view/UI tests only"
        echo "  search       - Run search tests only"
        echo "  integration  - Run integration tests only"
        echo "  models       - Run model tests only"
        echo "  security     - Run security tests only"
        echo "  quick        - Run quick test suite (unit tests)"
        echo "  full         - Run full test suite (default)"
        echo "  help         - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./bin/run_tests.sh              # Run all tests"
        echo "  ./bin/run_tests.sh auth         # Run authentication tests"
        echo "  ./bin/run_tests.sh quick        # Run quick unit tests"
        echo "  ./bin/run_tests.sh integration  # Run integration tests"
        exit 0
        ;;
    *)
        echo "❌ Unknown option: $1"
        echo "Use './bin/run_tests.sh help' for usage information"
        exit 1
        ;;
esac

echo ""
echo "🎉 All selected tests completed successfully!"
echo ""
echo "Test Coverage Areas:"
echo "• Magic link authentication system"
echo "• View rendering and URL patterns"
echo "• Search functionality"
echo "• Content relationships and navigation"
echo "• Security and access control"
echo "• Template rendering"
echo "• Model functionality"
echo ""
echo "To run specific test categories, use:"
echo "  ./bin/run_tests.sh auth         # Authentication only"
echo "  ./bin/run_tests.sh views        # Views and templates"
echo "  ./bin/run_tests.sh integration  # Full workflows" 