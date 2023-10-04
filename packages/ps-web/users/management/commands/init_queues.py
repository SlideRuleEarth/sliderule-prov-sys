from django.core.management.base import BaseCommand, CommandError
import logging
from users.utils import init_redis_queues

LOG = logging.getLogger('django')

class Command(BaseCommand):
    help = 'initialize queues'

    def handle(self, *args, **kwargs):
        try: 
            init_redis_queues()
        except Exception as e:
            LOG.error(f"Caught an exception: {e}")
            raise CommandError('Initalize queues failed.')
