# Test with more debugging
import sesame.settings as sesame_settings

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth.models import User

from overslot import models, utils

from sesame.utils import get_token, create_token, get_user

import sesame
import inspect
import base64

class Command(BaseCommand):
    def handle(self, *args, **options):

        # Test with the sesame backend now properly configured
        print('=== Testing with sesame backend in AUTHENTICATION_BACKENDS ===')

        # Check the settings
        from django.conf import settings
        print(f'Authentication backends: {settings.AUTHENTICATION_BACKENDS}')

        # Test authenticate again
        from django.contrib.auth import authenticate
        token = "AAAAAQor0WRLpOC5zpDHPtQu"

        auth_result = authenticate(request=None, sesame=token)
        print(f'authenticate(request=None, sesame=token): {auth_result}')

        # Test the full get_user function
        from sesame.utils import get_user
        get_user_result = get_user(token)
        print(f'get_user(token): {get_user_result}')

        # Generate a new token and test it
        user = User.objects.first()
        new_token = get_token(user)
        print(f'New token: {new_token}')

        new_auth_result = authenticate(request=None, sesame=new_token)
        print(f'authenticate(new_token): {new_auth_result}')

        new_get_user_result = get_user(new_token)
        print(f'get_user(new_token): {new_get_user_result}')