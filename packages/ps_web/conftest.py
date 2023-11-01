import pytest
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, Mock
from django.conf import settings
from users.tests.utilities_for_unit_tests import init_test_environ,init_mock_ps_server,check_redis_for_testing,TEST_ORG_NAME


############# These are shared between ps_web and api ################


@pytest.fixture(scope='session', autouse=True)
def setup_logging():
    # Create a custom logger
    logger = logging.getLogger('unit_testing')
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

def log_schedule_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit_testing')
    logger.info(f"schedule_process_state_change args:{args} kwargs:{kwargs}")    


@pytest.fixture
def mock_schedule_process_state_change():
    '''
    This fixture is used to mock the schedule_process_state_change function.
    It is used in the test cases to verify that the function is called.
    '''
    with patch("users.tasks.schedule_process_state_change") as mock:
        yield mock


def log_tasks_enqueue_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit_testing')
    logger.info(f"stub tasks_enqueue_process_state_change args:{args} kwargs:{kwargs}")    

@pytest.fixture
def mock_tasks_enqueue_stubbed_out():
    '''
    This fixture is used to mock the enqueue_process_state_change function.
    It is used in the test cases to verify that the function is called.
    '''
    with patch("users.tasks.enqueue_process_state_change") as mock:
        mock.side_effect = log_tasks_enqueue_process_state_change
        yield mock

def log_views_enqueue_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit_testing')
    logger.info(f"stub views_enqueue_process_state_change args:{args} kwargs:{kwargs}")    

@pytest.fixture
def mock_views_enqueue_stubbed_out():
    '''
    This fixture is used to mock the enqueue_process_state_change function.
    It is used in the test cases to verify that the function is called.
    '''
    with patch("users.views.enqueue_process_state_change") as mock:
        mock.side_effect = log_views_enqueue_process_state_change
        yield mock

@pytest.fixture
def initialize_test_environ(setup_logging,request):
    logger = setup_logging
    version = 'latest'
    is_public = True
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
    logger.info(f"org:{orgAccountObj.name} owner:{orgAccountObj.owner.username}")

@pytest.fixture
def initialize_mock_ps_server_and_test_environ(setup_logging,request):

    logger = setup_logging
    version = 'latest'
    is_public = False
    num_nodes = 0

    if hasattr(request, "param"):
        if 'version' in request.param:
            version = request.param['version']
        else:
            version = 'latest'
        if 'is_public' in request.param:
            is_public = request.param['is_public']
        else:
            is_public = False
        if 'num_nodes' in request.param:
            num_nodes = request.param['num_nodes']
        else:
            num_nodes = 0
    logger.info(f"version: {version}")
    logger.info(f"is_public: {is_public}")
    logger.info(f"num_nodes: {num_nodes}")
    init_mock_ps_server(logger=logger,version=version,is_public=is_public,num_nodes=num_nodes)
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
    logger.info(f"org:{orgAccountObj.name} owner:{orgAccountObj.owner.username}")

