import pytest
import logging
import sys
import os
import pathlib
import uuid
import pytz
import json
import pprint
import grpc
from users import ps_client
import time_machine
from subprocess import CalledProcessError
import ps_server_pb2
import ps_server_pb2_grpc
from google.protobuf.json_format import MessageToJson

from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from django.urls import reverse
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user,pytest_approx,the_TEST_USER,init_mock_ps_server,verify_org_manage_cluster_onn,the_OWNER_USER,check_for_scheduled_jobs,clear_enqueue_process_state_change,verify_org_configure,verify_post_org_num_nodes_ttl
from users.models import Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster,PsCmdResult,GranChoice,OrgCost
from users.forms import OrgAccountForm
from users.tasks import update_burn_rates,purge_old_PsCmdResultsForOrg,process_num_node_table,process_owner_ps_cmds_table,process_Update_cmd,process_Destroy_cmd,process_Refresh_cmd,cost_accounting,check_provision_env_ready,sort_ONN_by_nn_exp,remove_num_node_requests,get_scheduled_jobs,log_scheduled_jobs,process_state_change,process_num_nodes_api,delete_onn_and_its_scheduled_job,get_scheduler,enqueue_process_state_change,get_or_create_OrgNumNodes,remove_PsCmdResultsWithNoExpirationAndOldCreationDate,getGranChoice,update_orgCost,get_db_org_cost,get_fytd_cost,debit_charges
from time import sleep
from django.contrib import messages
from allauth.account.decorators import verified_email_required
from django.forms.models import model_to_dict

from users.global_constants import *
from users.tests.global_test_constants import *
from users.ps_errors import *
# Import the fixtures
from users.tests.utilities_for_unit_tests import TEST_USER,TEST_PASSWORD,DEV_TEST_USER,DEV_TEST_PASSWORD,TEST_ORG_NAME

module_name = 'tasks'
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

# # do all setup before running all tests here
# def setup_module(tasks_module):
#     logger.info('---setup complete---')
    

# # teardown after running all tests 
# def teardown_module(tasks_module):
#     logger.info('---teardown complete---')

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_update_burn_rates(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'update_burn_rates' routine
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)

    assert(orgAccountObj.name == TEST_ORG_NAME)
    init_mock_ps_server(name=TEST_ORG_NAME,num_nodes=1)

    assert(orgAccountObj.owner.username == OWNER_USER)
    update_burn_rates(orgAccountObj)
    logger.info(f"{orgAccountObj.min_node_cap}/{clusterObj.cur_nodes}/{orgAccountObj.max_node_cap}")
    logger.info(f"{orgAccountObj.min_hrly}/{orgAccountObj.cur_hrly}/{orgAccountObj.max_hrly}")
    assert(pytest_approx(orgAccountObj.min_hrly,0.0001))
    assert(pytest_approx(orgAccountObj.cur_hrly,0.379))
    assert(pytest_approx(orgAccountObj.max_hrly,2.413))

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_purge_old_PsCmdResultsForOrg(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'purge_old_PsCmdResultsForOrg' routine
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    psCmdResultObj = PsCmdResult.objects.create(org=orgAccountObj,expiration=datetime.now(timezone.utc)+timedelta(days=1))
    psCmdResultObj = PsCmdResult.objects.create(org=orgAccountObj,expiration=datetime.now(timezone.utc)-timedelta(minutes=1))

    assert(orgAccountObj.name == TEST_ORG_NAME)
    assert(orgAccountObj.owner.username == OWNER_USER)
    assert(PsCmdResult.objects.count()==2) 
    purge_old_PsCmdResultsForOrg(orgAccountObj)
    assert(PsCmdResult.objects.count()==2) 

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_EMPTY_DESTROY(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when it should destroy the cluster when there are no
        capacity requests (i.e. onn) 
        and min num nodes is zero
        Note: we use the org name to trigger the specific exception in our Mock ps-server
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = True
    orgAccountObj.min_node_cap = 0
    
    assert OrgNumNode.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    process_num_node_table(orgAccountObj,0,False)
    orgAccountObj.refresh_from_db()
    
    assert orgAccountObj.num_setup_cmd == 0
    assert orgAccountObj.num_ps_cmd == 1 # Destroy
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 1
    assert PsCmdResult.objects.count() == 1
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[1]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[0].ps_cmd_summary_label


#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_EMPTY_UPDATE(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when it should NOT destroy the cluster when there 
        are no capacity requests and 
        and min num nodes is NOT zero so Update is issued for min num nodes
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 1
    orgAccountObj.save()
    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    
    assert OrgNumNode.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    process_num_node_table(orgAccountObj,0,False)
    orgAccountObj.refresh_from_db()
    
    assert orgAccountObj.num_ps_cmd == 1 #  Update
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 1
    assert PsCmdResult.objects.count() == 1
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
    assert orgAccountObj.desired_num_nodes == 1

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_EMPTY_NOT_DEPLOYED(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when it should NOT destroy the cluster when there 
        are no capacity requests and 
        and min num nodes is zero and the cluster is not deployed (i.e. NOTHING HAPPENS)
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = False
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 0
    orgAccountObj.save()
    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    
    assert OrgNumNode.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    process_num_node_table(orgAccountObj,0,False)
    orgAccountObj.refresh_from_db()
    
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    assert orgAccountObj.desired_num_nodes == 0

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_EMPTY_SET_TO_MIN(tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when it should NOT destroy the cluster when there 
        are no capacity requests and 
        and min num nodes is NOT zero and 
        the current desired_nodes is not 
        the same as min (last deployment was different than min)
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.save()
    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 0
    
    assert OrgNumNode.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    process_num_node_table(orgAccountObj,0,False)
    orgAccountObj.refresh_from_db()
    
    assert orgAccountObj.num_ps_cmd == 1 #  Update
    assert orgAccountObj.num_setup_cmd_successful == 0
    assert orgAccountObj.num_ps_cmd_successful == 1
    assert PsCmdResult.objects.count() == 1
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_NOT_EMPTY_CHANGE_VERSION(tasks_module,client,create_TEST_USER,initialize_test_environ,mock_tasks_enqueue_stubbed_out,mock_views_enqueue_stubbed_out):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when the ONN table entry is processed when the version was changed
        and generates a Destroy cmd
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    # setup necessary form data
    initial_version = orgAccountObj.version
    initial_is_public = orgAccountObj.is_public
    if initial_version == 'latest':
        new_version = 'v3' 
    elif initial_version == 'v3':
        new_version = 'latest'
    form_data = {
        'is_public': initial_is_public,
        'version': initial_version, 
        'min_node_cap': 1,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    verify_org_configure(client=client,
                         data=form_data,
                         orgAccountObj=orgAccountObj,
                         expected_change_ps_cmd=2, # SetUp Update
                         expected_change_setup_cmd=1,
                         mock_tasks_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                         mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

    logger.info(f"clusterObj.cur_version={clusterObj.cur_version} clusterObj.is_deployed={clusterObj.is_deployed}")

    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 1
    
    assert OrgNumNode.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 2
    assert PsCmdResult.objects.count() == 2
    
    orgAccountObj.refresh_from_db()
    logger.info(f"orgAccountObj: num_ps_cmd={orgAccountObj.num_ps_cmd} desired_num_nodes={orgAccountObj.desired_num_nodes} cnt:{PsCmdResult.objects.count()}")
     
    assert OwnerPSCmd.objects.count() == 0
    assert orgAccountObj.num_setup_cmd == 1 
    assert orgAccountObj.num_ps_cmd == 2 #  SetUp, Update
    assert orgAccountObj.num_setup_cmd_successful == 1
    assert orgAccountObj.num_ps_cmd_successful == 2 # SetUp, Update 
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    assert PsCmdResult.objects.count() == 2
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label

    form_data = {
        'is_public': initial_is_public,
        'version': new_version, 
        'min_node_cap': 1,
        'max_node_cap': 3,
        'allow_deploy_by_token': True,
        'destroy_when_no_nodes': True,
        'provisioning_suspended': False,
    }
    verify_org_configure(client=client,
                         data=form_data,
                         orgAccountObj=orgAccountObj,
                         expected_change_ps_cmd=3, # ... SetUp, Destroy, Update,
                         expected_change_setup_cmd=1,
                         mock_tasks_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                         mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    assert orgAccountObj.num_setup_cmd == 2 # handled in fixture and here
    assert orgAccountObj.num_ps_cmd == 5 # SetUp, Update, Destroy, SetUp, Update
    assert orgAccountObj.num_setup_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd_successful == 5 #  SetUp, Update, SetUp, Destroy, Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    assert PsCmdResult.objects.count() == 5
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[4].ps_cmd_summary_label

    form_data = {
        'form_submit': 'add_onn',
        'add_onn-desired_num_nodes': orgAccountObj.desired_num_nodes,
        'add_onn-ttl_minutes': 15,
    }
    response = verify_org_manage_cluster_onn(   client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.id],
                                                data=form_data,
                                                expected_change_ps_cmd=0, # Destroy is now handled in configure/SetUp
                                                expected_status='QUEUED',
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)
    assert OwnerPSCmd.objects.count() == 0
    assert orgAccountObj.num_setup_cmd == 2 # handled in fixture and here
    assert orgAccountObj.num_ps_cmd == 5 # SetUp, Update, SetUp Destroy, Update
    assert orgAccountObj.num_setup_cmd_successful == 2
    assert orgAccountObj.num_ps_cmd_successful == 5 #  SetUp, Update, SetUp, Destroy, Update
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"PsCmdResult.objects.count()={PsCmdResult.objects.count()}")
    assert PsCmdResult.objects.count() == 5
    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    logger.info(f"[2]:{psCmdResultObjs[2].ps_cmd_summary_label}")
    assert 'Configure' in psCmdResultObjs[2].ps_cmd_summary_label
    logger.info(f"[3]:{psCmdResultObjs[3].ps_cmd_summary_label}")
    assert 'Destroy' in psCmdResultObjs[3].ps_cmd_summary_label
    logger.info(f"[4]:{psCmdResultObjs[4].ps_cmd_summary_label}")
    assert 'Update' in psCmdResultObjs[4].ps_cmd_summary_label

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_NOT_EMPTY_CHANGE_IS_PUBLIC(tasks_module,create_TEST_USER,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when the ONN table is not empty 
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.cur_version = 'v3'
    clusterObj.is_public = True
    clusterObj.provision_env_ready = True
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 2
    orgAccountObj.version = 'v3'
    orgAccountObj.is_public = False
    orgAccountObj.save()
    expire_date = datetime.now(timezone.utc)+timedelta(hours=1)
    OrgNumNode.objects.create(user=the_TEST_USER(),org=orgAccountObj, desired_num_nodes=orgAccountObj.desired_num_nodes+1,expiration=expire_date)
    clusterObj.cnnro_ids = []
    clusterObj.cnnro_ids.append(str(OrgNumNode.objects.first().id))
    logger.info(f"clusterObj.cnnro_ids:{clusterObj.cnnro_ids}")
    clusterObj.save()

    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 2
    
    assert OrgNumNode.objects.count() == 1
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    
    process_num_node_table(orgAccountObj,0,False)

    orgAccountObj.refresh_from_db()
    
    assert OwnerPSCmd.objects.count() == 0
    assert orgAccountObj.num_ps_cmd == 1
    assert orgAccountObj.desired_num_nodes == 3 
    assert PsCmdResult.objects.count() == 1
    psCmdResultObj = PsCmdResult.objects.first()
    assert 'Update' in psCmdResultObj.ps_cmd_summary_label
    assert OrgNumNode.objects.count() == 1 # until it expires

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_process_num_node_table_ONN_NOT_EMPTY_UPDATE(tasks_module,create_TEST_USER,initialize_test_environ):
    '''
        This procedure will test the 'process_num_node_table' routine
        for the case when the ONN table entry processed changes desired num nodes
        and generates an Update
    '''

    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.cur_version = 'v3'
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 2
    new_desire_num_nodes = orgAccountObj.desired_num_nodes+1
    orgAccountObj.version = 'v3'
    orgAccountObj.save()
    expire_date = datetime.now(timezone.utc)+timedelta(hours=1)
    OrgNumNode.objects.create(user=the_TEST_USER(),org=orgAccountObj, desired_num_nodes=new_desire_num_nodes,expiration=expire_date)

    logger.info(f"desired:{orgAccountObj.desired_num_nodes}")
    assert orgAccountObj.desired_num_nodes == 2
    
    assert OrgNumNode.objects.count() == 1
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0
    
    process_num_node_table(orgAccountObj,0,False)

    orgAccountObj.refresh_from_db()
    
    assert OwnerPSCmd.objects.count() == 0 
    assert orgAccountObj.num_ps_cmd == 1 # 
    assert orgAccountObj.desired_num_nodes == new_desire_num_nodes
    assert PsCmdResult.objects.count() == 1
    psCmdResultObj = PsCmdResult.objects.first()
    assert 'Update' in psCmdResultObj.ps_cmd_summary_label
    assert OrgNumNode.objects.count() == 1 # until it expires
    onn = OrgNumNode.objects.first()
    clusterObj.refresh_from_db()
    assert str(onn.id) in clusterObj.cnnro_ids




test_params = [
    (NEG_TEST_GRPC_ERROR_ORG_NAME, NEG_TEST_GRPC_ERROR_MSG),
    (NEG_TEST_TERRAFORM_ERROR_ORG_NAME, NEG_TEST_TERRAFORM_ERROR_MSG),
    (NEG_TEST_STOP_ITER_ERROR_ORG_NAME, NEG_TEST_STOP_ITER_ERROR_MSG),
]
#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG", test_params)
def test_process_Update_cmd_when_exception_occurs(create_TEST_USER, NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG,setup_logging):
    '''
        This procedure will accept generic parms to negative test the 'process_Update_cmd' routine 
    '''
    logger = setup_logging
    init_test_environ(name=NEG_TEST_ERROR_ORG_NAME,the_logger=logger)
    orgAccountObj = get_test_org(NEG_TEST_ERROR_ORG_NAME)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.cur_version = 'v3'
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 0
    orgAccountObj.max_node_cap = 4
    orgAccountObj.is_public = False
    new_desire_num_nodes = orgAccountObj.desired_num_nodes+1
    orgAccountObj.version = 'v3'
    orgAccountObj.save()
    test_min = 0
    test_desired = 2
    test_max = 5
    test_version = 'v3'
    test_is_public = False
    test_expire_time = datetime.now(timezone.utc)+timedelta(hours=1)
    deploy_values ={'min_node_cap': test_min, 'desired_num_nodes': test_desired, 'max_node_cap': test_max,'version': test_version, 'is_public': test_is_public, 'expire_time': test_expire_time }

    with pytest.raises(ProvisionCmdError) as error:
        process_Update_cmd(orgAccountObj,TEST_USER,deploy_values,test_expire_time)

    # Assert that the error details match the expected error
    #logger.critical(f"error:{repr(error)}")
    assert str(NEG_TEST_ERROR_MSG) in str(error.value)

test_params = [
    (NEG_TEST_LOW_BALANCE_ORG_NAME, NEG_TEST_LOW_BALANCE_ERROR_MSG)
]
#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG", test_params)
def test_process_Update_cmd_when_LOW_BALANCE_exception_occurs_ON_Update(create_TEST_USER, NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG):
    '''
        This procedure will do a negative test of the 'process_Update_cmd' routine for LOW balance error
    '''

    init_test_environ(name=NEG_TEST_ERROR_ORG_NAME,balance=2.0)
    orgAccountObj = get_test_org(NEG_TEST_ERROR_ORG_NAME)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.cur_version = 'v3'
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 0
    orgAccountObj.max_node_cap = 4
    orgAccountObj.is_public = False
    orgAccountObj.version = 'v3'
    orgAccountObj.save()
    #logger.critical(f"BEFORE orgAccountObj:{pprint.pformat(model_to_dict(orgAccountObj,fields=None))}")
    cost_accounting(orgAccountObj)
    #logger.critical(f" AFTER orgAccountObj:{pprint.pformat(model_to_dict(orgAccountObj,fields=None))}")
    test_min = 0
    test_desired = 2
    test_max = 5
    test_version = 'v3'
    test_is_public = False
    test_expire_time = datetime.now(timezone.utc)+timedelta(hours=1)
    deploy_values ={'min_node_cap': test_min, 'desired_num_nodes': test_desired, 'max_node_cap': test_max,'version': test_version, 'is_public': test_is_public, 'expire_time': test_expire_time }

    with pytest.raises((ProvisionCmdError,LowBalanceError)) as error:
        process_Update_cmd(orgAccountObj,TEST_USER,deploy_values,test_expire_time)

    # Assert that the error details match the expected error
    #logger.critical(f"error:{repr(error)}")
    assert str(NEG_TEST_ERROR_MSG) in str(error.value)

test_params = [
    (NEG_TEST_TERRAFORM_ERROR_ORG_NAME, NEG_TEST_TERRAFORM_ERROR_MSG, 'Destroy'),
    (NEG_TEST_TERRAFORM_ERROR_ORG_NAME, NEG_TEST_TERRAFORM_ERROR_MSG, 'Refresh')
]
#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG, PS_CMD", test_params)
def test_process_Update_cmd_when_exception_occurs_ON_OWNER_PS_CMD(create_TEST_USER, NEG_TEST_ERROR_ORG_NAME, NEG_TEST_ERROR_MSG, PS_CMD):
    '''
        This procedure will accept generic parms to negative test the 'process_Update_cmd' routine when processing Owner PS Cmds (i.e. Destroy and Refresh)
    '''
    init_test_environ(name=NEG_TEST_ERROR_ORG_NAME)
    orgAccountObj = get_test_org(NEG_TEST_ERROR_ORG_NAME)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = True
    clusterObj.cur_version = 'v3'
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 0
    orgAccountObj.max_node_cap = 4
    orgAccountObj.is_public = False
    new_desire_num_nodes = orgAccountObj.desired_num_nodes+1
    orgAccountObj.version = 'v3'
    orgAccountObj.save()
    test_min = 0
    test_desired = 2
    test_max = 5
    test_version = 'v3'
    test_is_public = False
    test_expire_time = datetime.now(timezone.utc)+timedelta(hours=1)
    deploy_values ={'min_node_cap': test_min, 'desired_num_nodes': test_desired, 'max_node_cap': test_max,'version': test_version, 'is_public': test_is_public, 'expire_time': test_expire_time }
    owner_ps_cmd = OwnerPSCmd.objects.create(user=orgAccountObj.owner, org=orgAccountObj, ps_cmd='Destroy', create_time=datetime.now(timezone.utc))
    assert OwnerPSCmd.objects.count()==1
    with pytest.raises(ProvisionCmdError) as error:
        if PS_CMD == 'Destroy':
            process_Destroy_cmd(orgAccountObj,TEST_USER,owner_ps_cmd=owner_ps_cmd)
        elif PS_CMD == 'Refresh':
            process_Refresh_cmd(orgAccountObj,TEST_USER,owner_ps_cmd=owner_ps_cmd)
        else:
            assert False, f"PS_CMD:{PS_CMD} is not a valid value"
    assert OwnerPSCmd.objects.count()==0
    # Assert that the error details match the expected error
    #logger.critical(f"error:{repr(error)}")
    assert str(NEG_TEST_ERROR_MSG) in str(error.value)

def setup_before_process_num_node_table_with_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,IS_DEPLOYED):
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.is_deployed = IS_DEPLOYED
    clusterObj.is_public = False
    clusterObj.cur_version = 'v1.0.0'
    clusterObj.save()
    orgAccountObj.destroy_when_no_nodes = DESTROY_WHEN_NO_NODES
    orgAccountObj.min_node_cap = MIN_NODE_CAP
    orgAccountObj.desired_num_nodes = MIN_NODE_CAP + 1 # we need this to not equal orgAccountObj.min_node_cap to force the Destroy
    orgAccountObj.is_public = clusterObj.is_public
    orgAccountObj.version = clusterObj.cur_version
    orgAccountObj.save()

    if not ONN_IS_EMPTY:
        OrgNumNode.objects.create(  org=orgAccountObj, 
                                    user=orgAccountObj.owner, 
                                    desired_num_nodes= MIN_NODE_CAP + 2, # to force the Update
                                    expiration=datetime.now(timezone.utc)+timedelta(hours=1))
        assert OrgNumNode.objects.count() == 1
    else:
        # this verfies that the cull_expired_entries is called and properly deletes the expired entry
        OrgNumNode.objects.create(  org=orgAccountObj, 
                                    user=orgAccountObj.owner, 
                                    desired_num_nodes= MIN_NODE_CAP + 2, # to force the Update
                                    expiration=datetime.now(timezone.utc)-timedelta(minutes=1))# Expired and will be deleted
        assert OrgNumNode.objects.count() == 1
    
    assert orgAccountObj.num_ps_cmd == 0
    assert PsCmdResult.objects.count() == 0

def verify_after_process_num_node_table_after_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,WAS_DEPLOYED):
    '''
        This procedure will verify the OrgNumNode table after an exception occurs in the process_Update_cmd routine

        Args:       orgAccountObj:          The OrgAccount object
                    ONN_IS_EMPTY:           Boolean indicating if the OrgNumNode table is empty
                    DESTROY_WHEN_NO_NODES:  Boolean indicating if the OrgAccount.destroy_when_no_nodes is True
                    MIN_NODE_CAP:           The OrgAccount.min_node_cap
                    WAS_DEPLOYED:           Boolean indicating if the Cluster.is_deployed is True
        we assume in setup that onnTop.desired_num_nodes != orgAccountObj.desired_num_nodes: 
    '''
    logger.info(f"orgAccountObj:{orgAccountObj} ONN_IS_EMPTY:{ONN_IS_EMPTY} DESTROY_WHEN_NO_NODES:{DESTROY_WHEN_NO_NODES} MIN_NODE_CAP:{MIN_NODE_CAP} WAS_DEPLOYED:{WAS_DEPLOYED}")
    orgAccountObj.refresh_from_db()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    logger.info(f"orgAccountObj.max_ddt:{orgAccountObj.max_ddt}")
    logger.info(f"timedelta(hours=MIN_HRS_TO_LIVE_TO_START):{timedelta(hours=MIN_HRS_TO_LIVE_TO_START)}")
    assert OrgNumNode.objects.count() == 0 # on exception we remove the entry
    assert ((clusterObj.cnnro_ids == []) or (clusterObj.cnnro_ids == None)) # cleaned up on exception
    called_process_Destroy_cmd = False
    called_process_Update_cmd = False
    called_process_SetUp_cmd = False
    cmd_cnt = 0
    if ONN_IS_EMPTY:
        if DESTROY_WHEN_NO_NODES and MIN_NODE_CAP == 0:
            if WAS_DEPLOYED:
                called_process_Destroy_cmd = True
                cmd_cnt = cmd_cnt+1
        else:
            if orgAccountObj.min_node_cap != orgAccountObj.desired_num_nodes:
                if not WAS_DEPLOYED:
                    called_process_SetUp_cmd = True
                    cmd_cnt = cmd_cnt+1
                called_process_Update_cmd = True
                cmd_cnt = cmd_cnt+1
    else:
        if not WAS_DEPLOYED:
            called_process_SetUp_cmd = True
            cmd_cnt = cmd_cnt+1
        called_process_Update_cmd = True
        cmd_cnt = cmd_cnt+1
    if called_process_Destroy_cmd:
        assert WAS_DEPLOYED
        assert orgAccountObj.num_ps_cmd == 1  
        logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
        assert PsCmdResult.objects.count() == 1
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Destroy' in psCmdResultObjs[0].ps_cmd_summary_label
    elif called_process_SetUp_cmd:
        assert not WAS_DEPLOYED
        assert orgAccountObj.num_ps_cmd == 2  
        logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
        assert PsCmdResult.objects.count() == 2
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
        logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
    elif called_process_Update_cmd:
        assert orgAccountObj.num_ps_cmd == 1  
        logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
        assert PsCmdResult.objects.count() == 1
        psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
        logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
        assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label



test_params = [
    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,True,2,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,True,2,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,True,2,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,False,2,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,False,2,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,False,2,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,True,0,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,True,0,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,True,0,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,False,0,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,False,0,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,False,0,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,True,2,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,True,2,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,True,2,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,False,2,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,False,2,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,False,2,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,True,0,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,True,0,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,True,0,True),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,False,0,True),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,False,0,True),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,False,0,True),
# ###########
    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,True,2,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,True,2,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,True,2,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,False,2,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,False,2,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,False,2,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,True,0,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,True,0,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,True,0,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,True,False,0,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,True,False,0,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,True,False,0,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,True,2,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,True,2,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,True,2,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,False,2,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,False,2,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,False,2,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,True,0,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,True,0,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,True,0,False),

    ((ProvisionCmdError,Exception),NEG_TEST_GRPC_ERROR_ORG_NAME,False,False,0,False),
    ((ProvisionCmdError,CalledProcessError,Exception),NEG_TEST_TERRAFORM_ERROR_ORG_NAME,False,False,0,False),
    ((ProvisionCmdError,StopIteration,Exception),NEG_TEST_STOP_ITER_ERROR_ORG_NAME,False,False,0,False),

]
#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("PS_EXCEPTIONS,NEG_TEST_ERROR_ORG_NAME, ONN_IS_EMPTY, DESTROY_WHEN_NO_NODES, MIN_NODE_CAP, IS_DEPLOYED", test_params)
def test_process_num_node_table_NEGATIVE_TESTS(tasks_module,create_TEST_USER, PS_EXCEPTIONS, NEG_TEST_ERROR_ORG_NAME, ONN_IS_EMPTY, DESTROY_WHEN_NO_NODES, MIN_NODE_CAP, IS_DEPLOYED):
    '''
        This procedure will negative test the 'process_num_node_table' routine
        for the case when it should destroy the cluster when there are no
        capacity requests (i.e. onn) 
        and min num nodes is zero and an terraform exception is raised
        Note: we use the org name to trigger the specific exception in our Mock ps-server
    '''
    init_test_environ(name=NEG_TEST_ERROR_ORG_NAME)
    orgAccountObj = get_test_org(NEG_TEST_ERROR_ORG_NAME)
    setup_before_process_num_node_table_with_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,IS_DEPLOYED)
    process_num_node_table(orgAccountObj,0,False)
    logger.info(f"orgAccountObj:{orgAccountObj} ONN_IS_EMPTY:{ONN_IS_EMPTY} DESTROY_WHEN_NO_NODES:{DESTROY_WHEN_NO_NODES} MIN_NODE_CAP:{MIN_NODE_CAP} WAS_DEPLOYED:{IS_DEPLOYED}")
    verify_after_process_num_node_table_after_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,IS_DEPLOYED)
    if ONN_IS_EMPTY:
        if DESTROY_WHEN_NO_NODES and MIN_NODE_CAP == 0:
            if IS_DEPLOYED:
                psCmdResultObj = PsCmdResult.objects.first()
                assert 'Destroy' in psCmdResultObj.ps_cmd_summary_label
                assert orgAccountObj.destroy_when_no_nodes == False # under these conditions on exception we set destroy_when_no_nodes to False to stop loop
                assert orgAccountObj.desired_num_nodes == 0 # on exception we set desired to zero to match min to stop loop
                assert orgAccountObj.min_node_cap == 0 # on exception we set min to zero
        else:
            if MIN_NODE_CAP != orgAccountObj.desired_num_nodes:
                if IS_DEPLOYED:
                    assert orgAccountObj.num_ps_cmd == 1  
                    logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
                    assert PsCmdResult.objects.count() == 1
                    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
                    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
                    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
                else:
                    assert orgAccountObj.num_ps_cmd == 2  
                    logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
                    assert PsCmdResult.objects.count() == 2
                    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
                    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
                    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
                    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
                    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label     
                    assert orgAccountObj.desired_num_nodes == 0 # on exception we set desired to zero to match min to stop loop
                    assert orgAccountObj.min_node_cap == 0 # on exception we set min to zero
                    assert orgAccountObj.desired_num_nodes == 0 # on exception we set desired to zero to match min to stop loop
    else:
        # assume onnTop.desired_num_nodes != orgAccountObj.desired_num_nodes
        # Note: here we just remove the entry that got the exception
        # and we do not expect the desired_num_nodes to be changed in this pass
        if IS_DEPLOYED:
            assert orgAccountObj.num_ps_cmd == 1  
            logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
            assert PsCmdResult.objects.count() == 1
            psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
            logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
            assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
        else:
            assert orgAccountObj.num_ps_cmd == 2  
            logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
            assert PsCmdResult.objects.count() == 2
            psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
            logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
            assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
            logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
            assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label     

test_params = [
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,True,2,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,False,2,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,True,0,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,False,0,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,True,2,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,False,2,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,True,0,False),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,False,0,False),

    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,True,2,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,False,2,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,True,0,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',True,False,0,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,True,2,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,False,2,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,True,0,True),
    ((ProvisionCmdError,Exception),'LowBalanceError_org',False,False,0,True),
]
#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
@pytest.mark.parametrize("PS_EXCEPTIONS, NEG_TEST_ERROR_ORG_NAME, ONN_IS_EMPTY, DESTROY_WHEN_NO_NODES, MIN_NODE_CAP, IS_DEPLOYED", test_params)
def test_process_process_num_node_table_when_LOW_BALANCE_exception_occurs_ON_Update(create_TEST_USER, PS_EXCEPTIONS, NEG_TEST_ERROR_ORG_NAME, ONN_IS_EMPTY, DESTROY_WHEN_NO_NODES, MIN_NODE_CAP,IS_DEPLOYED):
    '''
        This procedure will do a negative test of the 'process_Update_cmd' routine for LOW balance error
    '''
    #logger.critical(f"COOLOFF_SECS:{COOLOFF_SECS}")
    init_test_environ(name=NEG_TEST_ERROR_ORG_NAME,balance=2.0)
    orgAccountObj = get_test_org(NEG_TEST_ERROR_ORG_NAME)
    #logger.critical(f"BEFORE orgAccountObj:{pprint.pformat(model_to_dict(orgAccountObj,fields=None))}")
    cost_accounting(orgAccountObj)
    setup_before_process_num_node_table_with_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,IS_DEPLOYED)
    orgAccountObj.balance = 2.0 # force low balance exception
    orgAccountObj.save()
    process_num_node_table(orgAccountObj,0,False)
    verify_after_process_num_node_table_after_exception(orgAccountObj,ONN_IS_EMPTY,DESTROY_WHEN_NO_NODES,MIN_NODE_CAP,IS_DEPLOYED)
    if ONN_IS_EMPTY:
        if DESTROY_WHEN_NO_NODES and MIN_NODE_CAP == 0:
            if IS_DEPLOYED:
                assert PsCmdResult.objects.count() == 1 
                psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
                logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
                assert 'Destroy' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
                assert orgAccountObj.destroy_when_no_nodes == DESTROY_WHEN_NO_NODES # we don't throw an exception when destroying for low balance
                assert orgAccountObj.min_node_cap == MIN_NODE_CAP # on exception we set min to zero
        else:
            if MIN_NODE_CAP != orgAccountObj.desired_num_nodes:
                if not IS_DEPLOYED:
                    assert orgAccountObj.num_ps_cmd == 2  
                    logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
                    assert PsCmdResult.objects.count() == 2
                    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
                    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
                    assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
                    logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
                    assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label
                else:
                    assert PsCmdResult.objects.count() == 1 #  Update (min_node_cap is 1)
                    psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
                    logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
                    assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label # we use Configure (it's user friendly) but it's really SetUp)
    else:
        # assume onnTop.desired_num_nodes != orgAccountObj.desired_num_nodes
        # Note: here we just remove the entry that got the exception
        # and we do not expect the desired_num_nodes to be changed in this pass
        if IS_DEPLOYED:
            assert orgAccountObj.num_ps_cmd == 1  
            logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
            assert PsCmdResult.objects.count() == 1
            psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
            logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
            assert 'Update' in psCmdResultObjs[0].ps_cmd_summary_label
        else:
            assert orgAccountObj.num_ps_cmd == 2  
            logger.info(f"PsCmdResult.objects.count():{PsCmdResult.objects.count()}")
            assert PsCmdResult.objects.count() == 2
            psCmdResultObjs = PsCmdResult.objects.filter(org=orgAccountObj).order_by('creation_date')
            logger.info(f"[0]:{psCmdResultObjs[0].ps_cmd_summary_label}")
            assert 'Configure' in psCmdResultObjs[0].ps_cmd_summary_label
            logger.info(f"[1]:{psCmdResultObjs[1].ps_cmd_summary_label}")
            assert 'Update' in psCmdResultObjs[1].ps_cmd_summary_label     

#@pytest.mark.dev
@pytest.mark.real_ps_server
@pytest.mark.django_db
def test_get_current_version_after_setup(tasks_module,initialize_test_environ,verified_TEST_USER):
    '''
        test current version after setup
    '''
    
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.provision_env_ready = False
    clusterObj.save()
    env_ready,setup_occurred = check_provision_env_ready(orgAccountObj)
    assert env_ready == True
    assert setup_occurred == True # we set provision_env_ready to False above so we forced setup
    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp = stub.GetCurrentSetUpCfg(ps_server_pb2.GetCurrentSetUpCfgReq(name=orgAccountObj.name))
    assert rsp.setup_cfg.name == orgAccountObj.name
    assert rsp.setup_cfg.version == orgAccountObj.version
    assert rsp.setup_cfg.is_public == orgAccountObj.is_public    

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.real_ps_server
@pytest.mark.parametrize('tasks_module_to_import', ['tasks'], indirect=True)
def test_provision_env_ready(tasks_module_to_import,developer_TEST_USER,initialize_test_environ):
    '''
        This procedure will test the 'provision_env_ready' routine 
    '''
    orgAccountObj = get_test_org()
    orgAccountObj.version = 'v3'
    orgAccountObj.is_public = False
    orgAccountObj.save()
    clusterObj = Cluster.objects.get(org=orgAccountObj) # get the cluster object
    clusterObj.provision_env_ready = False # forces a SetUp to occur
    clusterObj.save()
    logger.info(f"{orgAccountObj.name} v:{orgAccountObj.version} ip:{orgAccountObj.is_public} clusterObj.provision_env_ready:{clusterObj.provision_env_ready}")
    env_ready,setup_occurred = check_provision_env_ready(orgAccountObj)
    assert env_ready == True
    assert setup_occurred  # fixture already did setup
    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp = stub.GetCurrentSetUpCfg(ps_server_pb2.GetCurrentSetUpCfgReq(name=orgAccountObj.name))
    assert rsp.setup_cfg.name == orgAccountObj.name
    assert rsp.setup_cfg.version == orgAccountObj.version
    assert rsp.setup_cfg.is_public == orgAccountObj.is_public

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_delete_onn_and_its_scheduled_job(setup_logging,client,tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'delete_onn_and_its_scheduled_job' routine
    '''
    logger = setup_logging
    jobs = log_scheduled_jobs()
    assert (len(jobs) == 3), f"jobs:{jobs}" # three cron jobs
    orgAccountObj = get_test_org()
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    logger.info(f"clusterObj.cur_version={clusterObj.cur_version} clusterObj.is_deployed={clusterObj.is_deployed}")
    orgAccountObj.destroy_when_no_nodes = False
    orgAccountObj.min_node_cap = 2
    orgAccountObj.desired_num_nodes = 2
    orgAccountObj.version = 'v3'
    orgAccountObj.save()
    now = datetime.now(timezone.utc)
    exp_tm = now+timedelta(minutes=15)
    onn,redundant,msg = get_or_create_OrgNumNodes(orgAccountObj=orgAccountObj,
                                                    user=orgAccountObj.owner,
                                                    desired_num_nodes=orgAccountObj.desired_num_nodes+1,
                                                    expire_date=exp_tm)
    assert(msg.startswith('Created'))
    assert(onn.desired_num_nodes == orgAccountObj.desired_num_nodes+1)
    assert(onn.expiration==exp_tm.replace(microsecond=0)) # verify that it is truncated to seconds
    process_state_change(orgAccountObj) # verify that it doesn't matter if this is called
    assert OrgNumNode.objects.count() == 1
    onn = OrgNumNode.objects.first()
    jobs = log_scheduled_jobs()
    assert (len(jobs) == 4)
    assert orgAccountObj.desired_num_nodes == 2 # no change
    delete_onn_and_its_scheduled_job(onn)
    jobs = get_scheduled_jobs()
    assert (len(jobs) == 3)
    assert OrgNumNode.objects.count() == 0

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_remove_PsCmdResultsWithNoExpirationAndOldCreationDate(setup_logging,client,tasks_module,initialize_test_environ):
    '''
        This procedure will test the 'remove_PsCmdResultsWithNoExpirationAndOldCreationDate' routine
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    current_time = datetime.now(timezone.utc)
    time_before = datetime.now(timezone.utc) - timedelta(days=orgAccountObj.pcqr_retention_age_in_days,minutes=1)
    logger.info(f"time_before:{time_before} current_time:{current_time.strftime(FMT)}")
    with time_machine.travel(time_before):
        logger.info(f"new time now:{datetime.now(timezone.utc).strftime(FMT)} time_before:{time_before.strftime(FMT)}")
        assert datetime.now(timezone.utc) < current_time
        assert (datetime.now(timezone.utc) - time_before) < timedelta(seconds=1)
        psCmdResultObj = PsCmdResult.objects.create(org=orgAccountObj)
        psCmdResultObj.expiration = None
        psCmdResultObj.save()
    new_current = datetime.now(timezone.utc)
    logger.info(f"new_current:{new_current.strftime(FMT)} current_time:{current_time.strftime(FMT)}")
    assert new_current >= current_time
    assert PsCmdResult.objects.count() == 1
    first = PsCmdResult.objects.first()
    logger.info(f"expiration:{first.expiration} create_date:{first.creation_date}")
    remove_PsCmdResultsWithNoExpirationAndOldCreationDate(orgAccountObj)
    assert PsCmdResult.objects.count() == 0

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_update_org_cost(setup_logging,tasks_module,initialize_test_environ):
    '''
        This procedure will test the update_org_cost routine
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    granObj = getGranChoice(granularity=GranChoice.DAY)
    assert granObj.granularity == 'DAILY'
    assert granObj.granularity == GranChoice.DAY
    assert GranChoice.DAY == 'DAILY'
    assert GranChoice.objects.count() == 3
    assert OrgCost.objects.count() == 3
    for gc in GranChoice.objects.all():
        logger.info(f"gc:{gc} gc.granularity:{gc.granularity}")
    for oc in OrgCost.objects.filter(org=orgAccountObj):
        logger.info(f"oc.gran:{oc.gran} oc.gran.granularity:{oc.gran.granularity}")
    orgCostObj,num_values_returned = update_orgCost(orgAccountObj,granObj.granularity)
    assert orgCostObj is not None # fetched data from Stubbed ps_server that has 3
    assert num_values_returned == 3

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_get_db_org_cost(setup_logging,tasks_module,initialize_test_environ):
    '''
        This procedure will test the get_db_org_cost routine
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    granObj = getGranChoice(granularity=GranChoice.DAY)
    assert granObj.granularity == 'DAILY'
    assert granObj.granularity == GranChoice.DAY
    assert GranChoice.DAY == 'DAILY'
    assert GranChoice.objects.count() == 3
    assert OrgCost.objects.count() == 3
    for gc in GranChoice.objects.all():
        logger.info(f"gc:{gc} gc.granularity:{gc.granularity}")
    for oc in OrgCost.objects.filter(org=orgAccountObj):
        logger.info(f"oc.gran:{oc.gran} oc.gran.granularity:{oc.gran.granularity}")
    got_data,orgCostObj = get_db_org_cost(granObj.granularity,orgAccountObj)
    assert orgCostObj is not None # fetched data from STUBBED ps_server, it has 3
    assert got_data
    data = {
        "name": "unit-test-org",
        "granularity": "DAILY",
        "total": 222.1645490317,
        "unit": "USD",
        "tm": [
            "2023-09-01", "2023-09-02", "2023-09-03", "2023-09-04", "2023-09-05", 
            "2023-09-06", "2023-09-07", "2023-09-08", "2023-09-09", "2023-09-10", 
            "2023-09-11", "2023-09-12", "2023-09-13", "2023-09-14", "2023-09-15", 
            "2023-09-16", "2023-09-17", "2023-09-18", "2023-09-19", "2023-09-20", 
            "2023-09-21", "2023-09-22", "2023-09-23", "2023-09-24", "2023-09-25", 
            "2023-09-26", "2023-09-27", "2023-09-28", "2023-09-29", "2023-09-30",
            "2023-10-01", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", 
            "2023-10-06", "2023-10-07", "2023-10-08", "2023-10-09", "2023-10-10", 
            "2023-10-11", "2023-10-12", "2023-10-13", "2023-10-14", "2023-10-15", 
            "2023-10-16", "2023-10-17", "2023-10-18", "2023-10-19", "2023-10-20", 
            "2023-10-21", "2023-10-22", "2023-10-23", "2023-10-24", "2023-10-25", 
            "2023-10-26", "2023-10-27", "2023-10-28", "2023-10-29", "2023-10-30", 
            "2023-10-31"
        ],
        "cost": [
            0.2538695764, 0.0, 0.2273658695, 0.0, 0.0, 
            0.0, 3.6303886334, 14.0256756802, 14.0244330885, 8.8623750766, 
            0.0, 0.0, 4.154894857, 6.8782239081, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 2.6428320146, 9.0113056544, 0.1253392361, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 3.7097725334, 5.0209568953, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.1152943085, 0.0, 
            0.0, 0.3536871076, 0.0, 0.0, 0.0, 
            0.0
        ],
        "stats": {
            "avg": 0.3043349986735617,
            "max": 18.4394250495,
            "std": 1.4515730380085299
        }
    }
    json_data = json.dumps(data)    
    oc = OrgCost.objects.get(org=orgAccountObj,gran=granObj)
    oc.ccr = json_data
    oc.save()
    got_data,orgCostObj = get_db_org_cost(granObj.granularity,orgAccountObj)
    assert orgCostObj is not None # fetched data from STUBBED ps_server, it has 3
    assert got_data
    assert orgCostObj.ccr == json_data

#@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_get_fytd_cost(setup_logging,tasks_module,initialize_test_environ):
    '''
        This procedure will test the get_fytd_cost routine
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    granObj = getGranChoice(granularity=GranChoice.DAY)
    assert granObj.granularity == 'DAILY'
    assert granObj.granularity == GranChoice.DAY
    assert GranChoice.DAY == 'DAILY'
    assert GranChoice.objects.count() == 3
    assert OrgCost.objects.count() == 3
    for gc in GranChoice.objects.all():
        logger.info(f"gc:{gc} gc.granularity:{gc.granularity}")
    for oc in OrgCost.objects.filter(org=orgAccountObj):
        logger.info(f"oc.gran:{oc.gran} oc.gran.granularity:{oc.gran.granularity}")
    fytd_cost = get_fytd_cost(orgAccountObj)
    # Stubbed ps_server is hard coded to return this: rsp_cost=[float("2.51"), float("10.80"), float("2.40")] == 15.71   
    assert fytd_cost == Decimal('15.71') 

    data = {
        "name": "unit-test-org",
        "granularity": "DAILY",
        "total": 222.1645490317,
        "unit": "USD",
        "tm": [
            "2023-09-01", "2023-09-02", "2023-09-03", "2023-09-04", "2023-09-05", 
            "2023-09-06", "2023-09-07", "2023-09-08", "2023-09-09", "2023-09-10", 
            "2023-09-11", "2023-09-12", "2023-09-13", "2023-09-14", "2023-09-15", 
            "2023-09-16", "2023-09-17", "2023-09-18", "2023-09-19", "2023-09-20", 
            "2023-09-21", "2023-09-22", "2023-09-23", "2023-09-24", "2023-09-25", 
            "2023-09-26", "2023-09-27", "2023-09-28", "2023-09-29", "2023-09-30",
            "2023-10-01", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", 
            "2023-10-06", "2023-10-07", "2023-10-08", "2023-10-09", "2023-10-10", 
            "2023-10-11", "2023-10-12", "2023-10-13", "2023-10-14", "2023-10-15", 
            "2023-10-16", "2023-10-17", "2023-10-18", "2023-10-19", "2023-10-20", 
            "2023-10-21", "2023-10-22", "2023-10-23", "2023-10-24", "2023-10-25", 
            "2023-10-26", "2023-10-27", "2023-10-28", "2023-10-29", "2023-10-30", 
            "2023-10-31"
        ],
        "cost": [
            0.2538695764, 0.0, 0.2273658695, 0.0, 0.0, 
            0.0, 3.6303886334, 14.0256756802, 14.0244330885, 8.8623750766, 
            0.0, 0.0, 4.154894857, 6.8782239081, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 2.60, 9.01, 0.12, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.0, 0.0, 
            0.0, 3.70, 5.02, 0.0, 0.0, 
            0.0, 0.0, 0.0, 0.11, 0.0, 
            0.0, 0.35, 0.0, 0.0, 0.0, 
            0.0
        ],
        "stats": {
            "avg": 0.3043349986735617,
            "max": 18.4394250495,
            "std": 1.4515730380085299
        }
    }
    rsp = ps_server_pb2.CostAndUsageRsp(name=orgAccountObj.name, 
                                        granularity=GranChoice.DAY,
                                        tm = data['tm'],
                                        cost = data['cost'],)
    rsp.ClearField('tm')
    rsp.tm.extend(data['tm'])
    rsp.ClearField('cost')
    rsp.cost.extend(data['cost'])
    oc = OrgCost.objects.get(org=orgAccountObj,gran=granObj)
    json_data = MessageToJson(rsp)
    oc.ccr =json_data
    oc.save()
    logger.info(f"oc.ccr:{oc.ccr}")
    assert oc.ccr == json_data
    with time_machine.travel(datetime(2023, 11, 1, tzinfo=timezone.utc)):
        fytd_cost = get_fytd_cost(orgAccountObj)
        assert fytd_cost == Decimal('20.91') # sum of the values after October 1st
 
@pytest.mark.dev
@pytest.mark.django_db
@pytest.mark.ps_server_stubbed
def test_debit_charges(setup_logging,tasks_module,initialize_test_environ):
    '''
        This procedure will test the debit_charges routine
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    granObj = getGranChoice(granularity=GranChoice.DAY)
    assert granObj.granularity == 'DAILY'
    assert granObj.granularity == GranChoice.DAY
    assert GranChoice.DAY == 'DAILY'
    assert GranChoice.objects.count() == 3
    assert OrgCost.objects.count() == 3
    for gc in GranChoice.objects.all():
        logger.info(f"gc:{gc} gc.granularity:{gc.granularity}")
    for oc in OrgCost.objects.filter(org=orgAccountObj):
        logger.info(f"oc.gran:{oc.gran} oc.gran.granularity:{oc.gran.granularity}")
    assert orgAccountObj.balance == Decimal('2000.00')
    time_now = datetime.now(timezone.utc)
    start_tm = time_now - timedelta(days=4)
    start_of_today = time_now.replace(hour=0, minute=0, second=0, microsecond=0)
    accrued_cost,final_tm = debit_charges(orgAccountObj,start_tm,GranChoice.DAY)
    assert accrued_cost == Decimal('15.71')
    # Stubbed ps_server is hard coded to return this: rsp_cost=[float("2.51"), float("10.80"), float("2.40")] == 15.71 
    # with relative time stamps of 1,2,3 days ago  
    assert orgAccountObj.balance == Decimal('1984.29') 
    assert final_tm == start_of_today
