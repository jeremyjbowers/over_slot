#!/usr/bin/env python3
"""
Debug script to test DigitalOcean Spaces storage configuration.
Run this in your production environment to check if uploads are working.
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
import tempfile
from PIL import Image
import io

def test_storage_configuration():
    """Test the storage configuration and AWS credentials."""
    print("=== TESTING STORAGE CONFIGURATION ===")
    
    # Check AWS settings
    print(f"AWS_ACCESS_KEY_ID: {'✓ Set' if settings.AWS_ACCESS_KEY_ID else '✗ Not Set'}")
    print(f"AWS_SECRET_ACCESS_KEY: {'✓ Set' if settings.AWS_SECRET_ACCESS_KEY else '✗ Not Set'}")
    print(f"AWS_STORAGE_BUCKET_NAME: {settings.AWS_STORAGE_BUCKET_NAME}")
    print(f"AWS_S3_ENDPOINT_URL: {settings.AWS_S3_ENDPOINT_URL}")
    print(f"AWS_S3_CUSTOM_DOMAIN: {settings.AWS_S3_CUSTOM_DOMAIN}")
    print(f"DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}")
    print(f"MEDIA_URL: {settings.MEDIA_URL}")
    
    # Test basic connection
    print("\n=== TESTING STORAGE CONNECTION ===")
    try:
        # Test listing (should not fail even if empty)
        files = default_storage.listdir('')
        print("✓ Successfully connected to storage")
        print(f"Root directories: {files[0] if files else 'Empty'}")
    except Exception as e:
        print(f"✗ Storage connection failed: {e}")
        return False
    
    # Test file upload
    print("\n=== TESTING FILE UPLOAD ===")
    try:
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='red')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)
        
        # Upload test file
        test_file = ContentFile(img_io.getvalue(), name='debug_test.jpg')
        saved_path = default_storage.save('test/debug_test.jpg', test_file)
        print(f"✓ File uploaded successfully: {saved_path}")
        
        # Check if file exists
        if default_storage.exists(saved_path):
            print("✓ File exists in storage")
            
            # Get URL
            file_url = default_storage.url(saved_path)
            print(f"✓ File URL: {file_url}")
            
            # Clean up
            default_storage.delete(saved_path)
            print("✓ Test file cleaned up")
            
        else:
            print("✗ File does not exist in storage after upload")
            return False
            
    except Exception as e:
        print(f"✗ File upload failed: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n=== ALL TESTS PASSED ===")
    return True

def test_media_upload_path():
    """Test the specific media upload paths used by your models."""
    print("\n=== TESTING MODEL UPLOAD PATHS ===")
    
    try:
        # Test article featured image path
        from overslot.models import Article
        article = Article()
        # This simulates what happens when you upload through admin
        test_path = article.featured_image.field.upload_to
        print(f"Article featured_image upload_to: {test_path}")
        
        # Test ranking featured image path  
        from overslot.models import Ranking
        ranking = Ranking()
        test_path = ranking.featured_image.field.upload_to
        print(f"Ranking featured_image upload_to: {test_path}")
        
        print("✓ Model upload paths configured correctly")
        
    except Exception as e:
        print(f"✗ Error testing model paths: {e}")

if __name__ == "__main__":
    print("Django Storage Debug Script")
    print("===========================")
    
    success = test_storage_configuration()
    test_media_upload_path()
    
    if success:
        print("\n✅ Storage appears to be configured correctly!")
        print("If uploads still don't work, check:")
        print("1. DigitalOcean Spaces CORS settings")
        print("2. Django admin file upload permissions")
        print("3. Browser network tab for upload errors")
    else:
        print("\n❌ Storage configuration has issues that need to be resolved.") 