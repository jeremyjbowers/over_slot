# Test Runner Guide

## Overview
We have multiple test runners available depending on your needs:

## 🚀 Quick Test Runner (`bin/quick_test.sh`)
**Use for**: Fast feedback during development

```bash
./bin/quick_test.sh
```

- Runs all tests in one command
- No detailed reporting
- Fast and simple
- Good for quick checks

## 🧪 Comprehensive Test Runner (`bin/run_all_tests.sh`)
**Use for**: Detailed analysis and creating tickets for failures

### Run All Tests at Once (Faster)
```bash
./bin/run_all_tests.sh all
```

### Run Individual Test Suites (More Detailed)
```bash
./bin/run_all_tests.sh individual
# or just:
./bin/run_all_tests.sh
```

## 📊 Generated Reports

When you run the comprehensive test runner, it creates a `test_reports/` directory with:

### 1. CSV Report (`test_results_TIMESTAMP.csv`)
**Perfect for**: Importing into issue trackers (Jira, GitHub Issues, etc.)

Format:
```csv
test_path,status,test_count,duration_seconds,description,error_info
overslot.tests.AuthenticationTestCase,PASSED,8,2,Original Authentication Tests,
overslot.test_secondary_email,FAILED,15,5,Secondary Email Tests,"AssertionError: False is not true"
```

### 2. JSON Report (`test_results_TIMESTAMP.json`)
**Perfect for**: Programmatic processing, CI/CD integration

```json
{
  "test_run": {
    "timestamp": "2024-01-15T10:30:00-08:00",
    "project": "Over Slot",
    "total_suites": 6,
    "passed_suites": 5,
    "failed_suites": 1
  },
  "results": [
    {
      "test_path": "overslot.tests.AuthenticationTestCase",
      "status": "PASSED",
      "test_count": 8,
      "duration_seconds": 2,
      "description": "Original Authentication Tests"
    }
  ]
}
```

### 3. Text Report (`test_results_TIMESTAMP.txt`)
**Perfect for**: Human-readable summaries, email reports

```
Over Slot Test Results
======================
Timestamp: Mon Jan 15 10:30:00 PST 2024
Total Suites: 6
Passed: 5
Failed: 1

DETAILED RESULTS:
✅ PASSED: Original Authentication Tests
   Tests run: 8, Duration: 2s

❌ FAILED: Secondary Email Tests
   Tests run: 15, Duration: 5s
   Error: AssertionError: False is not true

FAILED TESTS TO CREATE TICKETS FOR:
❌ FAILED: Secondary Email Tests
```

### 4. Detailed Log (`test_detailed_TIMESTAMP.log`)
**Perfect for**: Full debugging information

Contains complete test output for each suite, including:
- Full stack traces
- Detailed error messages
- All test output
- Django system checks

## 🎯 Creating Tickets from Failed Tests

### From CSV Report:
1. Open the CSV in Excel/Google Sheets
2. Filter by `status = FAILED`
3. Each row becomes a ticket:
   - **Title**: `description` field
   - **Description**: `error_info` field + link to detailed log
   - **Labels**: `test_path` for categorization

### From JSON Report:
Perfect for automation:
```python
import json

with open('test_results_TIMESTAMP.json') as f:
    data = json.load(f)

failed_tests = [r for r in data['results'] if r['status'] == 'FAILED']
for test in failed_tests:
    create_ticket(
        title=f"Test Failure: {test['description']}",
        description=f"Test: {test['test_path']}\nError: {test.get('error_info', 'See logs')}",
        labels=['testing', 'bug']
    )
```

### From Text Report:
1. Copy the "FAILED TESTS TO CREATE TICKETS FOR:" section
2. Each line becomes a ticket title
3. Reference the detailed log for full error info

## 🔄 Authentication-Specific Runner (`bin/run_auth_tests.sh`)
**Use for**: Focused authentication testing (existing script)

```bash
./bin/run_auth_tests.sh
```

- Runs only authentication-related tests
- Colored output
- Authentication-specific summary

## 💡 Usage Recommendations

### During Development:
```bash
./bin/quick_test.sh  # Fast feedback
```

### Before Commits:
```bash
./bin/run_all_tests.sh all  # Full validation with reports
```

### CI/CD Pipeline:
```bash
./bin/run_all_tests.sh all
# Upload reports as artifacts
# Parse JSON for build status
```

### Weekly Testing/QA:
```bash
./bin/run_all_tests.sh individual  # Detailed analysis
# Review reports
# Create tickets for any failures
```

## 📁 Report File Management

Reports are automatically timestamped and stored in `test_reports/`:
```
test_reports/
├── test_results_20240115_103000.csv
├── test_results_20240115_103000.json
├── test_results_20240115_103000.txt
└── test_detailed_20240115_103000.log
```

You can safely clean up old reports or archive them as needed.

## 🛠️ Integration Examples

### GitHub Actions:
```yaml
- name: Run Tests with Reports
  run: ./bin/run_all_tests.sh all
  
- name: Upload Test Reports
  uses: actions/upload-artifact@v3
  with:
    name: test-reports
    path: test_reports/
```

### Jira Integration:
Use the CSV report to bulk-create issues:
1. Export CSV
2. Use Jira's CSV import feature
3. Map columns appropriately

### Slack Notifications:
```bash
# Parse results and send to Slack
FAILED_COUNT=$(jq '.test_run.failed_suites' test_reports/test_results_*.json)
if [ "$FAILED_COUNT" -gt 0 ]; then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"🚨 '"$FAILED_COUNT"' test suites failed!"}' \
        $SLACK_WEBHOOK_URL
fi
```