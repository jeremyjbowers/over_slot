#!/usr/bin/env python3
"""
Test if custom storage class can be imported
"""

import os
import sys
import django
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.do_app_platform.settings')
django.setup()

print("Testing storage class import...")

try:
    from config.storage import MediaStorage
    print("✓ Successfully imported MediaStorage from config.storage")
    
    # Test instantiation
    storage = MediaStorage()
    print(f"✓ Successfully created MediaStorage instance")
    print(f"  Class: {type(storage).__name__}")
    print(f"  Module: {type(storage).__module__}")
    print(f"  Location: {getattr(storage, 'location', 'Not set')}")
    
    # Check if it has the right attributes
    attrs = ['bucket_name', 'access_key', 'secret_key', 'endpoint_url']
    for attr in attrs:
        if hasattr(storage, attr):
            value = getattr(storage, attr)
            if 'key' in attr:
                value = "***SET***" if value else "NOT SET"
            print(f"  {attr}: {value}")
        else:
            print(f"  {attr}: NOT FOUND")
            
except ImportError as e:
    print(f"✗ Failed to import MediaStorage: {e}")
except Exception as e:
    print(f"✗ Error creating MediaStorage: {e}")

# Test the setting value
print(f"\nDEFAULT_FILE_STORAGE setting: {django.conf.settings.DEFAULT_FILE_STORAGE}")

# Test what default_storage actually resolves to
from django.core.files.storage import default_storage
print(f"Actual default_storage class: {type(default_storage).__name__}")
print(f"Actual default_storage module: {type(default_storage).__module__}") 