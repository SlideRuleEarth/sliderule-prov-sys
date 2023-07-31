import pytest
import logging

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

def pytest_addoption(parser):
    parser.addoption("--domain", action="store", default="testsliderule.org")
    parser.addoption("--asset", action="store", default="icesat2")
    parser.addoption("--organization", action="store", default="UofMDTest")
    parser.addoption("--desired_nodes", action="store", default=2)

@pytest.fixture(scope='session')
def domain(request):
    value = request.config.option.domain
    if value is None:
        pytest.skip()
    return value

@pytest.fixture(scope='session')
def asset(request):
    value = request.config.option.asset
    if value is None:
        pytest.skip()
    return value

@pytest.fixture(scope='session')
def organization(request):
    value = request.config.option.organization
    if value == "None":
        value = None
    return value

@pytest.fixture(scope='session')
def desired_nodes(request):
    value = request.config.option.desired_nodes
    if value is not None:
        if value == "None":
            value = None
        else:
            value = int(value)
    return value