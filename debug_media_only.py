#!/usr/bin/env python3
"""
Debug media file uploads specifically
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

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
import io

print("=== MEDIA FILES DEBUG ===")

# Check current storage configuration
print(f"DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}")
print(f"AWS_LOCATION: {getattr(settings, 'AWS_LOCATION', 'Not set')}")
print(f"MEDIA_URL: {settings.MEDIA_URL}")

# Check actual storage instance
storage = default_storage
print(f"\nActual storage class: {type(storage).__name__}")
print(f"Storage module: {type(storage).__module__}")

if hasattr(storage, 'location'):
    print(f"Storage location: {storage.location}")
if hasattr(storage, 'bucket_name'):
    print(f"Storage bucket: {storage.bucket_name}")

# Test 1: Simple text file upload
print("\n=== TEST 1: Simple text file ===")
try:
    test_content = ContentFile(b"Media test file", name='media_test.txt')
    saved_path = storage.save('test/media_test.txt', test_content)
    print(f"✓ Saved path: {saved_path}")
    
    exists = storage.exists(saved_path)
    print(f"✓ File exists: {exists}")
    
    url = storage.url(saved_path)
    print(f"✓ File URL: {url}")
    
except Exception as e:
    print(f"✗ Simple upload failed: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Image file upload (like featured_image)
print("\n=== TEST 2: Image file upload ===")
try:
    # Create test image
    img = Image.new('RGB', (100, 100), color='green')
    img_io = io.BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    
    image_file = ContentFile(img_io.getvalue(), name='test_image.jpg')
    
    # Test the actual upload path used by models
    saved_path = storage.save('articles/featured/test_upload.jpg', image_file)
    print(f"✓ Image saved path: {saved_path}")
    
    exists = storage.exists(saved_path)
    print(f"✓ Image exists: {exists}")
    
    url = storage.url(saved_path)
    print(f"✓ Image URL: {url}")
    
    # Test the URL by trying to get the file size
    try:
        size = storage.size(saved_path)
        print(f"✓ Image size: {size} bytes")
    except Exception as e:
        print(f"✗ Could not get size: {e}")
    
except Exception as e:
    print(f"✗ Image upload failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Check what happens with model upload paths
print("\n=== TEST 3: Model upload paths ===")
try:
    from overslot.models import Article
    article = Article()
    upload_to = article.featured_image.field.upload_to
    print(f"Article upload_to: {upload_to}")
    
    # Simulate what Django does when saving a model
    test_filename = f"{upload_to}/debug_model_test.jpg"
    print(f"Full path would be: {test_filename}")
    
except Exception as e:
    print(f"✗ Model path test failed: {e}")

print("\n=== STORAGE BACKEND ANALYSIS ===")
print("If files are saved but URLs don't work, possible issues:")
print("1. AWS_LOCATION setting conflict")
print("2. Different storage backend needed for media vs static")
print("3. Path structure issues")
print("4. CORS or permissions on specific paths") 