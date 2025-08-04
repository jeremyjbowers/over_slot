"""
Quick syntax validation for the new test files.
This ensures all test classes are properly importable.
"""

from django.test import TestCase

# Import all test classes to verify syntax
try:
    from tests.test_secondary_email import (
        UserEmailModelTestCase,
        AuthenticationWithSecondaryEmailTestCase, 
        AccountManagementViewsTestCase,
        EmailVerificationTestCase,
        BackwardsCompatibilityTestCase,
        SecurityTestCase,
        NavigationTestCase,
        AdminIntegrationTestCase
    )
    
    from tests.test_secondary_email_integration import (
        SecondaryEmailWorkflowIntegrationTestCase,
        MultipleSecondaryEmailsIntegrationTestCase,
        CrossAuthenticationMethodTestCase,
        ErrorHandlingIntegrationTestCase,
        PerformanceIntegrationTestCase
    )
    
    IMPORT_SUCCESS = True
except ImportError as e:
    IMPORT_SUCCESS = False
    IMPORT_ERROR = str(e)


class SyntaxValidationTestCase(TestCase):
    """Test that all new test modules can be imported successfully"""
    
    def test_imports_successful(self):
        """Test that all test classes import without syntax errors"""
        self.assertTrue(IMPORT_SUCCESS, f"Import failed: {IMPORT_ERROR if not IMPORT_SUCCESS else ''}")
    
    def test_test_classes_defined(self):
        """Test that all expected test classes are defined"""
        expected_classes = [
            'UserEmailModelTestCase',
            'AuthenticationWithSecondaryEmailTestCase', 
            'AccountManagementViewsTestCase',
            'EmailVerificationTestCase',
            'BackwardsCompatibilityTestCase',
            'SecondaryEmailWorkflowIntegrationTestCase',
            'MultipleSecondaryEmailsIntegrationTestCase',
            'CrossAuthenticationMethodTestCase'
        ]
        
        for class_name in expected_classes:
            # Check if class exists in local scope (imported successfully)
            self.assertTrue(
                class_name in locals() or class_name in globals(),
                f"Test class {class_name} not found"
            )