import pytest
import logging
import sys
import os
import pathlib
import uuid
import json
import requests
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from django.urls import reverse,resolve
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,initialize_test_org,call_process_state_change,verify_org_configure,verify_schedule_process_state_change
from users.tests.utilities_for_unit_tests import TEST_EMAIL,TEST_ORG_NAME,TEST_PASSWORD,TEST_USER,DEV_TEST_EMAIL,DEV_TEST_PASSWORD,DEV_TEST_USER,OWNER_USER,OWNER_PASSWORD,OWNER_EMAIL,the_TEST_USER,the_OWNER_USER,the_DEV_TEST_USER
import subprocess
from users.global_constants import ONN_MIN_TTL, ONN_MAX_TTL

import time_machine

from users.models import Membership,Cluster,OrgAccount,OrgNumNode,OwnerPSCmd,PsCmdResult
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
#logger = logging.getLogger(__name__)
logger = logging.getLogger('django')
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
@pytest.mark.ps_server_stubbed
def test_simple_cfg_org(caplog,client,initialize_test_environ):
    '''
        This procedure will test the cfg org
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

    json_data = json.loads(response.content)
    logger.info(f"org-token-obtain-pair rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   

    headers = {
        'Authorization': f"Bearer {json_data['access']}",
        'Accept': 'application/json'  # Specify JSON response
    }
    orgAccountObj = get_test_org()
    url = reverse('org-cfg',args=[orgAccountObj.name,0,orgAccountObj.admin_max_node_cap])
    response = client.put(url,headers=headers)
    logger.info(f"org-cfg status:{response.status_code} response:{response.json()}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)   
    assert(orgAccountObj.min_node_cap == 0)
    assert(orgAccountObj.max_node_cap == orgAccountObj.admin_max_node_cap)

    url = reverse('org-cfg',args=[orgAccountObj.name,1,orgAccountObj.admin_max_node_cap-1])
    response = client.put(url,headers=headers)
    logger.info(f"org-cfg status:{response.status_code} response:{response.json()}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)   
    assert(orgAccountObj.min_node_cap == 1)
    assert(orgAccountObj.max_node_cap == orgAccountObj.admin_max_node_cap-1)



#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_config_org(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the config min-max nodes api
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

    headers = {
        'Authorization': f"Bearer {json_data['access']}",
        'Accept': 'application/json'  # Specify JSON response
    }
    # negative test POST
    url = reverse('org-cfg',args=[get_test_org().name,0,5])
    response = client.post(url)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    assert (response.status_code == 405)  

    # negative test no Token
    url = reverse('org-cfg',args=[get_test_org().name,0,5])
    response = client.put(url)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    assert (response.status_code == 400)  

    # now test config with valid values
    url = reverse('org-cfg',args=[get_test_org().name,0,5])
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)   
    assert(orgAccountObj.min_node_cap == 0)
    assert(orgAccountObj.max_node_cap == 5)

    # now test config with valid values
    url = reverse('org-cfg',args=[get_test_org().name,0,orgAccountObj.admin_max_node_cap])
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)   
    assert(orgAccountObj.min_node_cap == 0)
    assert(orgAccountObj.max_node_cap == orgAccountObj.admin_max_node_cap)

    # now test config with INVALID: max is 0
    url = reverse('org-cfg',args=[get_test_org().name,0,0])
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    assert (response.status_code == 400)

    # now test config with INVALID: max is max_admin + 1
    url = reverse('org-cfg',args=[get_test_org().name,0,orgAccountObj.max_node_cap+1])
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    assert (response.status_code == 400)

    # now test config with INVALID: min is -1
    name = get_test_org().name
    min_nodes = -1  # Provide an invalid value for min_nodes
    max_nodes = 5
    # Manually construct the URL with an invalid value for min_nodes
    url = f"/org_config/{name}/{min_nodes}/{max_nodes}/"
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 404)

    # now test config with INVALID: max < min
    url = reverse('org-cfg',args=[get_test_org().name,2,1])
    response = client.put(url,headers=headers)
    logger.info(f"status:{response.status_code} response:{response.json()}")
    assert (response.status_code == 400)

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_membership_status(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the membership status api
    '''
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)

    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    json_data = json.loads(response.content)

    headers = {
        'Authorization': f"Bearer {json_data['access']}",
        'Accept': 'application/json'  # Specify JSON response
    }

    url = reverse('get-membership-status',args=[get_test_org().name])
    response = client.get(url,headers=headers)
    rsp_body = response.json()
    logger.info(f"status:{response.status_code} response:{rsp_body}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)
    assert(rsp_body['active'] == True)   

    url = reverse('get-membership-status',args=[get_test_org().name+"BadOrgName"])
    response = client.get(url,headers=headers)
    rsp_body = response.json()
    logger.info(f"status:{response.status_code} response:{rsp_body}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 400)
    assert(rsp_body['status'] == 'FAILED')
    assert('Unknown org' in rsp_body['error_msg'])   

    PUBLIC_ORG = 'unit-test-public'
    new_test_org,owner = initialize_test_org(PUBLIC_ORG,org_owner=orgAccountObj.owner,is_public=True,max_allowance=10000,monthly_allowance=100,balance=1000)

 
    # org exists but is NOT the one in the token claim, user NOT a member
    url = reverse('get-membership-status',args=[PUBLIC_ORG])
    response = client.get(url,headers=headers)
    rsp_body = response.json()
    logger.info(f"status:{response.status_code} response:{rsp_body}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 400)
    assert(rsp_body['status'] == 'FAILED')
    emsg = f"Token claim org:{orgAccountObj.name} does not match organization given:{PUBLIC_ORG} "
    assert(emsg in rsp_body['error_msg'])   

#@pytest.mark.dev
@pytest.mark.django_db
#@pytest.mark.ps_server_stubbed
@pytest.mark.ps_disable # will shut down the provisioning system
def test_disable_provisioning_success(caplog,client,mock_email_backend,developer_TEST_USER,initialize_test_environ):
    url = reverse('api-disable-provisioning')
    data={
        "username":DEV_TEST_USER,
        "password":DEV_TEST_PASSWORD, 
        "mfa_code":"123456"
        }
    #json_str = json.dumps(data)
    #logger.info(json_str)
    response = client.put(url,data=data,content_type= 'application/json', HTTP_ACCEPT= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
    else:
        logger.info(f"response:{response}")
    assert response.status_code == 200 # Bingo!

def check_disable_provisioning_rsp(json_data,alternate_port):
    assert json_data['status'] == 'SUCCESS'
    assert json_data['msg'] == 'You have disabled provisioning! Re-Deploy required!'
    assert json_data['alternate_port'] == alternate_port
    return True

#@pytest.mark.dev
@pytest.mark.django_db
#@pytest.mark.ps_server_stubbed
@pytest.mark.ps_disable # will shut down the provisioning system
def test_disable_provisioning_idempotent(caplog,client,mock_email_backend,developer_TEST_USER,initialize_test_environ):
    ps_server_port = os.environ.get('PS_SERVER_PORT')
    ps_server_alternate_port = os.environ.get('PS_SERVER_ALTERNATE_PORT')
    logger.info(f"test_disable_provisioning_idempotent PS_SERVER_PORT:{ps_server_port} PS_SERVER_ALTERNATE_PORT:{ps_server_alternate_port}")
    url = reverse('api-disable-provisioning')
    data={
        "username":DEV_TEST_USER,
        "password":DEV_TEST_PASSWORD, 
        "mfa_code":"123456"
        }
    #json_str = json.dumps(data)
    #logger.info(json_str)
    response = client.put(url,data=data,content_type= 'application/json', HTTP_ACCEPT= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"json_data:{json_data}")
        check_disable_provisioning_rsp(json_data,alternate_port=ps_server_alternate_port)
        assert response.status_code == 200 
    else:
        logger.error(f"response:{response}")
        assert False

    response = client.put(url,data=data,content_type= 'application/json', HTTP_ACCEPT= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
        check_disable_provisioning_rsp(json_data,alternate_port=ps_server_alternate_port) # this toggles back and forth
        assert response.status_code == 200 
    else:
        logger.error(f"response:{response}")
        assert False

    response = client.put(url,data=data,content_type= 'application/json', HTTP_ACCEPT= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
        check_disable_provisioning_rsp(json_data,alternate_port=ps_server_alternate_port)
        assert response.status_code == 200 
    else:
        logger.error(f"response:{response}")
        assert False


#@pytest.mark.dev
@pytest.mark.django_db
#@pytest.mark.ps_server_stubbed
def test_disable_provisioning_failure_NOT_developer(caplog,client,mock_email_backend,developer_TEST_USER,initialize_test_environ):
    url = reverse('api-disable-provisioning')
    logger.info(f"url:{url} OWNER_USER:{OWNER_USER} OWNER_PASSWORD:{OWNER_PASSWORD}  ")
    data = {
        "username": OWNER_USER,
        "password": OWNER_PASSWORD,
        "mfa_code": "123456"  
    }
    json_str = json.dumps(data)
    logger.info(json_str)
    response = client.put(url,json=data,content_type= 'application/json', accept= 'application/json')

    logger.info(f"Response Status Code: {response.status_code}")
    logger.info(f"Response Content: {response.content.decode('utf-8')}")
    logger.info(f"Response Headers: {response.headers}")
    if hasattr(response, 'context'):
        if response.context is not None:
            for context in response.context:
                if isinstance(context, dict):  # Ensure it's a dictionary before calling items()
                    for key, value in context.items():
                        logger.info(f"Context Key: {key}, Value: {value}")


    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
    else:
        logger.info(f"response:{response}")


    assert response.status_code == 400 # User is not developer  
 

#@pytest.mark.dev
@pytest.mark.django_db
#@pytest.mark.ps_server_stubbed
def test_disable_provisioning_failure_WRONG_mfa(caplog,client,mock_email_backend,developer_TEST_USER,initialize_test_environ):
    url = reverse('api-disable-provisioning')
    logger.info(f"url:{url}  DEV_TEST_USER:{DEV_TEST_USER} DEV_TEST_PASSWORD:{DEV_TEST_PASSWORD} DEV_TEST_EMAIL:{DEV_TEST_EMAIL} ")
    data={
        "username":DEV_TEST_USER,
        "password":DEV_TEST_PASSWORD, 
        "mfa_code":"123456_WRONG"
        }
    json_str = json.dumps(data)
    logger.info(json_str)
    response = client.put(url,json=data,content_type= 'application/json', accept= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
    else:
        logger.info(f"response:{response}")
    assert response.status_code == 400 # wrong mfa code 


#@pytest.mark.dev
@pytest.mark.django_db
#@pytest.mark.ps_server_stubbed
def test_disable_provisioning_failure_WRONG_password(caplog,client,mock_email_backend,developer_TEST_USER,initialize_test_environ):
    url = reverse('api-disable-provisioning')
    logger.info(f"url:{url}  DEV_TEST_USER:{DEV_TEST_USER} DEV_TEST_PASSWORD:{DEV_TEST_PASSWORD} DEV_TEST_EMAIL:{DEV_TEST_EMAIL} ")
    data={
        "username":DEV_TEST_USER,
        "password":DEV_TEST_PASSWORD+"wrong", 
        "mfa_code":"123456"
        }
    json_str = json.dumps(data)
    logger.info(json_str)
    response = client.put(url,json=data,content_type= 'application/json', accept= 'application/json')
    logger.info(f"status:{response.status_code}")
    if response.content:
        json_data = json.loads(response.content)
        logger.info(f"rsp:{json_data}")
    else:
        logger.info(f"response:{response}")
    assert response.status_code == 400 # wrong mfa code 

@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_ONN_ttl(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, mock_email_backend,initialize_test_environ):
    '''
        This procedure will test owner grabs token and can queue a ONN
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    
    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    assert (OwnerPSCmd.objects.count()==0)
    assert (OrgNumNode.objects.count()==0)
    json_data = json.loads(response.content)
    logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   

    orgAccountObj.num_owner_ps_cmd=0
    orgAccountObj.num_ps_cmd=0
    orgAccountObj.num_ps_cmd_successful=0
    orgAccountObj.desired_num_nodes=0
    orgAccountObj.min_node_cap=0
    orgAccountObj.max_node_cap=10
    orgAccountObj.save()
    assert orgAccountObj.min_node_cap == 0
    assert orgAccountObj.max_node_cap == 10
    assert orgAccountObj.desired_num_nodes == 0
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True
    assert orgAccountObj.provisioning_suspended == False

    start_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count

    ttl = 15
    min_tm = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).replace(microsecond=0)
    url = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,3,ttl]) # 3 nodes for 15 minutes
    max_tm = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).replace(microsecond=0)
    response = client.post(url,headers={'Authorization': f"Bearer {json_data['access']}"})
    assert (response.status_code == 200) 
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(json_data['msg']!='')   
    assert(json_data['error_msg']=='') 
    logger.info(f"msg:{json_data['msg']}") 
     
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()

    assert orgAccountObj.desired_num_nodes == 3
    # stubbed out ps_server simulates successful update to 3....
    assert clusterObj.cur_nodes == 3

    current_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count    
    call_process_state_change(orgAccountObj,1,start_cnt,current_cnt)
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()

    assert(current_cnt-start_cnt > 0)
    assert (mock_schedule_process_state_change.call_count == current_cnt-start_cnt)
    assert(clusterObj.provision_env_ready)
    assert(orgAccountObj.provisioning_suspended==False)
    assert(orgAccountObj.num_ps_cmd==1) # onn triggered update
    assert(orgAccountObj.num_ps_cmd_successful==1) 

    assert PsCmdResult.objects.count() == 1 # Update 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label

    assert(orgAccountObj.provisioning_suspended==False)
    assert(orgAccountObj.num_ps_cmd==1)
    assert(orgAccountObj.num_ps_cmd_successful==1) 

    verify_schedule_process_state_change(mock_schedule_process_state_change=mock_schedule_process_state_change,
                                         min_tm=min_tm,
                                         max_tm=max_tm, 
                                         orgAccountObj=orgAccountObj,
                                         clusterObj=clusterObj,
                                         expected_change_ps_cmd=1,
                                         expected_desired_num_nodes=0,
                                         expected_change_ps_cmd_when_expired=1,
                                         expected_desired_num_nodes_when_expired=0) # destroy with min=0


##@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_ONN_expires(caplog, client,initialize_test_environ):
    '''
        This procedure will test owner grabs token and can queue a ONN
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    assert orgAccountObj.num_setup_cmd == 0
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd == 0
    
    logger.info(f"orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    # setup necessary form data
    form_data = {
        'is_public': orgAccountObj.version, # don't change
        'version': orgAccountObj.is_public, # don't change
        'min_node_cap': 0,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    time_now = datetime.now(timezone.utc)
    dt = time_now - timedelta(seconds=1)
    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, delay_state_processing=False,new_time=dt) # SetUp - Update (min nodes is 1)

    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    assert (OwnerPSCmd.objects.count()==0)
    assert (OrgNumNode.objects.count()==0)
    json_data = json.loads(response.content)
    logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   

    orgAccountObj.num_owner_ps_cmd=0
    orgAccountObj.num_ps_cmd=0
    orgAccountObj.num_ps_cmd_successful=0
    orgAccountObj.save()
    url = reverse('put-org-num-nodes-ttl',args=[orgAccountObj.name,3,ONN_MIN_TTL])
    
    response = client.put(url,headers={'Authorization': f"Bearer {json_data['access']}"})
    assert (response.status_code == 200) 
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(json_data['msg']!='')   
    assert(json_data['error_msg']=='') 
    logger.info(f"msg:{json_data['msg']}")  
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    assert(clusterObj.provision_env_ready)
    assert(orgAccountObj.provisioning_suspended==False)
    assert(orgAccountObj.num_ps_cmd==1) # onn triggered update
    assert(orgAccountObj.num_ps_cmd_successful==1) 
    assert PsCmdResult.objects.count() == 1 # Update 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
    time_now = datetime.now(timezone.utc)
    # now change past the ttl triggers a call to process_state_change
    # so that the table is processed again and the exipred ONN is removed
    # and a destroy cmd is sent because it is configured to do so
    dt = time_now - timedelta(minutes=ONN_MIN_TTL+1) 
    with time_machine.travel(dt,tick=True):
        fake_now = datetime.now(timezone.utc)
        logger.info(f"fake_now:{fake_now} dt:{dt}")
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
        logger.info(f"[1]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Destroy' in psCmdResultObjs[0].ps_cmd_summary_label
        assert orgAccountObj.num_ps_cmd == 2
        assert psCmdResultObjs.count() == 2
