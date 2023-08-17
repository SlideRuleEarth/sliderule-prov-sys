import pytest
import logging
import sys
import os
import pathlib
import uuid
import json
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from django.urls import reverse,resolve
from users.tests.conftest import initialize_test_environ
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER,OWNER_USER,OWNER_PASSWORD

from users.models import Membership
from users.tasks import init_new_org_memberships

module_name = 'views'
# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
import views


# setup logging to terminal
#level = logging.DEBUG
level = logging.INFO
#logger = logging.getLogger(__name__)
logger = logging.getLogger('django')
logger.setLevel(level)

@pytest.fixture()
def tasks_module():
    yield import_module(module_name)

# do all setup before running all tests here
def setup_module(tasks_module):
    logger.info('------')
    

# teardown after running all tests 
def teardown_module(tasks_module):
    logger.info('------')

#@pytest.mark.dev
@pytest.mark.django_db
def test_token(tasks_module,caplog,client,initialize_test_environ):
    '''
        This procedure will test the obtain token api
    '''
    caplog.set_level(logging.DEBUG)
    time_now = datetime.now(timezone.utc)
    caplog.set_level(logging.DEBUG)
    url = reverse('org-token-obtain-pair')
    data = {'username': OWNER_USER, 'password': OWNER_PASSWORD, 'name': 'wrongOrgName'}
    response = client.post(url,data)
    assert (response.status_code == 403) # first pass is wrong org
    data = {'username': OWNER_USER, 'password': TEST_PASSWORD, 'name': TEST_ORG_NAME}
    response = client.post(url,data)
    assert (response.status_code == 401) # wrong password
    data = {'username': OWNER_USER, 'password': OWNER_PASSWORD, 'name': TEST_ORG_NAME}
    response = client.post(url,data)
    assert (response.status_code == 200) # first pass is 
