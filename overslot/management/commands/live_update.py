from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from overslot import models, utils


class Command(BaseCommand):
    def handle(self, *args, **options):
        pass