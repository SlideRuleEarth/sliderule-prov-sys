import pytest
import logging
import sys
import os
import pathlib
import json
from importlib import import_module
from decimal import *
from django.urls import reverse
from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,call_process_state_change
# Import the fixtures
from users.tests.utilities_for_unit_tests import TEST_USER,TEST_PASSWORD,DEV_TEST_USER,DEV_TEST_PASSWORD,TEST_ORG_NAME
from users.models import OwnerPSCmd,OrgNumNode,OrgAccount,PsCmdResult

module_name = 'views'
# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)

# setup logging to terminal
#level = logging.DEBUG
level = logging.INFO
logger = logging.getLogger('unit_testing')
logger.setLevel(level)
logger.info(f"parent_dir:{parent_dir}src_path:{src_path}")


@pytest.fixture()
def tasks_module():
    yield import_module(module_name)

# do all setup before running all tests here
def setup_module(tasks_module):
    logger.info('---setup complete---')
    

# teardown after running all tests 
def teardown_module(tasks_module):
    logger.info('---teardown complete---')


#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_no_token(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure response when no token provided 
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    url = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,3,15])
    response = client.post(url)
    assert (response.status_code == 400)   # no token was provided

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_token(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test owner grabs token and can queue a ONN
    '''
    caplog.set_level(logging.DEBUG)
    
    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':TEST_ORG_NAME})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    assert (OwnerPSCmd.objects.count()==0)
    assert (OrgNumNode.objects.count()==0)
    # Decode the JSON response
    json_data = json.loads(response.content)    
    #logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   
