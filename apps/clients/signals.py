import logging
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from .models import Client

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def create_client_profile(sender, instance, created, **kwargs):
    """Crée automatiquement un profil Client à la création d'un User."""
    if created:
        try:
            Client.objects.get_or_create(user=instance)
        except Exception as e:
            logger.error("Impossible de créer le profil Client pour l'user %s : %s", instance.pk, e)
