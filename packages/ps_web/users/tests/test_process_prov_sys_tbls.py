import pytest
import logging
import sys
import os
import pathlib
import uuid
import pytz
import json
import pprint
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,verify_post_org_num_nodes_ttl,the_TEST_USER,the_OWNER_USER,the_DEV_TEST_USER,init_mock_ps_server,create_test_user,verify_api_user_makes_onn_ttl,create_active_membership,initialize_test_org,log_ONN,fake_sync_clusterObj_to_orgAccountObj,call_SetUp,verify_org_configure,dump_cmd_results
from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster,PsCmdResult
from users.forms import OrgAccountForm
from users.tasks import need_destroy_for_changed_version_or_is_public,get_or_create_OrgNumNodes,sort_ONN_by_nn_exp,format_onn,sum_of_highest_nodes_for_each_user,process_state_change
from users.views import add_org_cluster_orgcost
from time import sleep
from django.contrib import messages
from django.contrib.auth import get_user_model
from allauth.account.decorators import verified_email_required
from django.contrib.auth.models import User
from django.urls import reverse
from oauth2_provider.models import Application


# Import the fixtures
from users.tests.utilities_for_unit_tests import TEST_USER,TEST_PASSWORD,DEV_TEST_USER,DEV_TEST_PASSWORD,TEST_ORG_NAME

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
logger = logging.getLogger('unit_testing')
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


@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_form_create(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'initialize_test_environ' fixture 
        which creates a new organization and initializes the memberships and queue
    '''
    assert(get_test_org().name == TEST_ORG_NAME)
    assert(get_test_org().owner.username == OWNER_USER)

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_owner_refreshes(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test a privileged user can queue a refresh cmd
    '''
    caplog.set_level(logging.DEBUG)
    

    logger.info(f"will now add ps cmds by calling deploy url")
    time_now = datetime.now(timezone.utc)
    caplog.set_level(logging.DEBUG)

    url = reverse('org-refresh-cluster',args=[get_test_org().id,])

    response = client.post(url)
    logger.info(f"status:{response.status_code}")
    assert ((response.status_code == 302) or (response.status_code == 200)) # 302 is redirect to login
    assert (OwnerPSCmd.objects.count()==0)
    
    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    response = client.post(url)
    # Assert the response status code and content
    assert ((response.status_code == 302) or (response.status_code == 200)) # 302 is redirect to login
    assert (OwnerPSCmd.objects.count()==1)
    client.logout()

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_redirect_login(caplog,client,mock_email_backend,create_TEST_USER,initialize_test_environ):
    '''
        This procedure will test redirect to login if not authorized yet
    '''
    caplog.set_level(logging.DEBUG)
    test_org=get_test_org()
    url = reverse('org-refresh-cluster',args=[test_org.id,])
    logger.info(f"url is using id for org:{test_org.name} owner:{test_org.owner}")
    response = client.post(url)
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 302)   
    assert (OwnerPSCmd.objects.count()==0)
    client.logout()

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_unverified_user(caplog,client,mock_email_backend,create_TEST_USER,initialize_test_environ):
    '''
        This procedure will test the response if the user did not verify email before trying to deploy
    '''
    caplog.set_level(logging.DEBUG)
    

    logger.info(f"will now add ps cmds by calling deploy url")
    time_now = datetime.now(timezone.utc)
    caplog.set_level(logging.DEBUG)
    test_org=get_test_org()
    url = reverse('org-refresh-cluster',args=[test_org.id,])
    logger.info(f"url is using id for org:{test_org.name} owner:{test_org.owner}")
    assert (OwnerPSCmd.objects.count()==0)

    # Log in the regular test user that has validated email (using fixture passed in above)
    logger.info(f"logging in with {TEST_USER}")
    assert(client.login(username=TEST_USER, password=TEST_PASSWORD))
    
    response = client.post(url)
    logger.info(f"response.wsgi_request.user.username:{response.wsgi_request.user.username} TEST_USER:{TEST_USER}")
    assert response.wsgi_request.user.username == TEST_USER
    # Assert the response status code and content
    assert response.status_code == 200 # this is because TEST_USER is has unverified email
    #logger.info(f"dir(response):{dir(response)}")
    #logger.info(f"reason_phrase:{response.reason_phrase}")
    assert(response.reason_phrase=='OK')
    #logger.info(f"content:{response.content}")
    # this verifies that allauth sent the web page that tells the user to verify their email address
    assert(b'Verify Your E-mail Address' in response.content)
    assert(b'This part of the site requires us to verify that' in response.content)
    assert(b'you are who you claim to be. For this purpose, we require that you' in response.content)

    client.logout()

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_no_privilege(caplog,client,mock_email_backend,verified_TEST_USER,initialize_test_environ):
    '''
        This procedure will test the response if the user is not a privileged user
    '''
    caplog.set_level(logging.DEBUG)
    

    logger.info(f"will now add ps cmds by calling deploy url")
    time_now = datetime.now(timezone.utc)
    caplog.set_level(logging.DEBUG)
    test_org=get_test_org()
    url = reverse('org-refresh-cluster',args=[test_org.id,])
    logger.info(f"url is using id for org:{test_org.name} owner:{test_org.owner}")
    assert (OwnerPSCmd.objects.count()==0)

    # Log in the regular test user that has validated email (using fixture passed in above)
    logger.info(f"logging in with {TEST_USER} (but this time the email is verified in test fixture)")
    assert(client.login(username=TEST_USER, password=TEST_PASSWORD))
    
    response = client.post(url)
    logger.info(f"response.wsgi_request.user.username:{response.wsgi_request.user.username} TEST_USER:{TEST_USER}")
    assert response.wsgi_request.user.username == TEST_USER
    # Assert the response status code and content
    assert response.status_code == 401 # this is because TEST_USER is a regular user and cannot deploy
    assert (OwnerPSCmd.objects.count()==0)
    client.logout()


@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_token(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test owner grabs token and can queue a ONN
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    assert (OwnerPSCmd.objects.count()==0)
    assert (OrgNumNode.objects.count()==0)
    # Decode the JSON response
    json_data = json.loads(response.content)    
    #logger.info(f"rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   

#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_get_or_create_OrgNumNodes(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test get_or_create_OrgNumNodes
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 2
    orgAccountObj.max_node_cap = 7
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    user = random_test_user()
    expire_tm = datetime.now(timezone.utc)+timedelta(hours=1)
    assert (OrgNumNode.objects.count()==0)
    onn1,redundant,msg = get_or_create_OrgNumNodes(orgAccountObj,user,3,expire_tm)
    assert(not redundant)
    assert(onn1)
    assert (OrgNumNode.objects.count()==1)
    # test add redundant
    onn2,redundant,msg = get_or_create_OrgNumNodes(orgAccountObj,user,3,expire_tm)
    assert(redundant)
    assert(onn2)
    assert(onn1==onn2)
    assert (OrgNumNode.objects.count()==1)


#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_ONN_redundant(caplog,client,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out,mock_email_backend,mock_schedule_process_state_change, initialize_test_environ):
    '''
        This procedure will test logic for redundant ONN requests
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    start_num_ps_cmd = orgAccountObj.num_ps_cmd
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
    access_token = json_data['access']   
    url = reverse('put-org-num-nodes',args=[orgAccountObj.name,3])
    
    response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db()
    assert(Cluster.objects.count()==1)
    assert(OrgNumNode.objects.count()==1)
    assert(OwnerPSCmd.objects.count()==0)
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(json_data['msg']!='')   
    assert(json_data['error_msg']=='') 
    logger.info(f"msg:{json_data['msg']}")  
    

    url_ttl = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,3,15])
    response = client.post(url_ttl,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db()
    assert(OrgNumNode.objects.count()==2)
    assert(OwnerPSCmd.objects.count()==0)

    # Test duplicate request does not queue another onn
    url = reverse('put-org-num-nodes',args=[orgAccountObj.name,3])
    response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db()
    assert(OrgNumNode.objects.count()==2) # Same as above because it's redundant
    json_data = json.loads(response.content)
    assert(json_data['status']=='REDUNDANT')   
    assert(OwnerPSCmd.objects.count()==0)

    # Test a new request with duplicate time does not create new clocked item
    url = reverse('put-org-num-nodes',args=[orgAccountObj.name,1])
    response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db()
    assert(OrgNumNode.objects.count()==3) 
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(OwnerPSCmd.objects.count()==0)

    task_idle, loop_count = process_state_change(orgAccountObj.name)
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    assert(orgAccountObj.num_ps_cmd==start_num_ps_cmd+1) # only one
     # only process one of the entries
     # only process one here, wait for expire
    
#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_ONN_remove(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the remove onn api
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
    access_token = json_data['access']   
    url = reverse('put-org-num-nodes',args=[orgAccountObj.name,3])
    
    response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db() # The client.put above updated the DB so we need this
    assert(Cluster.objects.count()==1)
    assert(OrgNumNode.objects.count()==1)
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(json_data['msg']!='')   
    assert(json_data['error_msg']=='') 
    logger.info(f"msg:{json_data['msg']}")  

    url_ttl = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,3,15])
    response = client.post(url_ttl,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    assert(OrgNumNode.objects.count()==2)
    assert(OwnerPSCmd.objects.count()==0)

    url_ttl = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,4,15])
    response = client.post(url_ttl,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    assert(OrgNumNode.objects.count()==3)
    assert(OwnerPSCmd.objects.count()==0)


    url_remove = reverse('remove-user-org-num-nodes-reqs',args=[orgAccountObj.name])
    response = client.put(url_remove,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    assert(OrgNumNode.objects.count()==0)
    assert(OwnerPSCmd.objects.count()==0)

#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_orgNumNodes(setup_logging,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the get org num nodes api/view
    '''
    logger = setup_logging
    init_mock_ps_server(logger)
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.save()
    url = reverse('org-token-obtain-pair')

    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    json_data = json.loads(response.content)
    access_token = json_data['access']   
    url = reverse('get-num-nodes',args=[orgAccountObj.name])
    response = client.get(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    assert(clusterObj.is_deployed)
    json_data = json.loads(response.content)
    logger.info(f"{json_data}")
    assert(json_data['status']=='SUCCESS')
    assert(json_data['min_nodes']== 0)
    assert(json_data['max_nodes']== 10)
    assert(json_data['current_nodes']== 0)
    #TBD how do we mock this?
    # assert(json_data['version']== 'latest')

    clusterObj.is_deployed = False
    clusterObj.save()

    response = client.get(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db() # The client.put above updated the DB so we need this
    assert(not clusterObj.is_deployed)
    json_data = json.loads(response.content)
    logger.info(f"{json_data}")
    assert(json_data['status']=='SUCCESS')
    assert(json_data['min_nodes']== 0)
    assert(json_data['max_nodes']== 10)
    assert(json_data['current_nodes']== 0)


#@pytest.mark.dev
@pytest.mark.django_db 
@pytest.mark.ps_server_stubbed
def test_org_ONN_redundant_2(setup_logging,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test logic for deploy using ONN requests
    '''
    logger = setup_logging
    init_mock_ps_server(logger)
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
    access_token = json_data['access']   
    url = reverse('put-org-num-nodes',args=[orgAccountObj.name,3])
    
    response = client.put(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db() # The client.put above updated the DB so we need this
    assert(Cluster.objects.count()==1)
    assert(OrgNumNode.objects.count()==1)
    assert(OwnerPSCmd.objects.count()==0)
    json_data = json.loads(response.content)
    assert(json_data['status']=='QUEUED')   
    assert(json_data['msg']!='')   
    assert(json_data['error_msg']=='') 
    logger.info(f"msg:{json_data['msg']}")  
    
    


    url_ttl = reverse('post-org-num-nodes-ttl',args=[orgAccountObj.name,3,15])
    response = client.post(url_ttl,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    clusterObj.refresh_from_db() # The client.put above updated the DB so we need this
    orgAccountObj.refresh_from_db() # The client.put above updated the DB so we need this
    assert(OrgNumNode.objects.count()==2)
    assert(OwnerPSCmd.objects.count()==0)


    orgAccountObj.num_ps_cmd=0
    orgAccountObj.num_ps_cmd_successful=0
    orgAccountObj.save()
    task_idle, loop_count = process_state_change(orgAccountObj.name)
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    assert(orgAccountObj.num_ps_cmd==1) # onn triggered a deploy
    assert(orgAccountObj.num_ps_cmd_successful==1) # onn triggered a deploy
     # only process one of the entries
     # only process one here, wait for expire

    url = reverse('get-num-nodes',args=[orgAccountObj.name])
    response = client.get(url,headers={'Authorization': f"Bearer {access_token}"})
    assert (response.status_code == 200) 
    assert(clusterObj.is_deployed)
    json_data = json.loads(response.content)
    logger.info(f"{json_data}")
    assert(json_data['status']=='SUCCESS')
    assert(json_data['min_nodes']== 0)
    assert(json_data['max_nodes']== 10)
    assert(json_data['current_nodes']== 3)

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_sort_ONN_by_nn_exp(caplog,client,mock_email_backend,initialize_test_environ,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out):
    '''
        This procedure will test logic the routine sort_ONN_by_nn_exp
    '''
    caplog.set_level(logging.DEBUG)
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    
    response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    assert(response.status_code == 200)   
    json_data = json.loads(response.content)
    access_token = json_data['access']   
    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,3,17],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=1, 
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,4,16],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=1,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,5,15],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=1,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    
    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,5,25],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=0,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,5,20],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=0,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,5,21],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=0,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    loop_count,response = verify_post_org_num_nodes_ttl(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.name,5,18],
                                                        access_token=access_token,
                                                        expected_change_ps_cmd=0,
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    prev = None
    qs = sort_ONN_by_nn_exp(orgAccountObj)
    for onn in qs:
        logger.info(format_onn(onn))
        if onn.expiration is not None:
            assert(onn.expiration > datetime.now(timezone.utc))
        if prev:
            assert(onn.desired_num_nodes <= prev.desired_num_nodes)
            if onn.desired_num_nodes == prev.desired_num_nodes:
                if onn.expiration is not None:
                    assert(onn.expiration >= prev.expiration)
        prev = onn 


## TBD make a system test for this
#
# def just_ONE_CASE(client,orgAccountObj, access_token, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, is_deployed, is_public_changes, version_changes, new_highest_onn_id):
#     logger.info(f"is_deployed: {is_deployed}, is_public_changes: {is_public_changes}, version_changes: {version_changes}, new_highest_onn_id: {new_highest_onn_id}")
#     orgAccountObj.desired_num_nodes=1
#     orgAccountObj.is_public = True
#     orgAccountObj.version = 'v2'

#     expire_date = datetime.now(timezone.utc)+timedelta(minutes=16) 
#     onn = OrgNumNode.objects.create(user=the_TEST_USER(),org=orgAccountObj, desired_num_nodes=orgAccountObj.desired_num_nodes,expiration=expire_date)
#     logger.info(f"created BASE onn:{onn} OrgNumNode.objects.count():{OrgNumNode.objects.count()}")   

#     sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
#     orgAccountObj.desired_num_nodes = sum_of_all_users_dnn # quiencent state
#     orgAccountObj.save()
#     call_SetUp(orgAccountObj=orgAccountObj,is_deployed=is_deployed)

#     if new_highest_onn_id:
#         # this simulates a new call to the api
#         onnTop = sort_ONN_by_nn_exp(orgAccountObj).first()
#         new_desired_num_nodes = onnTop.desired_num_nodes+1 # new highest
#         loop_count,response = verify_post_org_num_nodes_ttl(client=client,
#                                                             orgAccountObj=orgAccountObj,
#                                                             url_args=[orgAccountObj.name,new_desired_num_nodes,18],
#                                                             access_token=access_token,
#                                                             expected_change_ps_cmd=1,
#                                                             expected_status='QUEUED',
#                                                             mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
#                                                             mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)


#     # mimic an org configure
#     new_version = orgAccountObj.version+'a' if version_changes else orgAccountObj.version
#     new_is_public = not orgAccountObj.is_public if is_public_changes else orgAccountObj.is_public
#     # setup necessary form data
#     form_data = {
#         'is_public': new_is_public,
#         'version': new_version, # First time we use the current version
#         'min_node_cap': orgAccountObj.min_node_cap,
#         'max_node_cap': orgAccountObj.max_node_cap,
#         'allow_deploy_by_token': True,
#         'destroy_when_no_nodes': True,
#         'provisioning_suspended': False,
#     }
#     expected_change_ps_cmd = 0
#     expected_change_setup_cmd = 0
#     if version_changes or is_public_changes:
#         expected_change_ps_cmd = 1
#         expected_change_setup_cmd = 1
#     s_results = PsCmdResult.objects.count()
#     assert verify_org_configure(client=client, 
#                                 orgAccountObj=orgAccountObj, 
#                                 data=form_data,
#                                 expected_change_ps_cmd=expected_change_ps_cmd,
#                                 expected_change_setup_cmd=expected_change_setup_cmd, 
#                                 mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, 
#                                 mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)
    
#     assert PsCmdResult.objects.count() == s_results + expected_change_ps_cmd # SetUp + 
#     dump_cmd_results(orgAccountObj)
#     if expected_change_ps_cmd > 0:
#         psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
#         logger.info(f"[{s_results}]:{psCmdResultObjs[s_results].ps_cmd_summary_label}")
#         assert 'Destroy' in psCmdResultObjs[s_results].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)

#     # if not is_deployed:
#     #     assert not needed_to_destroy
#     # else:
#     #     logger.info(f" ** is_deployed: {is_deployed}, is_public_changes: {is_public_changes}, version_changes: {version_changes}, new_highest_onn_id: {new_highest_onn_id}")
#     #     if (is_public_changes or version_changes) and new_highest_onn_id:
#     #         clusterObj = Cluster.objects.get(org=orgAccountObj)
#     #         logger.info(f" ** cluster cur_version:{clusterObj.cur_version} cur_is_public:{clusterObj.is_public} is_deployed:{clusterObj.is_deployed}")
#     #         logger.info(f" ** cluster prov_env_version:{orgAccountObj.version} prov_env_is_public:{orgAccountObj.is_public}")
#     #         logger.info(f" ** cnnro_ids:{cnnro_ids} not same as clusterObj.cnnro_ids:{clusterObj.cnnro_ids} ?")
#     #         assert needed_to_destroy
#     #     else:
#     #         assert not needed_to_destroy


# @pytest.mark.dev
# @pytest.mark.django_db
# @pytest.mark.ps_server_stubbed
# def  test_need_destroy_for_changed_version_or_is_public_ALL_CASES(caplog,create_TEST_USER,client,mock_email_backend,initialize_test_environ, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change):
#     '''
#         This procedure will test logic for forced Destroy if all combinations of these are met
#     Changes to:
#     | is_deployed | is_public | version |  new_highest_onn_id  | Need to destroy?
#     |-------------|-----------|---------|--------------|
#     | 0           | 0         | 0       | 0            |
#     | 0           | 0         | 0       | 1            |
#     | 0           | 0         | 1       | 0            |
#     | 0           | 0         | 1       | 1            |
#     | 0           | 1         | 0       | 0            |
#     | 0           | 1         | 0       | 1            |
#     | 0           | 1         | 1       | 0            |
#     | 0           | 1         | 1       | 1            |
#     | 1           | 0         | 0       | 0            |
#     | 1           | 0         | 0       | 1            |
#     | 1           | 0         | 1       | 0            |
#     | 1           | 0         | 1       | 1            | YES
#     | 1           | 1         | 0       | 0            |
#     | 1           | 1         | 0       | 1            | YES
#     | 1           | 1         | 1       | 0            |
#     | 1           | 1         | 1       | 1            | YES

#     '''
#     orgAccountObj = get_test_org()                        
#     response = client.post(reverse('org-token-obtain-pair'),data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
#     assert(response.status_code == 200)   
#     json_data = json.loads(response.content)
#     access_token = json_data['access']   

#     variables = [False, True]  # Possible values for the boolean variables
#     for is_deployed in variables:
#         for is_public_changes in variables:
#             for version_changes in variables:
#                 for new_highest_onn_id in variables:
#                     just_ONE_CASE(  orgAccountObj=orgAccountObj,
#                                     client=client,
#                                     access_token= access_token,
#                                     mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
#                                     mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
#                                     is_deployed=is_deployed, 
#                                     is_public_changes=is_public_changes,
#                                     version_changes=version_changes, 
#                                     new_highest_onn_id=new_highest_onn_id)

def verify_new_entries_in_ONN(orgAccountObj,client,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out):

    # now verify different users can make different requests
    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_OWNER_USER(),
                                    password=OWNER_PASSWORD,
                                    desired_num_nodes=2,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    m = create_active_membership(orgAccountObj,the_DEV_TEST_USER())
    m.refresh_from_db()
    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_DEV_TEST_USER(),
                                    password=DEV_TEST_PASSWORD,
                                    desired_num_nodes=3,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    
    rtu = random_test_user()
    m = create_active_membership(orgAccountObj,rtu)
    m.refresh_from_db()
    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=rtu,
                                    password=TEST_PASSWORD,
                                    desired_num_nodes=1,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==6)
    assert(len(cnnro_ids)==3)
    freeze_time = datetime.now(timezone.utc)
    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_DEV_TEST_USER(),
                                    password=DEV_TEST_PASSWORD,
                                    desired_num_nodes=2, # not highest
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=0,
                                    expected_status='QUEUED',
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)  # no change

    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==6) # still 6
    assert(len(cnnro_ids)==3)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_DEV_TEST_USER(),
                                    password=DEV_TEST_PASSWORD,
                                    desired_num_nodes=2, # same as before
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=0,
                                    expected_status='QUEUED',
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # we guarentee unique time inside this routine

    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==6) # still 6
    assert(len(cnnro_ids)==3)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_OWNER_USER(),
                                    password=OWNER_PASSWORD,
                                    desired_num_nodes=1,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=0,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==6) # still 6
    assert(len(cnnro_ids)==3)

    assert verify_api_user_makes_onn_ttl(client=client,
                                        orgAccountObj=orgAccountObj,
                                        user=rtu,
                                        password=TEST_PASSWORD,
                                        desired_num_nodes=1,
                                        ttl_minutes=15,
                                        expected_change_ps_cmd=0,
                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==6) # still 6
    log_ONN()

    uuid_objects = [uuid.UUID(uuid_str) for uuid_str in cnnro_ids]
    for node in OrgNumNode.objects.filter(id__in=uuid_objects):
        logger.info(f"cnnro_ids - {node.user.username} {node.desired_num_nodes} {node.expiration}")

    assert(len(uuid_objects)==4)
    assert(len(cnnro_ids)==4)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=rtu,
                                    password=TEST_PASSWORD,
                                    desired_num_nodes=2,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==7)
    assert(len(cnnro_ids)==3)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_OWNER_USER(),
                                    password=OWNER_PASSWORD,
                                    desired_num_nodes=3,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==8)
    assert(len(cnnro_ids)==3)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_DEV_TEST_USER(),
                                    password=DEV_TEST_PASSWORD,
                                    desired_num_nodes=3,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=0,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    log_ONN()
    uuid_objects = [uuid.UUID(uuid_str) for uuid_str in cnnro_ids]
    for node in OrgNumNode.objects.filter(id__in=uuid_objects):
        logger.info(f"cnnro_ids - {node.user.username} {node.desired_num_nodes} {node.expiration}")

    assert(sum_of_all_users_dnn==8)
    assert(len(cnnro_ids)==4)

    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_DEV_TEST_USER(),
                                    password=DEV_TEST_PASSWORD,
                                    desired_num_nodes=4,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)

    log_ONN()

    uuid_objects = [uuid.UUID(uuid_str) for uuid_str in cnnro_ids]
    for node in OrgNumNode.objects.filter(id__in=uuid_objects):
        logger.info(f"cnnro_ids - {node.user.username} {node.desired_num_nodes} {node.expiration}")

    assert(sum_of_all_users_dnn==9)
    assert(len(cnnro_ids)==3)
    return True


def verify_sum_of_highest_nodes_for_each_user_default_test_org(orgAccountObj,client,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out):

    #   First configure the default test org
    url = reverse('org-token-obtain-pair')
    response = client.post(url,data={'username':OWNER_USER,'password':OWNER_PASSWORD, 'org_name':orgAccountObj.name})
    logger.info(f"status:{response.status_code}")
    assert (response.status_code == 200)   
    json_data = json.loads(response.content)
    logger.info(f"org-token-obtain-pair rsp:{json_data}")
    assert(json_data['access_lifetime']=='3600.0')   
    assert(json_data['refresh_lifetime']=='86400.0')   

    headers = {
        'Authorization': f"Bearer {json_data['access']}",
        'Accept': 'application/json'  # Specify JSON response
    }

    url = reverse('org-cfg',args=[orgAccountObj.name,0,orgAccountObj.admin_max_node_cap])
    response = client.put(url,headers=headers)
    logger.info(f"org-cfg status:{response.status_code} response:{response.json()}")
    orgAccountObj.refresh_from_db()
    assert(response.status_code == 200)   
    assert(orgAccountObj.min_node_cap == 0)
    assert(orgAccountObj.max_node_cap == orgAccountObj.admin_max_node_cap)

    assert(verify_new_entries_in_ONN(orgAccountObj=orgAccountObj,client=client, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out))
    return True


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_sum_of_highest_nodes_for_each_user(caplog,client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, mock_email_backend, initialize_test_environ, developer_TEST_USER):
    '''
        This procedure will test logic for sum_of_highest_nodes_for_each_user for two different orgs
    '''

    assert verify_sum_of_highest_nodes_for_each_user_default_test_org(orgAccountObj=get_test_org(),client=client,mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    # create a new org and initialize like init_test_environ and then mix it up 
    form = OrgAccountForm(data={
                        'name': 'test_create',
                        'owner': the_OWNER_USER(), # use same as sliderule org
                        'point_of_contact_name': 'test point of contact here',
                        'email': OWNER_EMAIL, 
                        'max_allowance':5000,
                        'monthly_allowance':1000,
                        'balance':500,
                        'admin_max_node_cap':10})
    valid = form.is_valid() 
    logger.info(f"form_errors:{form.errors.as_data()}")
    assert(valid)
    for app in Application.objects.all():
        logger.info(f"name:{app.name} uris:{app.redirect_uris}")      
    assert Application.objects.count() == 1 
    orgAccountObj,msg,emsg = add_org_cluster_orgcost(form)
    logger.info(f"msg:{msg} emsg:{emsg} ")
    assert(emsg=='')
    assert('Owner TestUser (ownertestuser) now owns new org/cluster:test_create' in msg)
    orgAccountObj.max_node_cap = 18
    assert(call_SetUp(orgAccountObj))
    assert(fake_sync_clusterObj_to_orgAccountObj(orgAccountObj))
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    logger.info(f"org:{orgAccountObj.name} provision_env_ready:{clusterObj.provision_env_ready} clusterObj.cur_version:{clusterObj.cur_version} orgAccountObj.version:{orgAccountObj.version} ")       
    assert clusterObj.cur_version == orgAccountObj.version
    log_ONN()
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==0) # for new org
    
    assert(verify_new_entries_in_ONN(orgAccountObj=orgAccountObj,client=client, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out))
    onn = log_ONN()
    assert len(onn) == 22
    assert onn[0].desired_num_nodes == 4
    assert onn[5].desired_num_nodes == 3
    assert onn[8].desired_num_nodes == 2
    assert onn[11].desired_num_nodes == 4
    assert onn[16].desired_num_nodes == 3
    assert onn[19].desired_num_nodes == 2
    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert (sum_of_all_users_dnn == 9) # for test_create org

    # now test out of bounds requests, and see that it is clamped

    # now verify different users can make different requests
    LARGE_REQ = orgAccountObj.max_node_cap+5
    assert verify_api_user_makes_onn_ttl( client=client,
                                    orgAccountObj=orgAccountObj,
                                    user=the_OWNER_USER(),
                                    password=OWNER_PASSWORD,
                                    desired_num_nodes=LARGE_REQ,
                                    ttl_minutes=15,
                                    expected_change_ps_cmd=1,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    sum_of_all_users_dnn,cnnro_ids = sum_of_highest_nodes_for_each_user(orgAccountObj)
    assert(sum_of_all_users_dnn==orgAccountObj.max_node_cap) # clamped

    onn = log_ONN()
    assert len(onn) == 23
    assert onn[0].desired_num_nodes == 4
    assert onn[5].desired_num_nodes == LARGE_REQ
    assert onn[9].desired_num_nodes == 2
    assert onn[12].desired_num_nodes == 4
    assert onn[17].desired_num_nodes == 3
    assert onn[20].desired_num_nodes == 2
