import pytest
import logging
import sys
import os
import pathlib
import uuid
import json
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from django.urls import reverse,resolve
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER,OWNER_USER,OWNER_PASSWORD

from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster,PsCmdResult
from users.tasks import init_new_org_memberships

module_name = 'views'
# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
import views


# setup logging to terminal
#level = logging.DEBUG
level = logging.INFO
logger = logging.getLogger('unit_testing')
logger.setLevel(level)

@pytest.fixture()
def tasks_module():
    yield import_module(module_name)

# do all setup before running all tests here
def setup_module(tasks_module):
    logger.info('------')
    

# teardown after running all tests 
def teardown_module(tasks_module):
    logger.info('------')

#@pytest.mark.dev
@pytest.mark.django_db
def test_token(tasks_module,caplog,client,initialize_test_environ):
    '''
        This procedure will test the obtain token api
    '''
    caplog.set_level(logging.DEBUG)
    time_now = datetime.now(timezone.utc)
    caplog.set_level(logging.DEBUG)
    url = reverse('org-token-obtain-pair')
    data = {'username': OWNER_USER, 'password': OWNER_PASSWORD, 'org_name': 'wrongOrgName'}
    response = client.post(url,data)
    assert (response.status_code == 403) # first pass is wrong org
    data = {'username': OWNER_USER, 'password': TEST_PASSWORD, 'org_name': TEST_ORG_NAME}
    response = client.post(url,data)
    assert (response.status_code == 401) # wrong password
    data = {'username': OWNER_USER, 'password': OWNER_PASSWORD, 'org_name': TEST_ORG_NAME}
    response = client.post(url,data)
    assert (response.status_code == 200) # first pass is 

#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_token_refresh(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, mock_email_backend,initialize_test_environ):
    '''
        This procedure will test owner grabs token and can use refresh token to get new token
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    
    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    json_data = json.loads(response.content)
    logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   
    refresh_token = json_data['refresh']
    response = client.post(reverse('org-token-refresh'),data={'refresh':refresh_token})
    assert (response.status_code == 200)
    json_data = json.loads(response.content)    
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0') 
    refresh_token = json_data['refresh']
    response = client.post(reverse('org-token-refresh'),data={'refresh':refresh_token})
    #assert (response.status_code == 200)
    json_data = json.loads(response.content)    
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0') 
    assert(response.status_code == 200)

    # now try to reuse a refresh token that was valid but used (and therefore blacklisted)
    response = client.post(reverse('org-token-refresh'),data={'refresh':refresh_token})
    assert (response.status_code == 401)
    


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_token_github_refresh(caplog,client, social_user, social_user_membership, github_social_account, mock_email_backend,initialize_test_environ):
    '''
        This procedure will test using a refresh token obtained from a github access token that matches a github social account to get org token and can queue a ONN
        You must set the GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN to a valid github access token for github account devtester-sliderule
    '''

    GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN = os.environ.get('GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN')
    assert GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN is not None
    caplog.set_level(logging.DEBUG)
    assert social_user_membership.user == social_user
    assert social_user_membership.org == get_test_org()
    
    url = reverse('org-token-github-obtain-pair')
   
    response = client.post(url,data={'access_token':GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN,'org_name':TEST_ORG_NAME})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    assert (OwnerPSCmd.objects.count()==0)
    assert (OrgNumNode.objects.count()==0)
    # Decode the JSON response
    json_data = json.loads(response.content)    
    #logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0') 
    refresh_token = json_data['refresh']
    response = client.post(reverse('org-token-refresh'),data={'refresh':refresh_token})
    assert (response.status_code == 200)
    json_data = json.loads(response.content)    
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0') 

    # now try to reuse a refresh token that was valid but used (and therefore blacklisted)
    response = client.post(reverse('org-token-refresh'),data={'refresh':refresh_token})
    assert (response.status_code == 401)

