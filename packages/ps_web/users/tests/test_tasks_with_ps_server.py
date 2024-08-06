import unittest
import pytest
from django.urls import reverse,resolve

from users.tests.global_test import GlobalTestCase
from users.tasks import get_current_cost_report,get_versions_for_org
from datetime import timezone,datetime
from datetime import date, datetime, timedelta, timezone, tzinfo
from users.tests.utilities_for_unit_tests import init_test_environ,verify_rsp_gen,call_SetUp,upload_json_string_to_s3,verify_upload,S3_BUCKET,ORGS_PERMITTED_JSON_FILE,have_same_elements,DEV_TEST_USER,DEV_TEST_PASSWORD,is_in_messages
from django.test import tag
import ps_server_pb2
import ps_server_pb2_grpc
from users import ps_client
from users.models import Cluster,OrgAccount
import time
from users.global_constants import *
import logging
logger = logging.getLogger('django')
from users.utils import FULL_FMT
from users.utils import DAY_FMT
from users.utils import MONTH_FMT
from users.tests.utilities_for_unit_tests import init_test_environ,get_test_org,OWNER_USER,OWNER_EMAIL,OWNER_PASSWORD,random_test_user

class TasksTestWithPSServer(GlobalTestCase):
    '''
    These tests use the ps-server and are run from build-and-deploy
    '''
    def setUp(self):
        #logger.info(f"{__name__}({self}) ... ------------------")
        return super().setUp()

    def tearDown(self):
        #logger.info(f"{__name__}({self}) ... ------------------")
        return super().tearDown()   

    # This will only be run if it is explicitly called
    @pytest.mark.cost
    @pytest.mark.real_ps_server
    @tag('cost')
    def testadhoc_get_org_cost_report_org_sliderule(self):
        '''
            This procedure will incur some small costs 
            https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
        '''
        orgAccountObj,owner = init_test_environ("sliderule",
                                                org_owner=None,
                                                max_allowance=20000, 
                                                monthly_allowance=1000,
                                                balance=2000,
                                                fytd_accrued_cost=100, 
                                                most_recent_charge_time=datetime.now(timezone.utc), 
                                                most_recent_credit_time=datetime.now(timezone.utc),
                                                most_recent_recon_time=datetime.now(timezone.utc))
        time_now = datetime.now(timezone.utc)

        ccr,rsp = get_current_cost_report(orgAccountObj.name,'HOURLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        time.sleep(1) # ce is rate limited
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'DAILY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        time.sleep(1) # ce is rate limited
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'MONTHLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)

    # This will only be run if it is explicitly called
    @pytest.mark.cost
    @pytest.mark.real_ps_server
    @tag('cost')
    def testadhoc_get_org_cost_report_org_developers(self):
        '''
            This procedure will incur some small costs 
            https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
        '''
        time_now = datetime.now(timezone.utc)
        orgAccountObj,owner = init_test_environ("developers",
                                                org_owner=None,
                                                max_allowance=20000, 
                                                monthly_allowance=1000,
                                                balance=2000,
                                                fytd_accrued_cost=100, 
                                                most_recent_charge_time=time_now, 
                                                most_recent_credit_time=time_now,
                                                most_recent_recon_time=time_now)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'HOURLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'DAILY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'MONTHLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)


    @pytest.mark.cost
    @pytest.mark.real_ps_server
    @tag('cost')
    def test_get_org_cost_report_org_uofmdtest(self):
        '''
            This procedure will incur some small costs 
            https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
        '''
        time_now = datetime.now(timezone.utc)
        orgAccountObj,owner = init_test_environ("UofMDTest",
                                                org_owner=None,
                                                max_allowance=20000, 
                                                monthly_allowance=1000,
                                                balance=2000,
                                                fytd_accrued_cost=100, 
                                                most_recent_charge_time=time_now, 
                                                most_recent_credit_time=time_now,
                                                most_recent_recon_time=time_now)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'HOURLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'DAILY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        ccr,rsp = get_current_cost_report(orgAccountObj.name,'MONTHLY',time_now)
        #logger.info(f"ccr:{ccr}")
        #logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)

# -------- pytests -----
#@pytest.mark.dev
#@pytest.mark.real_ps_server
@pytest.mark.django_db
def test_SetUp(initialize_test_environ,setup_logging):
    '''
        This tests against the real ps-server
    '''
    logger = setup_logging
    orgAccountObj = get_test_org()
    assert(call_SetUp(orgAccountObj))

@pytest.mark.dev
@pytest.mark.real_ps_server
@pytest.mark.django_db
def test_org_account_cfg_versions(caplog,client,s3,test_name,mock_email_backend,initialize_test_environ):
    org_account_id = get_test_org().id
    orgAccountObj = OrgAccount.objects.get(id=org_account_id)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    assert OrgAccount.objects.count() == 1
    org_account_id = get_test_org().id
    orgAccountObj = OrgAccount.objects.get(id=org_account_id)
    assert(orgAccountObj.version == 'latest') 
    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    upload_json_string_to_s3(s3_client=s3,
                             s3_bucket=S3_BUCKET,
                             s3_key=os.path.join('prov-sys','cluster_tf_versions','latest',ORGS_PERMITTED_JSON_FILE),
                             json_string=f'["{test_name}"]') # test_name is unit-test-org
    assert verify_upload(s3_client=s3,
                         s3_bucket=S3_BUCKET,
                         s3_key=os.path.join('prov-sys','cluster_tf_versions','latest',ORGS_PERMITTED_JSON_FILE),
                         original_json_string=f'["{test_name}"]')                     
    versions_for_org = get_versions_for_org(name='unit-test-private')
    logger.info(f'versions_for_org:{versions_for_org}')
    all_versions = get_versions_for_org(name='') # a blank org here means all versions
    logger.info(f'all_versions:{all_versions}')
    assert(not have_same_elements(versions_for_org,all_versions))
    assert ('latest' in all_versions)
    assert ('latest' not in versions_for_org) ## excluded because it is not in permitted_orgs.json
    assert ('v3' in all_versions)
    assert ('v3' in versions_for_org)
    assert ('unstable' in versions_for_org)
    assert ('unstable' in all_versions)

    # get the url
    url = reverse('org-configure', args=[org_account_id])
    # send the GET request
    response = client.get(url)
    # refresh the OrgAccount object
    orgAccountObj = OrgAccount.objects.get(id=org_account_id)
    assert response.status_code == 200 or response.status_code == 302
    # since we can get a 302 on success or failure lets check for the message
    assert(is_in_messages(response,"cfg updated successfully",logger))


@pytest.mark.dev
@pytest.mark.real_ps_server
@pytest.mark.django_db
def test_asg_cfgs(caplog,client,s3,test_name,mock_email_backend,initialize_test_environ,localstack_setup):
    org_account_id = get_test_org().id
    orgAccountObj = OrgAccount.objects.get(id=org_account_id)
    assert OrgAccount.objects.count() == 1
    org_account_id = get_test_org().id
    orgAccountObj = OrgAccount.objects.get(id=org_account_id)
    assert(orgAccountObj.version == 'latest') 
    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    upload_json_string_to_s3(s3_client=s3,
                             s3_bucket=S3_BUCKET,
                             s3_key=os.path.join('prov-sys','cluster_tf_versions','latest',ORGS_PERMITTED_JSON_FILE),
                             json_string=f'["{test_name}"]') # test_name is unit-test-org
    assert verify_upload(s3_client=s3,
                         s3_bucket=S3_BUCKET,
                         s3_key=os.path.join('prov-sys','cluster_tf_versions','latest',ORGS_PERMITTED_JSON_FILE),
                         original_json_string=f'["{test_name}"]')                     
    versions_for_org = get_versions_for_org(name='unit-test-private')
    logger.info(f'versions_for_org:{versions_for_org}')


@pytest.mark.real_ps_server
@pytest.mark.ps_disable
@pytest.mark.django_db
def test_ps_web_view_disable_provisioning_success(caplog,client,s3,test_name,mock_email_backend,initialize_test_environ,developer_TEST_USER):
    assert(client.login(username=DEV_TEST_USER, password=DEV_TEST_PASSWORD))
    url = reverse('disable-provisioning')
    response = client.put(url)
    assert (response.status_code == 200 or response.status_code == 302)

#@pytest.mark.dev
@pytest.mark.real_ps_server
@pytest.mark.django_db
def test_ps_web_view_disable_provisioning_failure_NOT_developer(caplog,client,s3,test_name,mock_email_backend,initialize_test_environ,developer_TEST_USER):
    assert(client.login(username=OWNER_USER, password=OWNER_PASSWORD))
    url = reverse('browse')
    response = client.get(url)
    assert response.status_code == 200
    url = reverse('disable-provisioning')
    response = client.put(url)
    logger.info(f"Response Status Code: {response.status_code}")
    logger.info(f"Response Content: {response.content.decode('utf-8')}")
    logger.info(f"Response Headers: {response.headers}")
    if hasattr(response, 'context'):
        if response.context is not None:
            for context in response.context:
                if isinstance(context, dict):  # Ensure it's a dictionary before calling items()
                    for key, value in context.items():
                        logger.info(f"Context Key: {key}, Value: {value}")
    assert (response.status_code == 400 or response.status_code == 302)
    # since we can get a 302 on success or failure lets check for the message
    assert(is_in_messages(response,"is not a Authorized to disable provisioning",logger))
