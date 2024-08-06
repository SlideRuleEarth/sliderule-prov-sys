import pytest
import boto3
from botocore.client import Config  # Make sure to import Config

from django.contrib.auth import get_user_model
from django.core import mail
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER,create_test_user
from users.tests.utilities_for_unit_tests import random_test_user,init_test_environ,verify_user,mock_django_email_backend,get_test_org,call_SetUp,check_for_scheduled_jobs,check_redis_for_testing,clear_enqueue_process_state_change
from users.models import Cluster,OrgNumNode
from users.tasks import process_state_change,log_scheduled_jobs
from datetime import datetime, timezone, timedelta
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from unittest.mock import patch, MagicMock, Mock
from time import sleep
from django.core.cache import cache
import time

import logging
from importlib import import_module

import requests
import time

def poll_for_localstack_status(logger):
    '''
    Checks the status of localstack. This is only called when the domain is localhost
    '''
    # wait for localstack to be ready
    start_time = time.time()
    error_encountered = False  # Flag to track if an error is encountered
    elapsed_time = 0
    logger.info("Polling --- Waiting for LocalStack to be ready ---")
    cnt = 0
    session = requests.Session()
    while cnt < 100: # can't poll forever
        response = None
        try:
            elapsed_time = time.time() - start_time
            if elapsed_time > 1:
               time.sleep(1) 
            else:
               time.sleep(0.1)
            response = session.get('http://localstack:4566/_localstack/init')
            logger.debug(f"response:{response}")
            response.raise_for_status()  # will raise an exception if the status is not 200
            data = response.json()
            logger.debug(f"data:{data}")
            for completed in data.get('completed', []):
                logger.debug(f"completed:{completed}")
                if data['completed']['READY'] == True:
                    logger.info("LocalStack is ready")
                    return  True # exit the loop and the fixture
        except requests.exceptions.HTTPError as e:
            logger.info(f"LocalStack not ready yet e:{e}")
        except requests.exceptions.ConnectionError as e:
            logger.info(f"LocalStack not ready yet e:{e}")
        except Exception as e:
            logger.exception(f"Exception:{e}")
            error_encountered = True
        cnt += 1

        if error_encountered:
            logger.error("Error encountered during LocalStack setup")
            logger.info(f"elapsed_time:{elapsed_time} secs cnt:{cnt}")
            break
        if elapsed_time > 15:  # timeout 
            logger.error("Timeout while waiting for LocalStack to be ready")
            logger.info(f"elapsed_time:{elapsed_time} secs cnt:{cnt}")
            break
    logger.info(f"elapsed_time:{elapsed_time} secs cnt:{cnt}")
    return False



@pytest.fixture(scope="session", autouse=True)
def redis_scheduled_jobs_setup(setup_logging):
    logger = setup_logging
    check_redis_for_testing(logger,__name__)
    assert(check_for_scheduled_jobs(logger,__name__,3)) # three cron jobs in docker init script
    jobs = log_scheduled_jobs()
    assert (len(jobs) == 3)

@pytest.fixture(scope="session")
def s3(setup_logging):
    logger = setup_logging
    logger.info(f'-------#####   using localstack s3   #####-----')
    # uses localstack
    s3_client = boto3.client(
        's3', 
        region_name='us-west-2',
        endpoint_url="http://localstack:4566",
        aws_access_key_id='dummy_access_key',
        aws_secret_access_key='dummy_secret_key',
        config=Config(signature_version='s3v4')
        )
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

@pytest.fixture(scope="session", autouse=True)
def localstack_setup(setup_logging):
    # wait for localstack to be ready
    start_time = time.time()
    logger = setup_logging
    assert poll_for_localstack_status(logger), "LocalStack is not running or failed to initialize"   
    return True


@pytest.fixture
def initialize_test_environ(setup_logging,redis_scheduled_jobs_setup,request):
    logger = setup_logging
    version = 'latest'
    is_public = False
    settings.DEBUG = True
    OrgNumNode.objects.all().delete()

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
    clear_enqueue_process_state_change(logger)
