#!/usr/bin/env python3
"""
Detailed debug script to identify storage upload issues.
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
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

def test_boto3_direct():
    """Test direct boto3 connection to see if credentials work"""
    print("=== TESTING DIRECT BOTO3 CONNECTION ===")
    
    try:
        # Create boto3 client directly
        session = boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        
        client = session.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Test listing bucket contents
        response = client.list_objects_v2(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Prefix='media/'
        )
        
        print("✓ Direct boto3 connection successful")
        
        if 'Contents' in response:
            print(f"Found {len(response['Contents'])} files in media/ folder:")
            for obj in response['Contents'][:5]:  # Show first 5 files
                print(f"  - {obj['Key']} (size: {obj['Size']} bytes)")
        else:
            print("No files found in media/ folder")
        
        # Test direct upload
        print("\n=== TESTING DIRECT BOTO3 UPLOAD ===")
        test_content = b"Direct boto3 test file"
        
        client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key='media/test/direct_boto3_test.txt',
            Body=test_content,
            ACL='public-read'
        )
        
        print("✓ Direct boto3 upload successful")
        
        # Verify file exists
        try:
            response = client.head_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key='media/test/direct_boto3_test.txt'
            )
            print(f"✓ File verified in storage (size: {response['ContentLength']} bytes)")
            
            # Test URL
            url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/test/direct_boto3_test.txt"
            print(f"Direct upload URL: {url}")
            
        except ClientError as e:
            print(f"✗ File not found after upload: {e}")
        
        return True
        
    except NoCredentialsError:
        print("✗ AWS credentials not found or invalid")
        return False
    except ClientError as e:
        print(f"✗ AWS client error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def debug_django_storage():
    """Debug Django's storage backend"""
    print("\n=== DEBUGGING DJANGO STORAGE BACKEND ===")
    
    # Check storage class details
    storage = default_storage
    print(f"Storage class: {type(storage).__name__}")
    print(f"Storage module: {type(storage).__module__}")
    
    # Check storage attributes
    attrs_to_check = [
        'bucket_name', 'location', 'access_key', 'secret_key', 
        'endpoint_url', 'region_name', 'default_acl'
    ]
    
    for attr in attrs_to_check:
        if hasattr(storage, attr):
            value = getattr(storage, attr)
            if 'key' in attr.lower():
                value = "***HIDDEN***" if value else "Not Set"
            print(f"  {attr}: {value}")
    
    # Test with very verbose output
    print("\n=== TESTING DJANGO STORAGE WITH VERBOSE OUTPUT ===")
    
    try:
        # Create test content
        img = Image.new('RGB', (50, 50), color='blue')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)
        
        test_file = ContentFile(img_io.getvalue(), name='django_test.jpg')
        
        print(f"Created test file, size: {len(img_io.getvalue())} bytes")
        
        # Save with Django
        saved_path = storage.save('media/test/django_verbose_test.jpg', test_file)
        print(f"Django save() returned: {saved_path}")
        
        # Check if Django thinks it exists
        exists = storage.exists(saved_path)
        print(f"storage.exists() returns: {exists}")
        
        if exists:
            # Get file size
            try:
                size = storage.size(saved_path)
                print(f"storage.size() returns: {size} bytes")
            except Exception as e:
                print(f"storage.size() error: {e}")
            
            # Get URL
            try:
                url = storage.url(saved_path)
                print(f"storage.url() returns: {url}")
            except Exception as e:
                print(f"storage.url() error: {e}")
        
        return saved_path
        
    except Exception as e:
        print(f"✗ Django storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_settings_values():
    """Check all relevant settings values"""
    print("\n=== CHECKING ALL SETTINGS VALUES ===")
    
    settings_to_check = [
        'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_STORAGE_BUCKET_NAME',
        'AWS_S3_ENDPOINT_URL', 'AWS_S3_REGION_NAME', 'AWS_S3_CUSTOM_DOMAIN',
        'AWS_DEFAULT_ACL', 'DEFAULT_FILE_STORAGE', 'MEDIA_URL'
    ]
    
    for setting_name in settings_to_check:
        try:
            value = getattr(settings, setting_name)
            if 'KEY' in setting_name:
                display_value = "***SET***" if value else "NOT SET"
            else:
                display_value = value
            print(f"{setting_name}: {display_value}")
        except AttributeError:
            print(f"{setting_name}: NOT DEFINED")

if __name__ == "__main__":
    print("DETAILED DJANGO STORAGE DEBUG")
    print("=============================\n")
    
    test_settings_values()
    
    boto3_works = test_boto3_direct()
    django_path = debug_django_storage()
    
    print("\n=== SUMMARY ===")
    print(f"Direct boto3 upload: {'✓ Works' if boto3_works else '✗ Failed'}")
    print(f"Django storage upload: {'✓ Works' if django_path else '✗ Failed'}")
    
    if boto3_works and not django_path:
        print("\n🔍 DIAGNOSIS: Direct boto3 works but Django doesn't.")
        print("This suggests a configuration issue with the Django storage backend.")
        print("Check the storage class configuration in settings.")
    elif not boto3_works:
        print("\n🔍 DIAGNOSIS: Direct boto3 connection failed.")
        print("This suggests an issue with AWS credentials or endpoint configuration.")
    else:
        print("\n🤔 Both tests claim to work but files don't appear.")
        print("This might be a permission issue or the files are going somewhere unexpected.") 