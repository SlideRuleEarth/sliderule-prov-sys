import pytest
import boto3

from django.contrib.auth import get_user_model
from django.core import mail
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER,create_test_user
from users.tests.utilities_for_unit_tests import random_test_user,init_test_environ,verify_user,mock_django_email_backend,get_test_org,call_SetUp,check_redis_for_testing
from users.models import Cluster
from users.tasks import process_state_change
from datetime import datetime, timezone, timedelta
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from unittest.mock import patch, MagicMock, Mock

import logging
from importlib import import_module


@pytest.fixture(scope="session")
def s3(setup_logging):
    logger = setup_logging
    # uses localstack
    s3_client = boto3.client('s3', region_name='us-west-2',endpoint_url="http://localstack:4566")
    yield s3_client
    logger.info(f'verify teardown of localstack s3 with s3_client:{s3_client} ')

@pytest.fixture(scope='session', autouse=True)
def test_name():
    return 'unit-test-org' 

@pytest.fixture(autouse=True)
def set_test_site(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        Site.objects.update_or_create(id=2, defaults={'domain': 'localhost', 'name': 'localhost'})

@pytest.fixture()
def tasks_module_to_import(request):
    yield import_module(request.param)


@pytest.fixture
def mock_email_backend(mocker):
    mock_django_email_backend(mocker)

@pytest.fixture
def create_TEST_USER():
    user = create_test_user(first_name="Test", last_name="User", username=TEST_USER, email=TEST_EMAIL, password=TEST_PASSWORD)
    return user


@pytest.fixture
def random_TEST_USER(setup_logging):
    user = random_test_user()
    logger = setup_logging
    logger.info(f"random_TEST_USER username:{user.username} password:{user.password}")   
    return user


@pytest.fixture
def developer_TEST_USER(setup_logging):
    logger = setup_logging
    ps_developer_group, _ = Group.objects.get_or_create(name="PS_Developer")
    dev_user = create_test_user(first_name="Dev", last_name="User", username=DEV_TEST_USER, email=DEV_TEST_EMAIL, password=DEV_TEST_PASSWORD)
    dev_user.groups.add(ps_developer_group)
    logger.info(f"developer_TEST_USER username:{dev_user.username} password:{dev_user.password}")   
    return verify_user(dev_user)

@pytest.fixture
def verified_TEST_USER(create_TEST_USER):
    return verify_user(create_TEST_USER)
