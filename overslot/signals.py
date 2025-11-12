from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def normalize_user_email_and_username(sender, instance: User, **kwargs):
    email = getattr(instance, "email", None)
    if email:
        instance.email = email.strip().lower()
    username = getattr(instance, "username", None)
    if username:
        instance.username = username.strip().lower()


