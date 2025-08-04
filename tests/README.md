# Tests Directory

This directory contains all test files for the Over Slot project, organized for better structure and maintainability.

## Test Files

### Core Tests
- **`test_original.py`** - Original test suite (formerly `overslot/tests.py`)
  - Authentication tests
  - Views tests  
  - Search tests
  - Template rendering tests
  - Model tests
  - URL pattern tests
  - Security tests

### Integration Tests
- **`test_integration.py`** - Integration test suite
  - Authentication integration tests
  - Content discovery tests
  - Data integrity tests
  - Performance tests

### Secondary Email Feature Tests
- **`test_secondary_email.py`** - Unit tests for secondary email functionality
  - UserEmail model tests
  - Authentication with secondary emails
  - Account management views
  - Email verification
  - Security tests

- **`test_secondary_email_integration.py`** - Integration tests for secondary emails
  - Complete workflow tests
  - Multiple email scenarios
  - Cross-authentication method tests
  - Error handling

### Email System Tests
- **`test_email_styles.py`** - Email template and styling tests
  - Template rendering consistency
  - Style consistency across emails
  - Accessibility features
  - Mobile responsiveness

### Utility Tests
- **`test_syntax_check.py`** - Quick syntax validation for test imports

## Running Tests

### From Project Root:

**All tests:**
```bash
django-admin test tests
```

**Specific test file:**
```bash
django-admin test tests.test_secondary_email
```

**Specific test class:**
```bash
django-admin test tests.test_original.AuthenticationTestCase
```

**Using test runners:**
```bash
./bin/quick_test.sh              # Quick run
./bin/run_all_tests.sh all       # All tests with reports  
./bin/run_auth_tests.sh          # Authentication-focused
```

## Organization Benefits

✅ **Clean separation** - Tests separated from application code  
✅ **Easy discovery** - All tests in one location  
✅ **Better imports** - Clear module structure  
✅ **Maintainable** - Logical grouping by functionality  
✅ **Scalable** - Easy to add new test files  

## Test Coverage

This test suite covers:
- 🔐 **Authentication** (login, magic links, secondary emails)
- 📧 **Email system** (templates, styling, verification)
- 🔍 **Search functionality** 
- 📱 **Template rendering**
- 🗂️ **Model operations**
- 🔗 **URL routing**
- 🛡️ **Security measures**
- 🔄 **Integration workflows**