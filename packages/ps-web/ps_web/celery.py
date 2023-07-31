from __future__ import absolute_import, unicode_literals
import os
from celery import Celery,Task
from django.conf import settings

import logging
LOG = logging.getLogger('django')
LOG.propagate = False

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ps_web.settings')

app = Celery('ps_web')
# namespace='CELERY' means all celery-related configuration keys
# should be uppercased and have a `CELERY_` prefix in Django settings.
# https://docs.celeryproject.org/en/stable/userguide/configuration.html
app.config_from_object(settings, namespace='CELERY')
# When we use the following in Django, it loads all the <appname>.tasks
# files and registers any tasks it finds in them. We can import the
# tasks files some other way if we prefer.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
