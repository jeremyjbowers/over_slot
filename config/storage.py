"""
Custom storage backends for DigitalOcean Spaces
"""
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class StaticStorage(S3Boto3Storage):
    """Custom storage for static files"""
    location = 'static'
    default_acl = 'public-read'


class MediaStorage(S3Boto3Storage):
    """Custom storage for media files (uploads)"""
    location = 'media'
    default_acl = 'public-read'
    file_overwrite = False 