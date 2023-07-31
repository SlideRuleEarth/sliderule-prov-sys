import unittest
import pytest
import os

from users.tests.global_test import GlobalTestCase
from users.utils import get_org_queue_name_str,get_ps_server_versions,get_ps_server_versions_from_env
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,pytest_approx,the_TEST_USER,init_mock_ps_server


import logging
logger = logging.getLogger('test_console')


class UtilsTest(GlobalTestCase):
    def setUp(self):
        #logger.info(f"{__name__}({self}) ... ------------------")
        return super().setUp()

    def tearDown(self):
        #logger.info(f"{__name__}({self}) ... ------------------")
        return super().tearDown()   

    def test_get_org_queue_name_str(self):
        #logger.info(f"{__name__}({self}) ... ------------------")
        assert(get_org_queue_name_str("testit")==f"ps-cmd-testit")

#@pytest.mark.dev
@pytest.mark.django_db
def test_get_ps_server_versions():

    PS_SERVER_DOCKER_TAG,PS_SERVER_GIT_VER = get_ps_server_versions()
    logger.info(f"PS_SERVER_DOCKER_TAG={PS_SERVER_DOCKER_TAG} PS_SERVER_GIT_VER={PS_SERVER_GIT_VER}")
    assert(PS_SERVER_DOCKER_TAG==os.environ.get("PS_SERVER_DOCKER_TAG")) # global tests with real ps_server use latest tag and local tests use stubbed ps_server which has dev tag

#@pytest.mark.dev
@pytest.mark.django_db
def test_get_ps_server_versions_from_env():

    PS_SERVER_DOCKER_TAG,PS_SERVER_GIT_VER = get_ps_server_versions()
    logger.info(f"PS_SERVER_DOCKER_TAG={PS_SERVER_DOCKER_TAG} PS_SERVER_GIT_VER={PS_SERVER_GIT_VER}")
    assert(PS_SERVER_DOCKER_TAG==os.environ.get("PS_SERVER_DOCKER_TAG")) # global tests with real ps_server use latest tag and local tests use stubbed ps_server which has dev tag

    PS_SERVER_DOCKER_TAG,PS_SERVER_GIT_VER = get_ps_server_versions_from_env()
    logger.info(f"PS_SERVER_DOCKER_TAG={PS_SERVER_DOCKER_TAG} PS_SERVER_GIT_VER={PS_SERVER_GIT_VER}")
    assert(PS_SERVER_DOCKER_TAG==os.environ.get("PS_SERVER_DOCKER_TAG")) # global tests with real ps_server use latest tag and local tests use stubbed ps_server which has dev tag
