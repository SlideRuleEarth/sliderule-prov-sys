import pytest
import logging
from unittest.mock import patch, MagicMock, Mock
############# These are shared between ps_web and api ################


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

def log_schedule_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit-testing')
    logger.info(f"schedule_process_state_change args:{args} kwargs:{kwargs}")    


@pytest.fixture
def mock_schedule_process_state_change():
    '''
    This fixture is used to mock the schedule_process_state_change function.
    It is used in the test cases to verify that the function is called.
    '''
    with patch("users.tasks.schedule_process_state_change") as mock:
        #mock.side_effect = log_schedule_process_state_change
        yield mock


def log_tasks_enqueue_process_state_change(*args, **kwargs):
    logger = logging.getLogger('unit-testing')
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
    logger = logging.getLogger('unit-testing')
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

