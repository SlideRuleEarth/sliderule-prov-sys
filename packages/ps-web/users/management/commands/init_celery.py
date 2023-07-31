from django.core.management.base import BaseCommand, CommandError
import logging
from users.utils import init_celery

LOG = logging.getLogger('django')

class Command(BaseCommand):
    help = 'initialize celery'

    def handle(self, *args, **kwargs):
        try: 
            init_celery()
        except Exception as e:
            LOG.error(f"Caught an exception: {e}")
            raise CommandError('Initalize celery failed.')
