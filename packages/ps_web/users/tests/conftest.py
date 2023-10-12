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


@pytest.fixture(scope='session', autouse=True)
def setup_logging():
    # Create a custom logger
    logger = logging.getLogger('unit-testing')
    # Set level of logging
    #logger.setLevel(logging.ERROR)
    logger.setLevel(logging.INFO)
    #logger.setLevel(logging.DEBUG)

    # Create handlers
    console_handler = logging.StreamHandler()
    #console_handler.setLevel(logging.ERROR)
    console_handler.setLevel(logging.INFO)
    #console_handler.setLevel(logging.DEBUG)

    # Create formatter and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)

    yield logger  # provide the fixture value

    # After the test session, remove the handler to avoid logging duplicate messages
    logger.removeHandler(console_handler)


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

@pytest.fixture
def initialize_test_environ(setup_logging,request):
    logger = setup_logging
    version = 'latest'
    is_public = False
    settings.DEBUG = True

    check_redis_for_testing(logger=logger,log_label="initialize_test_environ")

    if hasattr(request, "param"):
        if 'version' in request.param:
            version = request.param['version']
        if 'is_public' in request.param:
            is_public = request.param['is_public']
    
    logger.info(f"init version: {version}")
    logger.info(f"is_public: {is_public}")
    orgAccountObj,owner = init_test_environ(the_logger=logger,
                                            name=TEST_ORG_NAME,
                                            org_owner=None,
                                            max_allowance=20000, 
                                            monthly_allowance=1000,
                                            balance=2000,
                                            fytd_accrued_cost=100, 
                                            most_recent_charge_time=datetime.now(timezone.utc), 
                                            most_recent_credit_time=datetime.now(timezone.utc),
                                            most_recent_recon_time=datetime.now(timezone.utc),
                                            version=version,
                                            is_public=is_public)
    logger.info(f"finished initializing org:{orgAccountObj.name} owner:{orgAccountObj.owner.username}")


@pytest.fixture
def mock_redis_interface():
    with patch("users.tasks.get_PROVISIONING_DISABLED", return_value=False), \
         patch("users.tasks.django_rq") as mock_django_rq, \
         patch("users.tasks.cache") as mock_cache, \
         patch("users.tasks.Job") as mock_Job:
        
        yield {
            'mock_django_rq': mock_django_rq,
            'mock_cache': mock_cache,
            'mock_Job': mock_Job,
        }
def log_enqueue_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit-testing')
    logger.info(f"enqueue_process_state_change args:{args} kwargs:{kwargs}")    





# Create a fixture that mocks RQ scheduler
@pytest.fixture
def mock_rq_scheduler():
    with patch("django_rq.get_scheduler", autospec=True) as mock_get_scheduler:
        # Create a Mock object for the scheduler instance
        mock_scheduler = Mock()
        
        # Mock the enqueue_in method (or any other methods you use on the scheduler)
        mock_scheduler.enqueue_in = Mock()
        mock_scheduler.cron = Mock()
        mock_scheduler.enqueue_at = Mock()
        mock_scheduler.enqueue = Mock()
        # Mock job and related methods
        mock_job = Mock()
        mock_job.get_redis_server_version = Mock(return_value=(4, 0, 0)) 
        # Making _create_job return our mock job
        mock_scheduler._create_job = Mock(return_value=mock_job)
        
        # Returning mock scheduler to the calling context
        mock_get_scheduler.return_value = mock_scheduler
        yield mock_scheduler

@pytest.fixture
def mock_django_rq(mock_rq_scheduler):
    with patch("users.tasks.django_rq") as mock:
        yield mock

@pytest.fixture
def mock_enqueue_stubbed_out(mock_django_rq):
    '''
    This fixture is used to mock the enqueue_process_state_change function.
    It is used in the test cases to verify that the function is called.
    '''
    with patch("users.views.enqueue_process_state_change") as mock:
        mock.side_effect = log_enqueue_process_state_change
        yield mock


@pytest.fixture
def mock_enqueue_synchronous():
    '''
    This fixture is used to mock the enqueue_process_state_change function.
    It is used in the test cases to verify that the function is called.
    and calls the function synchronously instead of queuing it.
    '''
    with patch("users.views.enqueue_process_state_change") as mock:
        mock.side_effect = process_state_change 
        yield mock
