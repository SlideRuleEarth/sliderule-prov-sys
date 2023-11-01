import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER
from users.tests.utilities_for_unit_tests import init_mock_ps_server,random_test_user,init_test_environ,verify_user,mock_django_email_backend,create_test_user,check_redis_for_testing
from users.tests.conftest import TEST_USER,TEST_PASSWORD,DEV_TEST_USER,DEV_TEST_PASSWORD,TEST_ORG_NAME
from datetime import datetime, timezone, timedelta
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.cache import cache


import logging
logger = logging.getLogger('unit_testing')

@pytest.fixture
def mock_email_backend(mocker):
    mock_django_email_backend(mocker)

@pytest.fixture
def create_TEST_USER():
    create_test_user(first_name="Test", last_name="User", username=TEST_USER, email=TEST_EMAIL, password=TEST_PASSWORD)

@pytest.fixture
def the_TEST_USER():
    return get_user_model().objects.get(username=TEST_USER)


@pytest.fixture
def random_TEST_USER():
    user = random_test_user()
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


