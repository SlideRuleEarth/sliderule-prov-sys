from django.apps import AppConfig
import logging
LOG = logging.getLogger('django')


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        # can add code here if needed
        LOG.info("Users Ready")
