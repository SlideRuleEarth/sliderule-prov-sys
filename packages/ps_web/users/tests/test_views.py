from users.tests.global_test import GlobalTestCase
import pytest
import logging
import logging
import sys
import os
import pathlib
from importlib import import_module
from datetime import datetime, timezone, timedelta
from users.tests.utilities_for_unit_tests import *
from users.tasks import process_state_change,get_versions_for_org
from users.models import OwnerPSCmd,OrgNumNode,OrgAccount,PsCmdResult,Cluster
from django.urls import reverse
import time_machine
import json
from django.contrib.messages import get_messages
from unittest.mock import patch, MagicMock

from users.global_constants import *

parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)

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


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_index_loads_properly(client,initialize_test_environ):
    """The index page loads properly"""
    #LOG.info(f"{__name__}({self}) ... ------------------")
    response = client.get('http://localhost/', follow=True)
    assert(response.status_code == 200)

# 
#  -------  pytest stuff follows --------
#

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_adding_an_num_node(caplog,client,mock_email_backend,initialize_test_environ):
    '''
        This procedure will test a privileged user can queue a deploy cmd
    '''

    with time_machine.travel(datetime(year=2023, month=1, day=28,hour=11),tick=False):

        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
        
        logger.info(f"will now add onn by post of submit_value add_onn")
        form_prefix = 'add_onn-'
        url = reverse('org-manage-cluster',args=[get_test_org().id,])
        # setup necessary form data
        ttl_to_test = 20
        form_data = {
            f'{form_prefix}ttl_minutes': ttl_to_test,
            f'{form_prefix}desired_num_nodes': 1,
            f'form_submit': 'add_onn',
        }

        response = client.post(url,form_data)
        logger.info(f"status:{response.status_code}")
        # assert the form was successful
        assert response.status_code == 200 or response.status_code == 302
        assert OwnerPSCmd.objects.count() == 0
        assert OrgNumNode.objects.count() == 1
        onn = OrgNumNode.objects.first()
        assert onn is not None
        assert onn.desired_num_nodes == 1
        
        assert onn.expiration is not None
        assert onn.org == get_test_org() 

        assert onn.expiration == datetime.now(timezone.utc) + timedelta(minutes=ttl_to_test)


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_num_node_form_invalid_ttl_too_low(caplog,client,mock_email_backend,initialize_test_environ):

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    
    # setup necessary form data
    form_data = {
        'ttl_minutes': ONN_MIN_TTL-1,
        'desired_num_nodes': 1,
        'form_submit': 'add_onn',
    }
    # get the url
    url = reverse('org-manage-cluster', args=[get_test_org().id])
    # send the POST request
    response = client.post(url, form_data)
    # assert the form was successful
    assert response.status_code == 200 or response.status_code == 302
    assert OwnerPSCmd.objects.count() == 0
    assert OrgNumNode.objects.count() == 0

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_num_node_form_invalid_ttl_too_high(caplog,client,mock_email_backend,initialize_test_environ):

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    
    # setup necessary form data
    form_data = {
        'ttl_minutes': ONN_MAX_TTL+1,
        'desired_num_nodes': 1,
        'form_submit': 'add_onn',
    }
    # get the url
    url = reverse('org-manage-cluster', args=[get_test_org().id])
    # send the POST request
    response = client.post(url, form_data)
    # assert the form was successful
    assert response.status_code == 200 or response.status_code == 302
    assert OwnerPSCmd.objects.count() == 0
    assert OrgNumNode.objects.count() == 0

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_reg_user_access_negative_test(caplog,client,mock_email_backend,initialize_test_environ):
    user = verify_user(random_test_user())
    assert client.login(username=user.username, password=TEST_PASSWORD)
    assert not user.groups.filter(name='PS_Developer').exists()
    assert get_test_org().owner != user
    # get the url
    url = reverse('org-manage-cluster', args=[get_test_org().id])
    # send the POST request
    response = client.get(url)
    assert response.status_code == 401

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_account_cfg_success(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_email_backend,initialize_test_environ):
    assert OrgAccount.objects.count() == 1
    
    orgAccountObj = get_test_org()
    assert(not orgAccountObj.is_public) 
    assert(orgAccountObj.version == 'latest') 

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    
    # setup necessary form data
    form_data = {
        'is_public': True,
        'version': 'v3',
        'min_node_cap': 1,
        'max_node_cap': 10,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    start_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    # get the url
    url = reverse('org-configure', args=[orgAccountObj.id])
    # send the POST request
    response = client.post(url, data=form_data)
    current_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    call_process_state_change(orgAccountObj,1,start_cnt,current_cnt)
    # assert the form was successful
    # refresh the OrgAccount object
    orgAccountObj = get_test_org()
    assert response.status_code == 200 or response.status_code == 302
    assert(orgAccountObj.is_public) 
    assert(orgAccountObj.version == 'v3') 
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert clusterObj.provision_env_ready == True # Setup was called



#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_account_cfg_fail(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out,mock_email_backend,initialize_test_environ):
    assert OrgAccount.objects.count() == 1
    
    orgAccountObj = get_test_org()
    assert(not orgAccountObj.is_public) 
    assert(orgAccountObj.version == 'latest') 

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    
    # setup necessary form data
    form_data = {
        'is_public': True,
        'version': 'v3',
        'min_node_cap': 'BAD', ## <---- INVALID
        'max_node_cap': 10,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    start_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    # get the url
    url = reverse('org-configure', args=[orgAccountObj.id])
    # send the POST request
    response = client.post(url, data=form_data)
    current_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    call_process_state_change(orgAccountObj,0,start_cnt,current_cnt)
    # assert the form was unsuccessful
    # refresh the OrgAccount object
    orgAccountObj = get_test_org()
    assert response.status_code == 200 or response.status_code == 302
    assert(not orgAccountObj.is_public) # i.e. unmodified
    assert(orgAccountObj.version == 'latest')  # i.e. unmodified


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_destroy_cluster_only_one(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out,mock_email_backend,initialize_test_environ):
    assert OrgAccount.objects.count() == 1
    orgAccountObj = get_test_org()
    assert(not orgAccountObj.is_public) # fixture default
    assert(orgAccountObj.version == 'latest')  # fixture default

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    start_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    # get the url
    url = reverse('org-destroy-cluster', args=[orgAccountObj.id])
    # send the POST request
    # Test that only one gets queued no matter how many times you try
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    

    current_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    call_process_state_change(orgAccountObj,1,start_cnt,current_cnt)

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_org_refresh_cluster_only_one(caplog, client, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out,mock_email_backend,initialize_test_environ):
    assert OrgAccount.objects.count() == 1
    
    orgAccountObj = get_test_org()
    assert(not orgAccountObj.is_public) 
    assert(orgAccountObj.version == 'latest') 

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    start_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    # get the url
    url = reverse('org-refresh-cluster', args=[orgAccountObj.id])
    # send the POST request
    # Test that only one gets queued no matter how many times you try

    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    response = client.post(url)
    assert response.status_code in (200, 302) # redirects to org-manage-cluster # redirects to org-manage-cluster
    assert OwnerPSCmd.objects.count() == 1    
    current_cnt = mock_tasks_enqueue_stubbed_out.call_count+mock_views_enqueue_stubbed_out.call_count
    call_process_state_change(orgAccountObj,1,start_cnt,current_cnt)

@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize('initialize_test_environ', [{'version': 'latest', 'is_public': False},], indirect=True)
def test_change_version_with_user_view1(setup_logging, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, client, initialize_test_environ):
    logger = setup_logging
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
    initial_version = orgAccountObj.version
    initial_is_public = orgAccountObj.is_public
    if initial_version == 'latest':
        new_version = 'v3' 
    elif initial_version == 'v3':
        new_version = 'latest'
    else:
        assert False, f"initial_version:{initial_version} not supported"

    assert OrgAccount.objects.count() == 1
    orgAccountObj.save()

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    assert orgAccountObj.num_setup_cmd == 0
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd == 0
    
    logger.info(f"orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    # setup necessary form data
    form_data = {
        'is_public': initial_is_public,
        'version': initial_version, # First time we use the current version
        'min_node_cap': 1,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }

    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)

    # assert the form was successful
    # refresh the OrgAccount object
    orgAccountObj.refresh_from_db()
    assert(orgAccountObj.is_public == initial_is_public) 
    assert(orgAccountObj.version == initial_version) 
    assert orgAccountObj.num_setup_cmd == 1
    assert orgAccountObj.num_setup_cmd_successful == 1
    assert orgAccountObj.num_ps_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd == 2
    
    assert orgAccountObj.min_node_cap == 1
    assert orgAccountObj.max_node_cap == 3
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True

    assert clusterObj.is_deployed == False

    assert PsCmdResult.objects.count() == 2 # SetUp - Refresh 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label # no entries and min_node_cap is 1 so Update

    clusterObj.refresh_from_db()
    assert clusterObj.is_deployed == True

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 3,
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                            orgAccountObj=orgAccountObj,
                                            url_args=[orgAccountObj.id],
                                            access_token=None,
                                            data=form_data,
                                            expected_change_ps_cmd=1,
                                            expected_status='QUEUED',
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    assert PsCmdResult.objects.count() == 3 # SetUp - Update - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}") # update to 3
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label

    # setup necessary form data
    form_data = {
        'is_public': initial_is_public,
        'version': new_version, # <---- changed
        'min_node_cap': 1,
        'max_node_cap': 10,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2,mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Refresh (min nodes is 1)

    orgAccountObj.refresh_from_db()
    assert(orgAccountObj.is_public == initial_is_public) 
    assert(orgAccountObj.version == new_version) 
    assert orgAccountObj.num_setup_cmd == 2
    assert orgAccountObj.num_setup_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd_successful == 5
    assert orgAccountObj.num_ps_cmd == 5
    
    assert orgAccountObj.min_node_cap == 1
    assert orgAccountObj.max_node_cap == 10
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True


    assert PsCmdResult.objects.count() == 5 # Configure - Update - Update - Configure - Refresh 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Refresh' in psCmdResultObjs[4].ps_cmd_summary_label
    # logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
    # assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 3, # NOTE: we did NOT change this here
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.id],
                                                        access_token=None,
                                                        data=form_data,
                                                        expected_change_ps_cmd=0, # same desired_num_nodes so no change
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    
    assert orgAccountObj.desired_num_nodes == 3 # no change
    assert PsCmdResult.objects.count() == 5 # NO CHANGE - SetUp - Update - Update - SetUp - Destroy - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[4].ps_cmd_summary_label

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 4, # This triggers a change!
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.id],
                                                        access_token=None,
                                                        data=form_data,
                                                        expected_change_ps_cmd=1,  # Update
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    
    assert PsCmdResult.objects.count() == 7 # SetUp - Refresh - Update - SetUp - Destroy - Update - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
    logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label
    logger.info(f"[6]:{psCmdResultObjs[6].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[6].ps_cmd_summary_label

    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp_gen = stub.TearDown(ps_server_pb2.TearDownReq(name=orgAccountObj.name,now=datetime.now(timezone.utc).strftime(FMT)))
        cnt, got_rsp_done, stop_exception_cnt, exception_cnt, ps_error_cnt, stdout, stderr = verify_rsp_gen(rrsp_gen=rsp_gen,name=orgAccountObj.name,ps_cmd='TearDown',logger=logger)
        assert got_rsp_done == True
        assert exception_cnt == 0
        assert ps_error_cnt == 0
        assert stop_exception_cnt == 0
        assert cnt == 1
        assert stdout != ''
        assert stderr == ''

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize('initialize_test_environ', [{'version': 'v3', 'is_public': True},], indirect=True)
def test_change_version_with_user_view2(setup_logging, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, client, initialize_test_environ):
    logger = setup_logging
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
    initial_version = orgAccountObj.version
    initial_is_public = orgAccountObj.is_public
    if initial_version == 'latest':
        new_version = 'v3' 
    elif initial_version == 'v3':
        new_version = 'latest'
    else:
        assert False, f"initial_version:{initial_version} not supported"

    assert OrgAccount.objects.count() == 1
    orgAccountObj.save()

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    assert orgAccountObj.num_setup_cmd == 0
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd == 0
    
    logger.info(f"orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    # setup necessary form data
    form_data = {
        'is_public': initial_is_public,
        'version': initial_version, # First time we use the current version
        'min_node_cap': 1,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }

    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)

    # assert the form was successful
    # refresh the OrgAccount object
    orgAccountObj.refresh_from_db()
    assert(orgAccountObj.is_public == initial_is_public) 
    assert(orgAccountObj.version == initial_version) 
    assert orgAccountObj.num_setup_cmd == 1
    assert orgAccountObj.num_setup_cmd_successful == 1
    assert orgAccountObj.num_ps_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd == 2
    
    assert orgAccountObj.min_node_cap == 1
    assert orgAccountObj.max_node_cap == 3
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True

    assert clusterObj.is_deployed == False

    assert PsCmdResult.objects.count() == 2 # SetUp - Refresh 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label # no entries and min_node_cap is 1 so Update

    clusterObj.refresh_from_db()
    assert clusterObj.is_deployed == True

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 3,
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                            orgAccountObj=orgAccountObj,
                                            url_args=[orgAccountObj.id],
                                            access_token=None,
                                            data=form_data,
                                            expected_change_ps_cmd=1,
                                            expected_status='QUEUED',
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    assert PsCmdResult.objects.count() == 3 # SetUp - Update - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}") # update to 3
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label

    # setup necessary form data
    form_data = {
        'is_public': initial_is_public,
        'version': new_version,
        'min_node_cap': 1,
        'max_node_cap': 10,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=3,mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Refresh (min nodes is 1)

    orgAccountObj = get_test_org()
    assert(orgAccountObj.is_public == initial_is_public) 
    assert(orgAccountObj.version == new_version) 
    assert orgAccountObj.num_setup_cmd == 2
    assert orgAccountObj.num_setup_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd_successful == 6
    assert orgAccountObj.num_ps_cmd == 6
    
    assert orgAccountObj.min_node_cap == 1
    assert orgAccountObj.max_node_cap == 10
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True


    assert PsCmdResult.objects.count() == 6 # SetUp - Refresh - Update - SetUp - Refresh 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
    logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 3, # NOTE: we did NOT change this here
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.id],
                                                        access_token=None,
                                                        data=form_data,
                                                        expected_change_ps_cmd=0, # same desired_num_nodes so no change
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    
    assert orgAccountObj.desired_num_nodes == 3 # no change
    assert PsCmdResult.objects.count() == 6 # NO CHANGE - SetUp - Update - Update - SetUp - Destroy - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
    logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 4, # This triggers a change!
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                                        orgAccountObj=orgAccountObj,
                                                        url_args=[orgAccountObj.id],
                                                        access_token=None,
                                                        data=form_data,
                                                        expected_change_ps_cmd=1,  # Update
                                                        expected_status='QUEUED',
                                                        mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                        mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    
    assert PsCmdResult.objects.count() == 7 # SetUp - Refresh - Update - SetUp - Destroy - Update - Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
    logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label
    logger.info(f"[6]:{psCmdResultObjs[6].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[6].ps_cmd_summary_label

    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp_gen = stub.TearDown(ps_server_pb2.TearDownReq(name=orgAccountObj.name,now=datetime.now(timezone.utc).strftime(FMT)))
        cnt, got_rsp_done, stop_exception_cnt, exception_cnt, ps_error_cnt, stdout, stderr = verify_rsp_gen(rrsp_gen=rsp_gen,name=orgAccountObj.name,ps_cmd='TearDown',logger=logger)
        assert got_rsp_done == True
        assert exception_cnt == 0
        assert ps_error_cnt == 0
        assert stop_exception_cnt == 0
        assert cnt == 1
        assert stdout != ''
        assert stderr == ''


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize('initialize_test_environ', [{'version': 'latest', 'is_public': False}, {'version': 'v3', 'is_public': True}], indirect=True)
def test_change_is_public_with_user_view_with_onns(setup_logging, client,initialize_test_environ,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out,mock_schedule_process_state_change):
        logger = setup_logging
        
        orgAccountObj = get_test_org()
        clusterObj = Cluster.objects.get(org=orgAccountObj)
        assert(clusterObj.is_deployed == False)
        assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
        initial_version = orgAccountObj.version
        new_version = initial_version
        initial_is_public = orgAccountObj.is_public
        if initial_is_public:
            new_is_public = False
        else:
            new_is_public = True

        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

        assert OrgAccount.objects.count() == 1
        orgAccountObj.save()

        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

        assert orgAccountObj.num_setup_cmd == 0
        assert orgAccountObj.num_setup_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd == 0
        

        # setup necessary form data
        form_data = {
            'is_public': initial_is_public,
            'version': initial_version, # First time we use the current version
            'min_node_cap': 1,
            'max_node_cap': 3,
            'allow_deploy_by_token': True,
            'destroy_when_no_nodes': True,
            'provisioning_suspended': False,
        }

        assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)

        # assert the form was successful
        # refresh the OrgAccount object
        orgAccountObj = get_test_org()
        assert(orgAccountObj.is_public == initial_is_public)
        assert(orgAccountObj.version == initial_version) 
        assert orgAccountObj.num_setup_cmd == 1
        assert orgAccountObj.num_setup_cmd_successful == 1
        assert orgAccountObj.num_ps_cmd_successful == 2
        assert orgAccountObj.num_ps_cmd == 2
        
        assert orgAccountObj.min_node_cap == 1
        assert orgAccountObj.max_node_cap == 3
        assert orgAccountObj.allow_deploy_by_token == True
        assert orgAccountObj.destroy_when_no_nodes == True


        assert PsCmdResult.objects.count() == 2 # SetUp - Update (min_node_cap is 1)
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label


        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 3,
            'add_onn-ttl_minutes': 15,
        }
        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                expected_change_ps_cmd=1, # Update (to 3)
                                                expected_status='QUEUED',
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
        

        assert PsCmdResult.objects.count() == 3 # SetUp - Update (to 1) - Update (to 3)
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
        logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label

        # setup necessary form data
        form_data = {
            'is_public': new_is_public,
            'version': new_version,
            'min_node_cap': 1,
            'max_node_cap': 10,
            'allow_deploy_by_token': True,
            'destroy_when_no_nodes': True,
            'provisioning_suspended': False,
        }
        assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=3, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Refresh (min nodes is 1)
        logger.info(f"finished verify_org_configure")
        orgAccountObj = get_test_org()
        assert(orgAccountObj.is_public == new_is_public) 
        assert(orgAccountObj.version == new_version) 
        assert orgAccountObj.num_setup_cmd == 2
        assert orgAccountObj.num_setup_cmd_successful == 2
        assert orgAccountObj.num_ps_cmd_successful == 6
        assert orgAccountObj.num_ps_cmd == 6
        assert orgAccountObj.min_node_cap == 1
        assert orgAccountObj.max_node_cap == 10
        assert orgAccountObj.allow_deploy_by_token == True
        assert orgAccountObj.destroy_when_no_nodes == True


        assert PsCmdResult.objects.count() == 6 # SetUp - Refresh - Destroy - Update (to 3) - SetUp - Refresh 
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
        logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
        logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
        logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
        assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
        logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label

        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 3, # NOTE: we did NOT change this here
            'add_onn-ttl_minutes': 15,
        }
        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                expected_change_ps_cmd=0, # same desired_num_nodes so no change
                                                expected_status='QUEUED',
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

        

        assert orgAccountObj.desired_num_nodes == 3 # no change
        assert PsCmdResult.objects.count() == 6
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
        logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
        logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
        logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
        assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
        logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label

        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 4, # This triggers a change!
            'add_onn-ttl_minutes': 15,
        }
        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                expected_change_ps_cmd=1, # Update
                                                expected_status='QUEUED',
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # Destroy is inline so only 1
        
        assert PsCmdResult.objects.count() == 7 # + Destroy Update (new desired_num_nodes)
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
        logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[2].ps_cmd_summary_label
        logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[3].ps_cmd_summary_label
        logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
        assert 'Destroy' in psCmdResultObjs[4].ps_cmd_summary_label
        logger.info(f"[5]:{psCmdResultObjs[5].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[5].ps_cmd_summary_label
        logger.info(f"[6]:{psCmdResultObjs[6].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[6].ps_cmd_summary_label

        assert orgAccountObj.desired_num_nodes == 4    

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_web_user_desired_num_nodes(caplog, setup_logging, client, mock_email_backend, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, mock_schedule_process_state_change, initialize_test_environ, developer_TEST_USER):
    '''
        This procedure will test logic add num nodes from the org-manage-cluster web page
    '''
    logger = setup_logging
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert(clusterObj.is_deployed == False)
    assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
    initial_version = orgAccountObj.version
    new_version = initial_version
    initial_is_public = orgAccountObj.is_public

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    assert OrgAccount.objects.count() == 1
    orgAccountObj.save()

    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

    assert orgAccountObj.num_setup_cmd == 0
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd == 0
    

    # setup necessary form data
    form_data = {
        'is_public': initial_is_public,
        'version': initial_version, # First time we use the current version
        'min_node_cap': 1,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Refresh (min nodes is 1)
    # assert the form was successful
    # refresh the OrgAccount object
    orgAccountObj = get_test_org()
    assert(orgAccountObj.is_public == initial_is_public) 
    assert(orgAccountObj.version == initial_version) 
    assert orgAccountObj.num_setup_cmd == 1
    assert orgAccountObj.num_setup_cmd_successful == 1
    assert orgAccountObj.num_ps_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd == 2
    
    assert orgAccountObj.min_node_cap == 1
    assert orgAccountObj.max_node_cap == 3
    assert orgAccountObj.allow_deploy_by_token == True
    assert orgAccountObj.destroy_when_no_nodes == True
    assert PsCmdResult.objects.count() == 2 # SetUp - Refresh 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label # no entries and min_node_cap is 1 so Update
    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': -1, # Error
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(client=client,
                                            orgAccountObj=orgAccountObj,
                                            url_args=[orgAccountObj.id],
                                            access_token=None,
                                            data=form_data,
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                            expected_change_ps_cmd=0, # Error
                                            expected_status='FAILED',
                                            expected_html_status=200) # But error message is displayed
    # Get all messages from the response context
    stored_messages = [m.message for m in get_messages(response.wsgi_request)]
    assert any("Input Errors:" in message for message in stored_messages)

    # test clamp to minimum
    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 0, 
        'add_onn-ttl_minutes': 15,
    }

    response = verify_org_manage_cluster_onn(client=client,
                                            orgAccountObj=orgAccountObj,
                                            url_args=[orgAccountObj.id],
                                            access_token=None,
                                            data=form_data,
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                            expected_change_ps_cmd=0,# already set to min (i.e. 1) so no cmd issued
                                            expected_status='QUEUED')  # entry queued
# test clamp to maximum
    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': 20, 
        'add_onn-ttl_minutes': 15,
    }

    response = verify_org_manage_cluster_onn(client=client,
                                            orgAccountObj=orgAccountObj,
                                            url_args=[orgAccountObj.id],
                                            access_token=None,
                                            data=form_data,
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                            expected_change_ps_cmd=1, # update to max (i.e. 3)
                                            expected_status='QUEUED') 

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_web_user_clear_num_nodes(caplog, setup_logging, client, mock_email_backend, mock_schedule_process_state_change, mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out, initialize_test_environ, developer_TEST_USER):
        '''
            This procedure will test logic clear num nodes from the org-manage-cluster web page
        '''
        logger = setup_logging
        
        orgAccountObj = get_test_org()
        clusterObj = Cluster.objects.get(org=orgAccountObj)
        assert(clusterObj.is_deployed == False)
        assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
        initial_version = orgAccountObj.version
        new_version = initial_version
        initial_is_public = orgAccountObj.is_public

        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

        assert OrgAccount.objects.count() == 1
        orgAccountObj.refresh_from_db()

        assert orgAccountObj.num_setup_cmd == 0
        assert orgAccountObj.num_setup_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd == 0
        

        # setup necessary form data
        form_data = {
            'is_public': initial_is_public,
            'version': initial_version, # First time we use the current version
            'min_node_cap': 1,
            'max_node_cap': 3,
            'allow_deploy_by_token': True,
            'destroy_when_no_nodes': True,
            'provisioning_suspended': False,
        }

        assert verify_org_configure(client=client, 
                                    orgAccountObj=orgAccountObj, 
                                    data=form_data, 
                                    expected_change_ps_cmd=2,
                                    mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                    mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)
        # assert the form was successful
        # refresh the OrgAccount object
        orgAccountObj.refresh_from_db()
        assert(orgAccountObj.is_public == initial_is_public) 
        assert(orgAccountObj.version == initial_version) 
        assert orgAccountObj.num_setup_cmd == 1
        assert orgAccountObj.num_setup_cmd_successful == 1
        assert orgAccountObj.num_ps_cmd_successful == 2
        assert orgAccountObj.num_ps_cmd == 2
        
        assert orgAccountObj.min_node_cap == 1
        assert orgAccountObj.max_node_cap == 3
        assert orgAccountObj.allow_deploy_by_token == True
        assert orgAccountObj.destroy_when_no_nodes == True
        assert PsCmdResult.objects.count() == 2 # SetUp - Refresh 
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label # no entries and min_node_cap is 1 so Update
        assert OrgNumNode.objects.count() == 0

        # test clamp to minimum
        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 1, 
            'add_onn-ttl_minutes': 15,
        }

        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                                expected_change_ps_cmd=0,# already set to min (i.e. 1) so no cmd issued
                                                expected_status='QUEUED')  # this counter is num onn processed not queued
        log_ONN()
        assert OrgNumNode.objects.count() == 1


        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 2, 
            'add_onn-ttl_minutes': 15,
        }

        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                                expected_change_ps_cmd=1,# bumps to 2
                                                expected_status='QUEUED')  # this counter is num onn processed not queued
        log_ONN()
        assert OrgNumNode.objects.count() == 2
        url = reverse('clear-num-nodes-reqs',args=[orgAccountObj.id])
        logger.info(f"using url:{url}")

        response = client.post(url,HTTP_ACCEPT='application/json')
        assert((response.status_code == 200) or (response.status_code == 302))
        assert(is_in_messages(response, "ownertestuser cleaned all PENDING org node reqs for test_org",logger))
        assert OrgNumNode.objects.count() == 1

        # now clear the active one

        url = reverse('clear-active-num-node-req',args=[orgAccountObj.id])
        logger.info(f"using url:{url}")

        response = client.post(url,HTTP_ACCEPT='application/json')
        assert((response.status_code == 200) or (response.status_code == 302))
        assert(is_in_messages(response, "Successfully deleted active Org Num Node requests",logger))
        assert OrgNumNode.objects.count() == 0



#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_web_user_clear_num_nodes_multiple_users(caplog, setup_logging, client, mock_views_enqueue_stubbed_out, mock_tasks_enqueue_stubbed_out, mock_schedule_process_state_change, mock_email_backend, initialize_test_environ, developer_TEST_USER):
        '''
            This procedure will test logic clear num nodes from the 
            org-manage-cluster web page
        '''
        logger = setup_logging
        
        orgAccountObj = get_test_org()
        clusterObj = Cluster.objects.get(org=orgAccountObj)
        s_tcall_cnt = mock_tasks_enqueue_stubbed_out.call_count
        assert s_tcall_cnt == 0
        s_vcall_cnt = mock_views_enqueue_stubbed_out.call_count
        assert s_vcall_cnt == 1
        s_ps_cmd_rslt_cnt = PsCmdResult.objects.count() 
        assert s_ps_cmd_rslt_cnt == 0
        assert(clusterObj.is_deployed == False)
        assert(orgAccountObj.version == clusterObj.cur_version) # ensure initialization is correct 
        initial_version = orgAccountObj.version
        new_version = initial_version
        initial_is_public = orgAccountObj.is_public

        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

        assert OrgAccount.objects.count() == 1
        orgAccountObj.save()

        assert orgAccountObj.num_setup_cmd == 0
        assert orgAccountObj.num_setup_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd_successful == 0
        assert orgAccountObj.num_ps_cmd == 0
        

        # setup necessary form data
        form_data = {
            'is_public': initial_is_public,
            'version': initial_version, # First time we use the current version
            'min_node_cap': 1,
            'max_node_cap': 3,
            'allow_deploy_by_token': True,
            'destroy_when_no_nodes': True,
            'provisioning_suspended': False,
        }

        assert verify_org_configure(client=client, orgAccountObj=orgAccountObj, data=form_data, expected_change_ps_cmd=2, mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) # SetUp - Update (min nodes is 1)
        # assert the form was successful
        # refresh the OrgAccount object
        orgAccountObj = get_test_org()
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+1

        assert(orgAccountObj.is_public == initial_is_public) 
        assert(orgAccountObj.version == initial_version) 
        assert orgAccountObj.num_setup_cmd == 1
        assert orgAccountObj.num_setup_cmd_successful == 1
        assert orgAccountObj.num_ps_cmd_successful == 2
        assert orgAccountObj.num_ps_cmd == 2
        
        assert orgAccountObj.min_node_cap == 1
        assert orgAccountObj.max_node_cap == 3
        assert orgAccountObj.allow_deploy_by_token == True
        assert orgAccountObj.destroy_when_no_nodes == True
        assert PsCmdResult.objects.count() == s_ps_cmd_rslt_cnt + 2 # SetUp - Refresh 
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[{s_ps_cmd_rslt_cnt}]:{psCmdResultObjs[s_ps_cmd_rslt_cnt].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[s_ps_cmd_rslt_cnt].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
        logger.info(f"[{s_ps_cmd_rslt_cnt+1}]:{psCmdResultObjs[s_ps_cmd_rslt_cnt+1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[s_ps_cmd_rslt_cnt+1].ps_cmd_summary_label # no entries and min_node_cap is 1 so Update
        assert OrgNumNode.objects.count() == 0
        # test clamp to minimum
        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 1, 
            'add_onn-ttl_minutes': 15,
        }

        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, 
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                                expected_change_ps_cmd=0,# already set to min (i.e. 1) so no cmd issued
                                                expected_status='QUEUED') 
        log_ONN()
        assert OrgNumNode.objects.count() == 1
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+1
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+2
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)

        form_data = {
            'form_submit': 'add_onn',
            'add_onn-desired_num_nodes': 2, 
            'add_onn-ttl_minutes': 15,
        }

        response = verify_org_manage_cluster_onn(client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                access_token=None,
                                                data=form_data,
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out, 
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out, 
                                                expected_change_ps_cmd=1,# bumps to 2
                                                expected_status='QUEUED')  
        assert OrgNumNode.objects.count() == 2
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+2
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+3
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)


        rtu = random_test_user()
        m = create_active_membership(orgAccountObj,rtu)
        m.refresh_from_db()
        log_ONN()
        assert verify_api_user_makes_onn_ttl(client=client,
                                            orgAccountObj=orgAccountObj,
                                            user=rtu,
                                            password=TEST_PASSWORD,
                                            desired_num_nodes=1,
                                            ttl_minutes=15,
                                            expected_change_ps_cmd=1,
                                            mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                            mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out) 
        log_ONN()
        assert OrgNumNode.objects.count() == 3
        clusterObj.refresh_from_db()
        assert len(clusterObj.cnnro_ids) == 2
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+3
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+3
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)

        # Now negative test non owner user trying to remove entries

        assert(client.login(username=rtu, password=TEST_PASSWORD))

        url = reverse('clear-num-nodes-reqs',args=[orgAccountObj.id])
        logger.info(f"using url:{url}")

        response = client.post(url,HTTP_ACCEPT='application/json')
        assert((response.status_code == 200) or (response.status_code == 302))

        assert OrgNumNode.objects.count() == 3 # non owner cannot clear
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+3
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+3
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)


        # log back in with owner 
        assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))

        url = reverse('clear-num-nodes-reqs',args=[orgAccountObj.id])
        logger.info(f"using url:{url}")

        response = client.post(url,HTTP_ACCEPT='application/json')
        assert((response.status_code == 200) or (response.status_code == 302))
        assert OrgNumNode.objects.count() == 2
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+4
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+4
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)

        # now clear the active ones

        url = reverse('clear-active-num-node-req',args=[orgAccountObj.id])
        logger.info(f"using url:{url}")
        response = client.post(url,HTTP_ACCEPT='application/json')
        assert((response.status_code == 200) or (response.status_code == 302))
        assert OrgNumNode.objects.count() == 0
        clusterObj.refresh_from_db()
        # Get all messages from the response context
        stored_messages = [m.message for m in get_messages(response.wsgi_request)]
        assert not any("No active Org Num Node request to delete" in message for message in stored_messages)
        assert any("Successfully deleted active Org Num Node requests" in message for message in stored_messages)

        assert len(clusterObj.cnnro_ids) == 0
        logger.info(f"mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count}")
        assert mock_tasks_enqueue_stubbed_out.call_count == s_tcall_cnt+4
        assert mock_tasks_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
        logger.info(f"mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count}")
        assert mock_views_enqueue_stubbed_out.call_count == s_vcall_cnt+5
        assert mock_views_enqueue_stubbed_out.call_args == call(orgAccountObj.name)
