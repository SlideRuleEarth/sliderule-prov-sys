import pytest
import logging
import sys
import os
import pathlib
import uuid
import pytz
import json
import pprint
import requests
import time_machine
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from django.urls import reverse
from users.tests.utilities_for_unit_tests import get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,verify_onn_expires,verify_owner_ps_Destroy_cmd,verify_owner_ps_Refresh_cmd,verify_owner_ps_Update_cmd,verify_post_org_num_nodes_ttl,verify_put_org_num_nodes
from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster
from users.forms import OrgAccountForm
from users.tasks import process_state_change,init_new_org_memberships,init_new_org_memberships,process_prov_sys_tbls,get_org_queue_name,get_or_create_OrgNumNodes,enqueue_process_state_change
from django.contrib import messages
from django.contrib.auth import get_user_model
from allauth.account.decorators import verified_email_required
from unittest.mock import patch, MagicMock

# Import the fixtures
from users.tests.utilities_for_unit_tests import TEST_USER,TEST_PASSWORD,DEV_TEST_USER,DEV_TEST_PASSWORD,TEST_ORG_NAME
from users.global_constants import *
module_name = 'views'
# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
import views

# setup logging to terminal
level = logging.DEBUG
#level = logging.INFO
#logger = logging.getLogger(__name__)
logger = logging.getLogger('django')
logger.setLevel(level)

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
def test_login(client):
    # Get the URL for the login view.
    login_url = reverse('account_login')

    # Redirect the user to the login view.
    response = client.get(login_url)
    assert response.status_code == 200
    # Set the request body.
    body = {
        'username': DEV_TEST_USER,
        'password': DEV_TEST_PASSWORD
    }

    # Make the request.
    response = client.put(login_url, json=body)

    # Assert that the response is successful.
    assert response.status_code == 200

def login_owner_user(orgAccountObj,client):
    url = reverse('org-token-obtain-pair')
    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert(OwnerPSCmd.objects.count()==0)
    json_data = json.loads(response.content)
    logger.info(f"rsp:{json_data}")
    return json_data['access']   

def simple_test_onn_api(client,
                        orgAccountObj,
                        view_name,
                        url_args,
                        access_token,
                        expected_status):
    url = reverse(view_name,args=url_args)
    logger.info(f"using url:{url}")
    if 'post' in view_name:
        response = client.post(url,headers={'Authorization': f"Bearer {access_token}"})
    else:
        response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    json_data = json.loads(response.content)
    if expected_status == 200:
        assert(json_data['msg']!='')   
        assert(json_data['error_msg']=='')
    else:
        logger.info(f"json_data:{json_data}")

    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
    orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
    logger.info(f"{response.status_code} == {expected_status} ?")
    assert(response.status_code == expected_status) 
    return json_data

#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_apis_simple_case(caplog,client,verified_TEST_USER,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test various negative test cases apis
    '''
    caplog.set_level(logging.DEBUG)
    orgAccountObj=get_test_org()
    response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    assert(response.status_code == 200)   
    json_data = json.loads(response.content)
    access_token = json_data['access']   

    # validate a success first!
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='post-org-num-nodes-ttl',
                                    url_args=[orgAccountObj.name,3,15],
                                    access_token=access_token,
                                    expected_status=200)
    assert('created and queued capacity request' in json_data['msg'])

#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_negative_test_apis(caplog,client,verified_TEST_USER,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test various negative test cases apis
    '''
    caplog.set_level(logging.DEBUG)
    orgAccountObj=get_test_org()

    # test invalid name in token
    response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':'bad_org'})
    assert(response.status_code == 403) 

    # invalid user
    response = client.post(reverse('org-token-obtain-pair'),data={'username':"bad_username",'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    assert(response.status_code == 401)    

    # bad password
    response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':"bad_passw", 'org_name':orgAccountObj.name})
    assert(response.status_code == 401)    

    # Now good parms for token
    response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    assert(response.status_code == 200)    
    access_token = json.loads(response.content)['access']   

    # test corrupted token
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='post-org-num-nodes-ttl',
                                    url_args=[orgAccountObj.name,3,15],
                                    access_token=access_token+'BAD',
                                    expected_status=403)
    assert(json_data['messages'][0]['message'] == 'Token is invalid or expired') 

    # test invalid num_nodes gets clamped
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='post-org-num-nodes-ttl',
                                    url_args=[orgAccountObj.name,300,15],
                                    access_token=access_token,
                                    expected_status=200)

    # test invalid num_nodes gets clamped
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='put-org-num-nodes',
                                    url_args=[orgAccountObj.name,300],
                                    access_token=access_token,
                                    expected_status=200)

    # test 0 num_nodes (with org accepting 0)
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='put-org-num-nodes',
                                    url_args=[orgAccountObj.name,0],
                                    access_token=access_token,
                                    expected_status=200)

    # test num_nodes less than min gets clamped
    orgAccountObj.min_node_cap = 2
    orgAccountObj.save()
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='put-org-num-nodes',
                                    url_args=[orgAccountObj.name,1],
                                    access_token=access_token,
                                    expected_status=200)
    assert (f"Deploying test_org cluster Created new " in json_data['msg'])
    assert((f'Deploying {orgAccountObj.name} cluster' in json_data['msg']) or (f'Updating {orgAccountObj.name} cluster' in json_data['msg']))

    # test num_nodes greater than max gets clamped
    orgAccountObj.save()
    json_data = simple_test_onn_api(client,
                                    orgAccountObj=orgAccountObj,
                                    view_name='put-org-num-nodes',
                                    url_args=[orgAccountObj.name,15],
                                    access_token=access_token,
                                    expected_status=200)
    assert (f"Deploying test_org cluster Created new " in json_data['msg'])
    assert((f'Updating {orgAccountObj.name} cluster' in json_data['msg']) or (f'Deploying {orgAccountObj.name} cluster' in json_data['msg']))


#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_api_urls(caplog,client,verified_TEST_USER, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, mock_email_backend,initialize_test_environ):
    '''
        This procedure will various cases for the process_state_change function
    '''
    caplog.set_level(logging.DEBUG)
    grpc_timeout = int(os.environ.get("GRPC_TIMEOUT_SECS",1800))
    timeshift = grpc_timeout/2.0
    logger.info(f"Shifting time back by {timeshift} seconds (with a grpc_timeout:{grpc_timeout})")
    fake_time_now = datetime.now(timezone.utc) - timedelta(seconds=timeshift)
    with time_machine.travel(fake_time_now,tick=False):
        orgAccountObj = get_test_org()        
        response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
        assert(response.status_code == 200)   
        json_data = json.loads(response.content)
        access_token = json_data['access'] 
        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,3,15],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,                                                            expected_change_ps_cmd=1,
                                                            expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,3,15],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0, 
                                                            expected_status='REDUNDANT')
        current_fake_tm = datetime.now(timezone.utc)+timedelta(seconds=3) # 6 iters above is 3 seconds
        loop_count,response = verify_put_org_num_nodes(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,3],
                                                        access_token=access_token,
                                                        delay_state_processing=False,
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                        expected_change_ps_cmd=0, # because no iters
                                                        expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,3,16],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0, # because highest num nodes is still 3
                                                            expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,2,17],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0,
                                                            expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,1,19],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0,
                                                            expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            url_args=[orgAccountObj.name,4,15],
                                                            access_token=access_token,
                                                            delay_state_processing=False,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=1, # we bumped the highest to 4 and iter
                                                            expected_status='QUEUED')

@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_state_change(caplog,client,mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, verified_TEST_USER,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the state change function when 
        multiple calls to enqueue_process_state_change are made 
        before a process_state_change call happens
    '''
    caplog.set_level(logging.DEBUG)
    grpc_timeout = int(os.environ.get("GRPC_TIMEOUT_SECS",1800))
    timeshift = grpc_timeout/2.0
    logger.info(f"Shifting time back by {timeshift} seconds (with a grpc_timeout:{grpc_timeout})")
    fake_time_now = datetime.now(timezone.utc) - timedelta(seconds=timeshift)
    with time_machine.travel(fake_time_now,tick=False):
    
        orgAccountObj = get_test_org()
        owner_access_token = login_owner_user(orgAccountObj=orgAccountObj,client=client)

        clusterObj = Cluster.objects.get(org=orgAccountObj)
        
        assert(OwnerPSCmd.objects.count()==0)
        assert(OrgNumNode.objects.count()==0)
        assert(orgAccountObj.num_owner_ps_cmd==0)
        assert(orgAccountObj.num_ps_cmd==0)
        assert(orgAccountObj.num_ps_cmd_successful==0)
        
        current_fake_tm = datetime.now(timezone.utc)  

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            new_time=current_fake_tm,
                                                            url_args=[orgAccountObj.name,3,15],
                                                            access_token=owner_access_token,
                                                            expected_change_ps_cmd=0,
                                                            expected_status='QUEUED',
                                                            expected_change_OrgNumNode=1,
                                                            delay_state_processing=True,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
        
        
        #
        # This tests when multiple calls to api are processed between a process_state_change
        #
        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            new_time=current_fake_tm,
                                                            url_args=[orgAccountObj.name,4,16],
                                                            access_token=owner_access_token,
                                                            delay_state_processing=True,
                                                            expected_change_OrgNumNode=1,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0,
                                                            expected_status='QUEUED')

        loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                            orgAccountObj=orgAccountObj,
                                                            new_time=current_fake_tm,
                                                            url_args=[orgAccountObj.name,2,17],
                                                            access_token=owner_access_token,
                                                            expected_change_OrgNumNode=1,
                                                            delay_state_processing=True,
                                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                            expected_change_ps_cmd=0,
                                                            expected_status='QUEUED')

        #
        #
        clusterObj.refresh_from_db() # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this

        task_idle, loop_count = process_state_change(orgAccountObj.name)
        clusterObj.refresh_from_db() # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        assert(loop_count==1)
        
        assert(OwnerPSCmd.objects.count()==0)
        assert(OrgNumNode.objects.count()==3)
        assert(orgAccountObj.num_owner_ps_cmd==0)
        


        # verify setup occurred
        assert(clusterObj.provision_env_ready)
        assert(orgAccountObj.provisioning_suspended==False)

        # this on gets updated every time a ps cmd is processed
        # regardless of where it originated from (i.e. onn or owner_ps_cmd)
        assert(orgAccountObj.num_ps_cmd==1) # update cmd
        assert(orgAccountObj.desired_num_nodes==4)
        assert(orgAccountObj.num_ps_cmd_successful==1)
        task_idle, loop_count = process_state_change(orgAccountObj.name)
        assert(loop_count==2)
        
        
        # nothing else changes
        assert(OwnerPSCmd.objects.count()==0)
        assert(OrgNumNode.objects.count()==3)
        assert(orgAccountObj.num_owner_ps_cmd==0)
        
        assert(orgAccountObj.num_ps_cmd==1)
        assert(orgAccountObj.num_ps_cmd_successful==1)
        assert(orgAccountObj.desired_num_nodes==4)
        # web login
        assert(client.login(username=OWNER_USER,password=OWNER_PASSWORD))

        verify_owner_ps_Refresh_cmd(client=client,
                                    orgAccountObj=orgAccountObj,
                                    new_time=datetime.now(timezone.utc),
                                    delay_state_processing=True,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

        # verify setup occurred
        assert(clusterObj.provision_env_ready)
        assert(orgAccountObj.provisioning_suspended==False)

        assert(OwnerPSCmd.objects.count()==1) 
        assert(OrgNumNode.objects.count()==3)
        assert(orgAccountObj.num_owner_ps_cmd==0) #not until process_state_change
        
        assert(orgAccountObj.num_ps_cmd==1)
        assert(orgAccountObj.num_ps_cmd_successful==1)
        assert(orgAccountObj.desired_num_nodes==4)
        assert(loop_count==2)

        task_idle, loop_count = process_state_change(orgAccountObj.name)
        assert(loop_count==3)
        clusterObj.refresh_from_db() # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        assert(OwnerPSCmd.objects.count()==0) # processed and cleared
        assert(OrgNumNode.objects.count()==3)
        assert(orgAccountObj.num_owner_ps_cmd==1)
        
        assert(orgAccountObj.num_ps_cmd==2) # processed
        assert(orgAccountObj.num_ps_cmd_successful==2)
        assert(orgAccountObj.desired_num_nodes==4)
       
        

        # expire first one (3,15)
        # table is:
        #  3,15 <-- expire this one
        #  4,16
        #  2,17 
        verify_onn_expires(orgAccountObj = orgAccountObj,
                            new_time=(fake_time_now.replace(microsecond=0) +timedelta(minutes=15,seconds=1)), # force expire
                            expected_change_ps_cmd=0, # 4 is highest and was already added to table and was highest and processed
                            expected_change_OrgNumNode=-1, # removes the expired one
                            expected_desired_num_nodes=4,
                            delay_state_processing=False, # process the state change 
                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                            mock_schedule_process_state_change=mock_schedule_process_state_change)

        # simulate the deploy
        clusterObj.is_deployed = True
        clusterObj.save()

        # expire next one (4,16)
        # table is:
        #  3,15 **expired already
        #  4,16 <-- expire this one
        #  2,17 
        verify_onn_expires(orgAccountObj=orgAccountObj,
                            new_time=(fake_time_now+timedelta(minutes=16,seconds=1)),
                            expected_change_ps_cmd=1, # should do an update to get 2  
                            expected_change_OrgNumNode=-1,
                            expected_desired_num_nodes=2,
                            delay_state_processing=False,
                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                            mock_schedule_process_state_change=mock_schedule_process_state_change)

        # these two set like this mean we call destroy when table is empty
        assert(orgAccountObj.destroy_when_no_nodes)
        assert(orgAccountObj.min_node_cap==0)
        assert clusterObj.is_deployed
        assert OrgNumNode.objects.count()==1
        # expire next one (4,16)
        # table is:
        #  3,15 **expired already
        #  4,16 **expired already
        #  2,17 <-- expire this one
        verify_onn_expires(orgAccountObj=orgAccountObj,
                            new_time=(fake_time_now+timedelta(minutes=17,seconds=1)),
                            expected_change_ps_cmd=1, # destroy 
                            expected_change_OrgNumNode=-1,
                            expected_desired_num_nodes=0,
                            delay_state_processing=False,
                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                            mock_schedule_process_state_change=mock_schedule_process_state_change)


#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("provisioning_disabled, expected_result", [
    (True, False),
    (False, True)
])
def test_enqueue_process_state_change(provisioning_disabled, expected_result):
    with patch("users.tasks.get_PROVISIONING_DISABLED", return_value=provisioning_disabled), \
         patch("users.tasks.django_rq") as mock_django_rq, \
         patch("users.tasks.cache") as mock_cache, \
         patch("users.tasks.Job") as mock_Job:

        # Act
        result = enqueue_process_state_change("test_name")

        # Assert
        assert result == expected_result