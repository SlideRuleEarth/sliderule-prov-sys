import unittest
import pytest
import os

from users.tests.global_test import GlobalTestCase
from users.utils import get_ps_server_versions,get_ps_server_versions_from_env,disable_provisioning
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,pytest_approx,the_TEST_USER,init_mock_ps_server,the_DEV_TEST_USER,initialize_test_org,create_test_org,TEST_ORG_NAME
from users.tasks import get_org_queue_name_str
from users.models import OrgAccount

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

#@pytest.mark.dev
@pytest.mark.django_db
def test_disable_provisioning_function(test_name,developer_TEST_USER,initialize_test_environ):
    orgAccountObj = OrgAccount.objects.get(name=TEST_ORG_NAME)
    error_msg, disable_msg, rsp_msg = disable_provisioning(orgAccountObj.owner,f'{orgAccountObj.owner} is disabling provisioning for testing')
    assert('is not a Authorized' in error_msg) # negative test with unauthorized user

    authorized_user = developer_TEST_USER
    error_msg, disable_msg, rsp_msg = disable_provisioning(authorized_user,f'{authorized_user} is disabling provisioning for testing')
    logger.info(f"error_msg:{error_msg} disable_msg:{disable_msg} rsp_msg:{rsp_msg}")
    assert(error_msg=='')
    assert(f"User:{authorized_user} has disabled provisioning!" in disable_msg)
    assert('Setting provisioning_suspended to True for the following orgs:' in disable_msg)
    assert(f'{orgAccountObj.name}' in disable_msg)
    assert(rsp_msg=='')
    orgs_qs = OrgAccount.objects.all()
    assert(orgs_qs.count()==1),f"orgs_qs.count()={orgs_qs.count()}"
    for org in orgs_qs:
        org.refresh_from_db()
        assert org.name==TEST_ORG_NAME,f"org.name={org.name} test_name={test_name}"
        assert(org.provisioning_suspended),f"org:{org.name} FAILED to set provisioning_suspended for:{org.provisioning_suspended}"
