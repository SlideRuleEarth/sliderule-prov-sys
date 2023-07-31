from django.core.management.base import BaseCommand, CommandError
import logging
from users.utils import get_ps_server_versions

LOG = logging.getLogger('django')

class Command(BaseCommand):
    help = 'get ps_server versions (code and deploy env)'

    def handle(self, *args, **kwargs):
        try: 
            get_ps_server_versions()
        except Exception as e:
            LOG.error(f"Caught an exception: {e}")
            raise CommandError('get ps_server versions FAILED.')
