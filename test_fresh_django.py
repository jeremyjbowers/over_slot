#!/usr/bin/env python3
"""
Test storage with a completely fresh Django setup
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Clear any existing Django setup
if 'django' in sys.modules:
    del sys.modules['django']
    
# Fresh Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.do_app_platform.settings')

import django
django.setup()

from django.conf import settings
from django.core.files.storage import default_storage

print("=== FRESH DJANGO TEST ===")
print(f"DEFAULT_FILE_STORAGE setting: {settings.DEFAULT_FILE_STORAGE}")
print(f"AWS_LOCATION setting: {getattr(settings, 'AWS_LOCATION', 'Not set')}")
print(f"Actual storage class: {type(default_storage).__name__}")
print(f"Actual storage module: {type(default_storage).__module__}")

if hasattr(default_storage, 'location'):
    print(f"Storage location: {default_storage.location}")
if hasattr(default_storage, 'bucket_name'):
    print(f"Storage bucket: {default_storage.bucket_name}")

# Quick upload test
try:
    from django.core.files.base import ContentFile
    test_file = ContentFile(b"Fresh Django test", name='fresh_test.txt')
    saved_path = default_storage.save('test/fresh_django_test.txt', test_file)
    print(f"\n✓ Upload test successful: {saved_path}")
    
    url = default_storage.url(saved_path)
    print(f"✓ File URL: {url}")
    
except Exception as e:
    print(f"\n✗ Upload test failed: {e}")
    import traceback
    traceback.print_exc() 