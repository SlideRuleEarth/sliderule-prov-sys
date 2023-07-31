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
from django.urls import reverse
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,process_onn_api,the_TEST_USER,init_mock_ps_server
from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster,PsCmdResult
from users.forms import OrgAccountForm
from users.tasks import loop_iter,need_destroy_for_changed_version_or_is_public,get_or_create_OrgNumNodes,sort_ONN_by_nn_exp,format_onn
from time import sleep
from django.contrib import messages
from django.contrib.auth import get_user_model
from allauth.account.decorators import verified_email_required

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
def test_org_ONN_redundant(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test logic for redundant ONN requests
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

    loop_count=0
    task_idle, loop_count = loop_iter(orgAccountObj,loop_count)
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    assert(loop_count==1)
    assert(orgAccountObj.num_ps_cmd==1)
    assert(orgAccountObj.num_onn==1) # only process one of the entries
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
def test_orgNumNodes(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test the get org num nodes api/view
    '''
    caplog.set_level(logging.DEBUG)
    init_mock_ps_server()
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
    url = reverse('get-org-num-nodes',args=[orgAccountObj.name])
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
def test_org_ONN_redundant_2(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test logic for deploy using ONN requests
    '''
    caplog.set_level(logging.DEBUG)
    init_mock_ps_server()
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


    loop_count=0
    orgAccountObj.num_ps_cmd=0
    orgAccountObj.num_ps_cmd_successful=0
    orgAccountObj.save()
    num_owner_ps_cmd=0
    num_onn=0
    task_idle, loop_count = loop_iter(orgAccountObj,loop_count)
    clusterObj.refresh_from_db()
    orgAccountObj.refresh_from_db()
    assert(loop_count==1)
    assert(orgAccountObj.num_ps_cmd==1) # onn triggered a deploy
    assert(orgAccountObj.num_ps_cmd_successful==1) # onn triggered a deploy
    assert(orgAccountObj.num_onn==1) # only process one of the entries
     # only process one here, wait for expire

    url = reverse('get-org-num-nodes',args=[orgAccountObj.name])
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
def test_sort_ONN_by_nn_exp(caplog,client,mock_email_backend,initialize_test_environ):
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
    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,3,17],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,4,16],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,5,15],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')
    
    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,5,25],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,5,20],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,5,21],
                                access_token=access_token,
                                data=None,
                                loop_count=0,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

    loop_count = process_onn_api(client,
                                orgAccountObj,
                                datetime.now(timezone.utc),
                                view_name='post-org-num-nodes-ttl',
                                url_args=[orgAccountObj.name,5,18],
                                access_token=access_token,
                                loop_count=0,
                                data=None,
                                num_iters=0,
                                expected_change_ps_cmd=0,
                                expected_status='QUEUED')

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

def just_ONE_CASE(is_deployed, is_public_changes, version_changes, new_onn_id):
    logger.info(f"is_deployed: {is_deployed}, is_public_changes: {is_public_changes}, version_changes: {version_changes}, new_onn_id: {new_onn_id}")

    orgAccountObj = get_test_org()
    orgAccountObj.desired_num_nodes=1
    orgAccountObj.is_public = True
    orgAccountObj.version = 'v2'
    orgAccountObj.save()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = is_deployed
    clusterObj.cur_version = orgAccountObj.version+'a' if version_changes else orgAccountObj.version
    clusterObj.is_public = not orgAccountObj.is_public if is_public_changes else orgAccountObj.is_public
    clusterObj.save()
    new_desired_num_nodes = orgAccountObj.desired_num_nodes
    expire_date = datetime.now(timezone.utc)+timedelta(hours=1)
    onn = OrgNumNode.objects.create(user=the_TEST_USER(),org=orgAccountObj, desired_num_nodes=new_desired_num_nodes,expiration=expire_date)
    clusterObj.cnnro_id = onn.id
    clusterObj.save()
    if new_onn_id:
        expire_date = datetime.now(timezone.utc)+timedelta(minutes=16) # before the one above!
        onn = OrgNumNode.objects.create(user=the_TEST_USER(),org=orgAccountObj, desired_num_nodes=new_desired_num_nodes,expiration=expire_date)
        clusterObj.save()

    need_to_destroy = need_destroy_for_changed_version_or_is_public(orgAccountObj,onn)
    if not is_deployed:
        assert not need_to_destroy
    else:
        if (is_public_changes or version_changes) and new_onn_id:
            logger.info(f"** is_deployed: {is_deployed}, is_public_changes: {is_public_changes}, version_changes: {version_changes}, new_onn_id: {new_onn_id}")
            logger.info(f"** cluster v:{clusterObj.cur_version} ip:{clusterObj.is_public} is_deployed:{clusterObj.is_deployed}")
            logger.info(f"**     org v:{orgAccountObj.version} ip:{orgAccountObj.is_public}")
            logger.info(f"** onnTop.id:{onn.id} != clusterObj.cnnro_id:{clusterObj.cnnro_id} ?")
            assert need_to_destroy    
        else:
            assert not need_to_destroy


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def  test_need_destroy_for_changed_version_or_is_public_ALL_CASES(caplog,create_TEST_USER,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test logic for forced Destroy if all combinations of these are met
    Changes to:
    | is_deployed | is_public | version |  new_onn_id  | Need to destroy?
    |-------------|-----------|---------|--------------|
    | 0           | 0         | 0       | 0            |
    | 0           | 0         | 0       | 1            |
    | 0           | 0         | 1       | 0            |
    | 0           | 0         | 1       | 1            |
    | 0           | 1         | 0       | 0            |
    | 0           | 1         | 0       | 1            |
    | 0           | 1         | 1       | 0            |
    | 0           | 1         | 1       | 1            |
    | 1           | 0         | 0       | 0            |
    | 1           | 0         | 0       | 1            |
    | 1           | 0         | 1       | 0            |
    | 1           | 0         | 1       | 1            | YES
    | 1           | 1         | 0       | 0            |
    | 1           | 1         | 0       | 1            | YES
    | 1           | 1         | 1       | 0            |
    | 1           | 1         | 1       | 1            | YES

    '''

    variables = [False, True]  # Possible values for the boolean variables
    for is_deployed in variables:
        for is_public in variables:
            for version in variables:
                for new_onn_id in variables:
                    just_ONE_CASE(is_deployed, is_public, version, new_onn_id)



