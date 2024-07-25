import pytest
import unittest
from allauth.account.models import EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import send_email_confirmation
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from users.forms import OrgAccountForm
from users.models import OrgAccount,Membership,OwnerPSCmd,OrgAccount,OrgNumNode,Cluster,OrgCost,GranChoice
from users.views import add_org_cluster_orgcost
from datetime import timezone,datetime
from datetime import date, datetime, timedelta, timezone, tzinfo
import django.utils.timezone
from django.contrib.messages import get_messages
from google.protobuf.json_format import MessageToJson

from users.tasks import init_new_org_memberships,process_state_change,sort_ONN_by_nn_exp,need_destroy_for_changed_version_or_is_public,sum_of_highest_nodes_for_each_user,check_redis,set_PROVISIONING_DISABLED,get_scheduler,get_scheduled_jobs,log_scheduled_jobs,getGranChoice
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import transaction
from oauth2_provider.models import Application
from google.protobuf.json_format import MessageToDict
from google.protobuf import json_format
from django.core.cache import cache
from unittest.mock import Mock, call

from django.urls import reverse
import time_machine
import json
import logging
#from ps_web.celery import app  
import random
import string
import re
from time import sleep
from users import ps_client
import ps_server_pb2
import ps_server_pb2_grpc
from users.global_constants import *
from django_rq import get_scheduler



logger = logging.getLogger('test_console')
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d:%(funcName)s] [%(message)s]",
    datefmt="%Y-%m-%d:%H:%M:%S",
)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)
# Add handlers to logger
logger.addHandler(console_handler)


TEST_PASSWORD='A-passw0rd'
TEST_EMAIL='devtester@mail.slideruleearth.io'
TEST_USER='testuser'

OWNER_PASSWORD='A-passw0rd_owner'
OWNER_EMAIL='devtester2@mail.slideruleearth.io' 
OWNER_USER='ownertestuser'

DEV_TEST_PASSWORD='A-passw0rd_dev'
DEV_TEST_EMAIL='devtester3@mail.slideruleearth.io'
DEV_TEST_USER='devtestuser2'

TEST_ORG_NAME='test_org'

TEST_ADMIN_NODE_CAP=10
S3_BUCKET = os.environ.get("S3_BUCKET",'unit-test-bucket')
ORGS_PERMITTED_JSON_FILE = 'OrgsPermitted.json'

alphabet = string.ascii_lowercase + string.digits
def random_choice():
    return ''.join(random.choices(alphabet, k=8))

def have_same_elements(list1, list2):
    return set(list1) == set(list2)

def mock_django_email_backend(mocker):
    # Use Django's locmem email backend for testing
    test_email_backend = 'django.core.mail.backends.locmem.EmailBackend'
    mocker.patch('django_amazon_ses.EmailBackend', mail.get_connection(backend=test_email_backend))

def check_redis_for_testing(logger,log_label):
    logger.info(f"{log_label} check_redis_for_testing")
    try:
        client = cache.client.get_client()  # Get the underlying Redis client
        while not client.ping():  # Call the ping method on the Redis client
            logger.critical(f"{log_label} waiting for redis to come up...")
            sleep(1)
        logger.info(f"{log_label} redis is up")
    except Exception as e:
        logger.critical(f"{log_label} check_redis_for_testing got this exception:{str(e)}")


def check_for_scheduled_jobs(logger,log_label,expected_num_jobs,timeout=None):
    timeout = timeout or 10
    logger.info(f"{log_label} check_for_scheduled_jobs expected_num_jobs:{expected_num_jobs} timeout:{timeout}")
    while(timeout > 0):
        jobs = get_scheduled_jobs()
        if len(jobs) == expected_num_jobs:
            return True
        else:
            logger.info(f"{log_label} check_for_scheduled_jobs waiting for {expected_num_jobs} jobs to be scheduled len(jobs):{len(jobs)} == expected_num_jobs:{expected_num_jobs}")
            sleep(1)
            timeout = timeout - 1
    return False

def clear_enqueue_process_state_change(logger):
    for job,tm in get_scheduler().get_jobs(with_times=True):
        tm_aware = tm.astimezone(timezone.utc)
        logger.info(f"job.func_name:{job.func_name} job.tm:{tm_aware}")
        if job.func_name == 'users.tasks.enqueue_process_state_change':
            logger.info(f"canceling job {job.func_name} at {tm_aware}")
            get_scheduler().cancel(job.id)

def the_TEST_USER():
    return get_user_model().objects.get(username=TEST_USER)

def the_OWNER_USER():
    return get_user_model().objects.get(username=OWNER_USER)

def the_DEV_TEST_USER():
    return get_user_model().objects.get(username=DEV_TEST_USER)

def create_test_user(first_name,last_name, email, username, password, verify=None):
    new_user = get_user_model().objects.create_user(username=username,
                                                    first_name=first_name,
                                                    last_name=last_name,
                                                    email=email,
                                                    password=password)
    verify = verify or False
    if verify:
        assert verify_user(new_user)
    return new_user

def is_in_messages(response,string_to_check,logger):
    messages = list(get_messages(response.wsgi_request))
    for message in messages:
        logger.info(f"message:{message}")   
    # since we can get a 302 on success or failure lets check for the message
    retStatus = any(string_to_check in str(message) for message in messages)
    if retStatus:
        logger.info(f"retStatus:{retStatus} for:{string_to_check}")
    else:
        logger.error(f"retStatus:{retStatus} for:{string_to_check}")
    return retStatus

def log_ONN():
    # Order by org, then by owner (username), and finally by desired_num_nodes (descending)
    ordered_nodes = OrgNumNode.objects.all().order_by('org__name', 'user__username', '-desired_num_nodes')

    # Determine the maximum width needed for each column
    max_name_len = max(len(node.org.name) for node in ordered_nodes)
    max_username_len = max(len(node.user.username) for node in ordered_nodes)
    max_desired_num_nodes_len = max(len(str(node.desired_num_nodes)) for node in ordered_nodes)
    max_expiration_len = max(len(node.expiration.strftime(FMT)) for node in ordered_nodes)

    # Now, print each node with proper formatting
    for node in ordered_nodes:
        expiration_str = node.expiration.strftime(FMT) if node.expiration else 'N/A'
        logger.info(f"{node.org.name:<{max_name_len}} "
                    f"{node.user.username:<{max_username_len}} "
                    f"{node.desired_num_nodes:<{max_desired_num_nodes_len}} "
                    f"{expiration_str:<{max_expiration_len}}")
    return ordered_nodes    

def create_active_membership(the_org,the_user):
    m = Membership()
    m.user = the_user
    m.org = the_org
    m.active = True
    m.save()
    logger.info(f"created active membership for user:{the_user.username} org:{the_org.name}")
    return m

def random_test_user():
    return create_test_user(first_name="Test", last_name="User", username=TEST_USER+random_choice(), email=TEST_EMAIL, password=TEST_PASSWORD)

def create_owner_user():
    return create_test_user(first_name="Owner", last_name="TestUser", username=OWNER_USER, email=OWNER_EMAIL, password=OWNER_PASSWORD) 

def verify_user(the_user):
    logger.info(f"verify username:{the_user.username} email:{the_user.email}")
    factory = RequestFactory()
    request = factory.request()
    request.user = the_user

    # Manually add SessionMiddleware and MessageMiddleware to the request
    middleware = SessionMiddleware(lambda req: req)
    middleware.process_request(request)
    request.session.save()

    middleware = MessageMiddleware(lambda req: req)
    middleware.process_request(request)
    request.session.save()

    ndx = len(mail.outbox)
    # Send an email confirmation request
    send_email_confirmation(request, the_user)
    # Check if there's any sent email
    assert len(mail.outbox) == ndx+1, "No email has been sent."


    # Extract the confirmation URL from the email body
    email_body = mail.outbox[ndx].body
    #logger.info(f"email.body:{email_body}")
    confirmation_url = re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', email_body).group(0)
    #logger.info(f"confirmation_url:{confirmation_url}")
    # Remove the trailing slash if it exists
    if confirmation_url.endswith("/"):
        confirmation_url = confirmation_url[:-1]
    #logger.info(f"confirmation_url:{confirmation_url}")
    # Get the confirmation key from the URL
    confirmation_key = confirmation_url.split("/")[-1]
    logger.info(f"username:{the_user.username} email:{the_user.email} using confirmation key:{confirmation_key}")

    # Create and confirm the email
    email_confirmation = EmailConfirmation.objects.create(
        email_address=the_user.emailaddress_set.get(email=the_user.email),
        sent=the_user.date_joined,
        key=confirmation_key
    )
    email_confirmation.confirm(request)

    return the_user

def verify_api_user_makes_onn_ttl(client,orgAccountObj,user,password,desired_num_nodes,ttl_minutes,expected_change_ps_cmd, mock_tasks_enqueue_stubbed_out=None, mock_views_enqueue_stubbed_out=None, expected_status='QUEUED'):
    '''
    This routine tests the org-num-nodes-ttl api with a testuser with assumed password TEST_PASSWORD
    '''
    #logged_in = client.login(username=user.username, password=password)
    #assert logged_in
    response = client.post(reverse('org-token-obtain-pair'),data={'username':user.username,'password':password, 'org_name':orgAccountObj.name})
    assert(response.status_code == 200)   
    json_data = json.loads(response.content)
    logger.info(f"org-token-obtain-pair rsp:{json_data}")
    access_token = json_data['access']   
    response = verify_post_org_num_nodes_ttl(  client=client,
                                                orgAccountObj=orgAccountObj,
                                                url_args=[orgAccountObj.name,desired_num_nodes,ttl_minutes],
                                                access_token=access_token,
                                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out,
                                                expected_change_ps_cmd=expected_change_ps_cmd,
                                                expected_status=expected_status)
    return True



def create_test_org(name, 
                    org_owner, 
                    max_allowance=None, 
                    monthly_allowance=None,
                    balance=None,
                    fytd_accrued_cost=None, 
                    most_recent_charge_time=None, 
                    most_recent_credit_time=None,
                    most_recent_recon_time=None,
                    node_fixed_cost=None,
                    node_mgr_fixed_cost=None,
                    min_node_cap=None,
                    max_node_cap=None,
                    desired_num_nodes=None,
                    version=None,
                    is_public=None
                    ):
    # most_recent_recon_time is by definition later than these
    if most_recent_recon_time is not None:
        if most_recent_charge_time is not None:
            assert(most_recent_recon_time >= most_recent_charge_time)
        else:
            most_recent_charge_time = most_recent_recon_time
        if most_recent_credit_time is not None:
            assert(most_recent_recon_time >= most_recent_credit_time)
        else:
            most_recent_credit_time = most_recent_recon_time 

    if not isinstance(max_allowance, (int, float)) or max_allowance < 0:
        raise ValidationError('max_allowance must be a positive number')
    if not isinstance(monthly_allowance, (int, float)) or monthly_allowance < 0:
        raise ValidationError('monthly_allowance must be a positive number')
    if not isinstance(balance, (int, float)) or balance < 0:
        raise ValidationError('balance must be a positive number')

    if not isinstance(min_node_cap, (int)) or min_node_cap < 0:
        raise ValidationError('min_node_cap must be a positive integer')
    if not isinstance(max_node_cap, (int)) or max_node_cap < 0:
        raise ValidationError('max_node_cap must be a positive integer')
    if not isinstance(desired_num_nodes, (int)) or desired_num_nodes < 0:
        raise ValidationError('desired_num_nodes must be a positive integer')

    org_owner = org_owner or random_test_user()
    logger.info(f"create_test_org username:{org_owner.username} password:{org_owner.password}")   
    max_allowance = max_allowance or 1000
    monthly_allowance = monthly_allowance or 100
    balance = balance or monthly_allowance
    fytd_accrued_cost = fytd_accrued_cost or monthly_allowance
    most_recent_charge_time = most_recent_charge_time or django.utils.timezone.now()
    most_recent_credit_time = most_recent_credit_time or django.utils.timezone.now()
    most_recent_recon_time = most_recent_recon_time or  most_recent_charge_time
    node_fixed_cost = node_fixed_cost or 0.226
    node_mgr_fixed_cost = node_mgr_fixed_cost or 0.153
    min_node_cap = min_node_cap or 0
    max_node_cap = max_node_cap or 10
    desired_num_nodes = desired_num_nodes or 1
    version = version or 'latest'
    is_public = is_public or False
    init_mock_ps_server(name=name,num_nodes=0)

    return OrgAccount.objects.create(name=name, 
                                    owner=org_owner,
                                    max_allowance=max_allowance, 
                                    monthly_allowance=monthly_allowance,
                                    balance=balance, 
                                    fytd_accrued_cost = fytd_accrued_cost,
                                    most_recent_charge_time=most_recent_charge_time,
                                    most_recent_credit_time=most_recent_credit_time,
                                    most_recent_recon_time=most_recent_recon_time,
                                    node_fixed_cost = node_fixed_cost,
                                    node_mgr_fixed_cost = node_mgr_fixed_cost,
                                    min_node_cap = min_node_cap,
                                    max_node_cap = max_node_cap,
                                    desired_num_nodes = desired_num_nodes,
                                    version=version,
                                    is_public=is_public)
def get_test_org(name=None):
    name = name or TEST_ORG_NAME
    return OrgAccount.objects.get(name=name)

def init_test_environ(  name=None,
                        org_owner=None,
                        the_logger=None,                        
                        max_allowance=None, 
                        monthly_allowance=None,
                        balance=None,
                        fytd_accrued_cost=None, 
                        most_recent_charge_time=None, 
                        most_recent_credit_time=None,
                        most_recent_recon_time=None,
                        node_fixed_cost=None,
                        node_mgr_fixed_cost=None,
                        min_node_cap=None,
                        max_node_cap=None,
                        desired_num_nodes=None,
                        version=None,
                        is_public=None):
    
    this_logger = the_logger or logger
    name = name or 'test_org'
    org_owner = org_owner or verify_user(create_owner_user())
    this_logger.info(f"--------- org:{name} owner:{org_owner} ---------")
    monthly_allowance = monthly_allowance or 1000
    balance = balance or 2000
    fytd_accrued_cost = fytd_accrued_cost or 100
    most_recent_charge_time = most_recent_charge_time or datetime.now(timezone.utc)
    most_recent_credit_time = most_recent_credit_time or datetime.now(timezone.utc)
    most_recent_recon_time = most_recent_recon_time or datetime.now(timezone.utc)
    min_node_cap = min_node_cap or 0
    max_node_cap = max_node_cap or 10
    desired_num_nodes = desired_num_nodes or 0
    version = version or 'version_notset'
    max_allowance = max_allowance or 100
    is_public = is_public or False

    # TBD make these DDTs parameters
    min_ddt = datetime.now(timezone.utc) + timedelta(days=10)
    cur_ddt = datetime.now(timezone.utc) + timedelta(days=6)
    max_ddt = datetime.now(timezone.utc) + timedelta(days=3)


    form = OrgAccountForm(data={
        'name': name,
        'owner': org_owner, # use same as sliderule org
        'point_of_contact_name': 'test point of contact here',
        'email': OWNER_EMAIL, 
        'max_allowance':max_allowance,
        'monthly_allowance':monthly_allowance,
        'balance':balance,
        'admin_max_node_cap':TEST_ADMIN_NODE_CAP,
        'is_public':is_public})
    this_logger.info(f"form_errors:{form.errors.as_data()}")
    assert form.errors.as_data() == {}
    assert form.is_valid() 
    new_orgAccountObj,msg,emsg = add_org_cluster_orgcost(form)  # this is atomic
    new_orgAccountObj.fytd_accrued_cost = fytd_accrued_cost
    new_orgAccountObj.most_recent_charge_time= most_recent_charge_time
    new_orgAccountObj.most_recent_credit_time= most_recent_credit_time
    new_orgAccountObj.most_recent_recon_time= most_recent_recon_time
    new_orgAccountObj.min_node_cap = min_node_cap
    new_orgAccountObj.max_node_cap = max_node_cap
    new_orgAccountObj.min_ddt = min_ddt
    new_orgAccountObj.cur_ddt = cur_ddt
    new_orgAccountObj.max_ddt = max_ddt
    new_orgAccountObj.version = version
    #new_orgAccountObj.desired_num_nodes = desired_num_nodes
    new_orgAccountObj.save()
    #logger.info(f"created org uuid:{new_orgAccountObj.id}")
    #logger.info(f"{msg}")
    qs = Membership.objects.filter(org=new_orgAccountObj).filter(user=new_orgAccountObj.owner)
    for m in qs:
        this_logger.info(f"m.id:{m.id} m.user.id:{m.user.id} m.user.username:{m.user.username} m.org.name:{m.org.name} m.org.id:{m.org.id}")
    assert(qs.count() == 1)
    assert(qs[0].user==new_orgAccountObj.owner)
    app = Application.objects.create(client_id='1492'+random_choice(),user=org_owner,client_secret='1492'+random_choice(),name='test_app')
    this_logger.info("calling call_SetUp")
    assert(call_SetUp(new_orgAccountObj))
    assert(fake_sync_clusterObj_to_orgAccountObj(new_orgAccountObj))
    clusterObj = Cluster.objects.get(org=new_orgAccountObj)
    this_logger.info(f"org:{new_orgAccountObj.name} provision_env_ready:{clusterObj.provision_env_ready} clusterObj.cur_version:{clusterObj.cur_version} orgAccountObj.version:{new_orgAccountObj.version} ")       
    assert clusterObj.cur_version == new_orgAccountObj.version
    set_PROVISIONING_DISABLED('False')
    return new_orgAccountObj,new_orgAccountObj.owner


def initialize_test_org(name,
                        org_owner=None,
                        max_allowance=None, 
                        monthly_allowance=None,
                        balance=None,
                        fytd_accrued_cost=None, 
                        most_recent_charge_time=None, 
                        most_recent_credit_time=None,
                        most_recent_recon_time=None,
                        node_fixed_cost=None,
                        node_mgr_fixed_cost=None,
                        min_node_cap=None,
                        max_node_cap=None,
                        desired_num_nodes=None,
                        version=None,
                        is_public=None):
    #logger.info(f"{__name__} ... ------------------")
    min_node_cap = min_node_cap or 0
    max_node_cap = max_node_cap or 10
    desired_num_nodes = desired_num_nodes or 1
    version = version or 'latest'
    is_public = is_public or False
    test_org = create_test_org( name=name,
                                org_owner=org_owner,
                                max_allowance=max_allowance,
                                monthly_allowance=monthly_allowance,
                                balance=balance,
                                most_recent_charge_time=most_recent_charge_time,
                                most_recent_credit_time=most_recent_credit_time,
                                most_recent_recon_time=most_recent_recon_time,
                                fytd_accrued_cost=fytd_accrued_cost,
                                node_fixed_cost=node_fixed_cost,
                                node_mgr_fixed_cost=node_mgr_fixed_cost,
                                min_node_cap=min_node_cap,
                                max_node_cap=max_node_cap,
                                desired_num_nodes=desired_num_nodes,
                                version=version,
                                is_public=is_public)
    test_org.max_ddt = datetime.now(timezone.utc) + timedelta(days=3)
    test_org.cur_ddt = datetime.now(timezone.utc) + timedelta(days=5)
    test_org.min_ddt = datetime.now(timezone.utc) + timedelta(days=5)
    test_org.save() 
    init_new_org_memberships(test_org)
    qs = Membership.objects.filter(org=test_org).filter(user=test_org.owner)
    assert(qs.count() == 1)
    assert(qs[0].user==test_org.owner)
    return test_org,test_org.owner

def get_org_dict(name):
    try:
        model_org_json = serializers.serialize('json', OrgAccount.objects.filter(name=name), indent=4)
        logger.info(f"type(model_org_json):{type(model_org_json)}  model_org_json:{model_org_json}")
        model_org_d = json.loads(model_org_json)[0]['fields']
        logger.info(f"type(model_org_d):{type(model_org_d)}  model_org_d:{model_org_d}")
    except Exception as e:
        logger.info(f"name:<{name}> orgs:{OrgAccount.objects.values_list('name', flat=True)}")
        logger.exception("Caught:")
    return model_org_d,model_org_json

def get_org_cost_dict(name, gran):
    try:
        granObj = getGranChoice(gran)
        orgAccountObj = OrgAccount.objects.get(name=name)
        model_org_cost_json = serializers.serialize('json', OrgCost.objects.filter(org=orgAccountObj, gran=granObj) , indent=4)
        logger.info(f"type(model_org_cost_json):{type(model_org_cost_json)}  model_org_cost_json:{model_org_cost_json}")
        model_org_cost_d = json.loads(model_org_cost_json)[0]['fields']
        logger.info(f"type(model_org_d):{type(model_org_cost_d)}  model_org_cost_d:{model_org_cost_d}")
    except Exception as e:
        logger.info(f"name:<{orgAccountObj.name}> orgs:{OrgAccount.objects.values_list('name', flat=True)}")
        logger.exception("Caught:")
        model_org_cost_d = None
        model_org_cost_json = None
    return model_org_cost_d,model_org_cost_json

def dump_org_account(name,banner=None,level=None):
    org_dict,org_json = get_org_dict(name)
    fake_now = datetime.now(timezone.utc)
    banner = banner or f"************** {fake_now} **************"
    bottom =           "***************************************************"
    if level == 'critical':
        logger.critical(f"{banner}\n{org_json}\n{bottom}")
    elif level == 'info':
        logger.info(f"{banner}\n{org_json}\n{bottom}")
    return org_dict

def dump_org_cost(name, gran, banner=None,level=None):
    org_dict,org_json = get_org_cost_dict(name=name, gran=gran)
    fake_now = datetime.now(timezone.utc)
    banner = banner or f"************** {fake_now} **************"
    bottom =           "***************************************************"
    if level == 'critical':
        logger.critical(f"{banner}\n{org_json}\n{bottom}")
    elif level == 'info':
        logger.info(f"{banner}\n{org_json}\n{bottom}")
    return org_dict
   

def pytest_approx(val1,val2):
    return pytest.approx(val1,abs=1e-9)==pytest.approx(val2,abs=1e-9)


def getOrgAccountObjCnts(orgAccountObj):
    logger.info(f"getOrgAccountObjCnts orgAccountObj:{orgAccountObj.name} num_owner_ps_cmd:{orgAccountObj.num_owner_ps_cmd} num_ps_cmd:{orgAccountObj.num_ps_cmd} num_setup_cmd:{orgAccountObj.num_setup_cmd} num_ps_cmd_successful:{orgAccountObj.num_ps_cmd_successful} num_setup_cmd_successful:{orgAccountObj.num_setup_cmd_successful}")
    return  orgAccountObj.num_owner_ps_cmd, orgAccountObj.num_ps_cmd, orgAccountObj.num_setup_cmd, orgAccountObj.num_ps_cmd_successful, orgAccountObj.num_setup_cmd_successful,


def getObjectCnts():
    return OwnerPSCmd.objects.count(),OrgNumNode.objects.count()


def call_process_state_change(orgAccountObj,expected_change_ps_cmd,start_cnt,current_cnt):
    '''
    This routine will call process_state_change for the given orgAccountObj 
    based on the start_cnt and current_cnt
    essentially mimicing the calls to process_state_change that would be made 
    when the mocked enqueue_process_state_change function was called
    '''
    orgAccountObj.refresh_from_db()
    logger.info(f"call_process_state_change orgAccountObj:{orgAccountObj.name} expected_change_ps_cmd:{expected_change_ps_cmd} start_cnt:{start_cnt} current_cnt:{current_cnt}")   
    num_iters = current_cnt - start_cnt
    num_idle=0
    task_idle = True
    for _ in range(num_iters):
        idle, loop_count = process_state_change(orgAccountObj.name)
        if idle:
            num_idle = num_idle + 1
        else:
            task_idle = False
    if num_iters == 0:
        logger.info(f"NO CALLS to process_state_change --> num_iters:{num_iters} num_idle:{num_idle} task_idle:{task_idle}")
    else:
        assert(task_idle==(expected_change_ps_cmd==0)),f"task_idle:{task_idle} expected_change_ps_cmd:{expected_change_ps_cmd}"
        logger.info(f"num_iters:{num_iters} num_idle:{num_idle} task_idle:{task_idle}")
    assert(task_idle==(expected_change_ps_cmd==0)),f"task_idle:{task_idle} expected_change_ps_cmd:{expected_change_ps_cmd}"
    return num_iters,num_idle,task_idle

def verify_post_org_num_nodes_ttl( client,
                                    orgAccountObj,
                                    url_args,
                                    access_token,
                                    expected_change_ps_cmd,
                                    expected_status,
                                    data=None,
                                    mock_tasks_enqueue_stubbed_out=None,
                                    mock_views_enqueue_stubbed_out=None,
                                    new_time=None,
                                    expected_html_status=None,
                                    expected_change_OrgNumNode=None):
    '''
    This routine will test calling the view API --> post-org-num-nodes-ttl  
    with the given url args or parameters/data. 
    It assumes the enqueue_process_state_change is stubbed out in views and tasks
    '''
    if new_time is None:
        #logger.critical(f"new_time is None ")
        sleep(1)
        new_time = datetime.now(timezone.utc)
    logger.info(f"verify_post_org_num_nodes_ttl url_args:{url_args} access_token:{access_token} data:{data} loop_count:{orgAccountObj.loop_count} expected_change_ps_cmd:{expected_change_ps_cmd} expected_status:{expected_status} expected_html_status:{expected_html_status}")
    logger.info(f"using new_time: {new_time.strftime(FMT) if new_time is not None else 'None'}")
    # backwards compatibility
    expected_num_onn_change = 0
    expected_html_status = expected_html_status or 200
    logger.info(f"url_args:{url_args}")
    url = reverse('post-org-num-nodes-ttl',args=url_args)
    logger.info(f"using url:{url}")
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    s_OwnerPSCmd_cnt = OwnerPSCmd.objects.count()
    s_OrgNumNode_cnt = OrgNumNode.objects.count()
    s_orgAccountObj_num_owner_ps_cmd, s_orgAccountObj_num_ps_cmd, s_orgAccountObj_num_setup_cmd, s_orgAccountObj_num_ps_cmd_successful, s_orgAccountObj_num_setup_cmd_successful  = getOrgAccountObjCnts(orgAccountObj)
    logger.info(f"using s_OrgNumNode_cnt:{s_OrgNumNode_cnt} s_OwnerPSCmd_cnt:{s_OwnerPSCmd_cnt} s_orgAccountObj_num_owner_ps_cmd:{s_orgAccountObj_num_owner_ps_cmd} s_orgAccountObj_num_ps_cmd:{s_orgAccountObj_num_ps_cmd} s_orgAccountObj_num_setup_cmd:{s_orgAccountObj_num_setup_cmd} s_orgAccountObj_num_ps_cmd_successful:{s_orgAccountObj_num_ps_cmd_successful} s_orgAccountObj_num_setup_cmd_successful:{s_orgAccountObj_num_setup_cmd_successful}")
    headers = {
        'Authorization': f"Bearer {access_token}",
        'Accept': 'application/json'  # Specify JSON response
    }
    logger.info(f"old time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
    with time_machine.travel(new_time,tick=True):
        logger.info(f"new time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            start_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
        if access_token is not None:
            assert(expected_status=='QUEUED' or expected_status == 'REDUNDANT' or expected_status == 'FAILED') 
            logger.info(f"url:{url} data:{data}")
            response = client.post(url,headers=headers)
            assert(response.status_code == expected_html_status) 
            json_data = json.loads(response.content)
            assert(json_data['status'] == expected_status)   
            assert(json_data['msg']!='')   
            assert(json_data['error_msg']=='')
            if json_data['status'] == 'QUEUED':
                expected_num_onn_change = 1
        else:
            if data is not None:
                logger.info(f"url:{url} data:{data}")
                response = client.post(url,data=data, HTTP_ACCEPT='application/json')
                assert((response.status_code == expected_html_status) or (response.status_code == 302)) 
                if expected_status != 'FAILED':
                    expected_num_onn_change = 1 # if we get here we expect a change
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this       
        assert(OwnerPSCmd.objects.count() == s_OwnerPSCmd_cnt) # url was an onn api not an owner ps cmd, so no change
        assert(OrgNumNode.objects.count() == (s_OrgNumNode_cnt + expected_num_onn_change))
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd) # no change just queued
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd) # no change just queued
        num_iters = 0
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            current_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
            num_iters,_,_ = call_process_state_change(orgAccountObj=orgAccountObj,expected_change_ps_cmd=expected_change_ps_cmd,start_cnt=start_cnt,current_cnt=current_cnt)
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        assert(orgAccountObj.num_ps_cmd == (s_orgAccountObj_num_ps_cmd + expected_change_ps_cmd)) # processed an update ps_cmd
        if num_iters==0:
            assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        else:
            if expected_change_OrgNumNode:
                logger.info(f"expected_org_account_num_onn_change:{expected_change_OrgNumNode} orgAccountObj.min_node_cap:{orgAccountObj.min_node_cap} orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")
                assert(OrgNumNode.objects.count()==(s_OrgNumNode_cnt + expected_change_OrgNumNode))
    return orgAccountObj.loop_count,response

def verify_put_org_num_nodes(  client,
                                orgAccountObj,
                                url_args,
                                access_token,
                                expected_change_ps_cmd,
                                expected_status,
                                data=None,
                                mock_tasks_enqueue_stubbed_out=None,
                                mock_views_enqueue_stubbed_out=None,
                                new_time=None,
                                expected_html_status=None):
    '''
    This routine will test calling the view ( API --> put-org-num-nodes ) 
    with the given url args or parameters/data. 
    It assumes the enqueue_process_state_change is stubbed out in both tasks and views
    '''
    if new_time is None:
        #logger.critical(f"new_time is None ")
        sleep(1)
        new_time = datetime.now(timezone.utc)
    logger.info(f"verify_put_org_num_nodes  url_args:{url_args} access_token:{access_token} data:{data} loop_count:{orgAccountObj.loop_count} expected_change_ps_cmd:{expected_change_ps_cmd} expected_status:{expected_status} expected_html_status:{expected_html_status}")
    logger.info(f"using new_time: {new_time.strftime(FMT) if new_time is not None else 'None'}")
    expected_num_onn_change = 0
    # backwards compatibility
    expected_html_status = expected_html_status or 200
    logger.info(f"url_args:{url_args}")
    url = reverse('put-org-num-nodes',args=url_args)
    logger.info(f"using url:{url}")
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    s_OwnerPSCmd_cnt = OwnerPSCmd.objects.count()
    s_OrgNumNode_cnt = OrgNumNode.objects.count()
    s_orgAccountObj_num_owner_ps_cmd, s_orgAccountObj_num_ps_cmd, s_orgAccountObj_num_setup_cmd, s_orgAccountObj_num_ps_cmd_successful, s_orgAccountObj_num_setup_cmd_successful  = getOrgAccountObjCnts(orgAccountObj)
    logger.info(f"using s_OrgNumNode_cnt:{s_OrgNumNode_cnt} s_OwnerPSCmd_cnt:{s_OwnerPSCmd_cnt} s_orgAccountObj_num_owner_ps_cmd:{s_orgAccountObj_num_owner_ps_cmd} s_orgAccountObj_num_ps_cmd:{s_orgAccountObj_num_ps_cmd} s_orgAccountObj_num_setup_cmd:{s_orgAccountObj_num_setup_cmd} s_orgAccountObj_num_ps_cmd_successful:{s_orgAccountObj_num_ps_cmd_successful} s_orgAccountObj_num_setup_cmd_successful:{s_orgAccountObj_num_setup_cmd_successful}")
    headers = {
        'Authorization': f"Bearer {access_token}",
        'Accept': 'application/json'  # Specify JSON response
    }
    logger.info(f"old time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
    with time_machine.travel(new_time,tick=True):
        logger.info(f"new time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
        start_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
        if access_token is not None:
            assert(expected_status=='QUEUED' or expected_status == 'REDUNDANT' or expected_status == 'FAILED') 
            logger.info(f"url:{url} data:{data}")
            response = client.put(url,headers=headers)
            assert(response.status_code == expected_html_status) 
            json_data = json.loads(response.content)
            assert(json_data['status'] == expected_status)   
            assert(json_data['msg']!='')   
            assert(json_data['error_msg']=='')
            if json_data['status'] == 'QUEUED':
                expected_num_onn_change = 1
        else:
            if data is not None:
                logger.info(f"url:{url} data:{data}")
                response = client.post(url,data=data, HTTP_ACCEPT='application/json')
                assert((response.status_code == expected_html_status) or (response.status_code == 302)) 
                if expected_status != 'FAILED':
                    expected_num_onn_change = 1 # if we get here we expect a change
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this       
        assert(OwnerPSCmd.objects.count() == s_OwnerPSCmd_cnt) # url was an onn api not an owner ps cmd, so no change
        assert(OrgNumNode.objects.count() == (s_OrgNumNode_cnt + expected_num_onn_change))
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd) # no change just queued
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd) # no change just queued
        num_iters = 0
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            current_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
            num_iters,_,_ = call_process_state_change(orgAccountObj=orgAccountObj,expected_change_ps_cmd=expected_change_ps_cmd,start_cnt=start_cnt,current_cnt=current_cnt)
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        assert(orgAccountObj.num_ps_cmd == (s_orgAccountObj_num_ps_cmd + expected_change_ps_cmd)) # processed an update ps_cmd
        if num_iters==0:
            assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        else:
            logger.info(f"orgAccountObj.min_node_cap:{orgAccountObj.min_node_cap} orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")
    return orgAccountObj.loop_count,response


def verify_org_manage_cluster_onn( client,
                                    orgAccountObj,
                                    url_args,
                                    data,
                                    expected_change_ps_cmd,
                                    expected_status,
                                    mock_tasks_enqueue_stubbed_out=None,
                                    mock_views_enqueue_stubbed_out=None,
                                    new_time=None,
                                    expected_html_status=None):
    '''
    This routine will test calling the view ( WEB --> org-manage-cluster ) 
    with the given url args or parameters/data. While it assumes the 
    '''
    if new_time is None:
        #logger.critical(f"new_time is None ")
        sleep(1)
        new_time = datetime.now(timezone.utc)
    logger.info(f"verify_org_manage_cluster_onn url_args:{url_args} data:{data} loop_count:{orgAccountObj.loop_count} expected_change_ps_cmd:{expected_change_ps_cmd} expected_status:{expected_status} expected_html_status:{expected_html_status}")
    logger.info(f"using new_time: {new_time.strftime(FMT) if new_time is not None else 'None'}")
    expected_num_onn_change = 0
    # backwards compatibility
    expected_html_status = expected_html_status or 200
    logger.info(f"url_args:{url_args}")
    url = reverse('org-manage-cluster',args=url_args)
    logger.info(f"using url:{url}")
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    s_OwnerPSCmd_cnt = OwnerPSCmd.objects.count()
    s_OrgNumNode_cnt = OrgNumNode.objects.count()
    s_orgAccountObj_num_owner_ps_cmd, s_orgAccountObj_num_ps_cmd, s_orgAccountObj_num_setup_cmd, s_orgAccountObj_num_ps_cmd_successful, s_orgAccountObj_num_setup_cmd_successful  = getOrgAccountObjCnts(orgAccountObj)
    logger.info(f"using s_OrgNumNode_cnt:{s_OrgNumNode_cnt} s_OwnerPSCmd_cnt:{s_OwnerPSCmd_cnt} s_orgAccountObj_num_owner_ps_cmd:{s_orgAccountObj_num_owner_ps_cmd} s_orgAccountObj_num_ps_cmd:{s_orgAccountObj_num_ps_cmd} s_orgAccountObj_num_setup_cmd:{s_orgAccountObj_num_setup_cmd} s_orgAccountObj_num_ps_cmd_successful:{s_orgAccountObj_num_ps_cmd_successful} s_orgAccountObj_num_setup_cmd_successful:{s_orgAccountObj_num_setup_cmd_successful}")

    logger.info(f"old time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
    with time_machine.travel(new_time,tick=True):
        logger.info(f"new time now:{datetime.now(timezone.utc).strftime(FMT)} new_time:{new_time.strftime(FMT)}")
        start_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
        logger.info(f"url:{url} data:{data}")
        response = client.post(url,data=data, HTTP_ACCEPT='application/json')
        assert((response.status_code == expected_html_status) or (response.status_code == 302)) 
        if expected_status != 'FAILED':
            expected_num_onn_change = 1 # if we get here we expect a change
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this       
        assert(OwnerPSCmd.objects.count() == s_OwnerPSCmd_cnt) # url was an onn api not an owner ps cmd, so no change
        assert(OrgNumNode.objects.count() == (s_OrgNumNode_cnt + expected_num_onn_change))
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd) # no change just queued
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd) # no change just queued
        num_iters = 0
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            current_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
            num_iters,_,_ = call_process_state_change(orgAccountObj=orgAccountObj,expected_change_ps_cmd=expected_change_ps_cmd,start_cnt=start_cnt,current_cnt=current_cnt)
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        assert(orgAccountObj.num_ps_cmd == (s_orgAccountObj_num_ps_cmd + expected_change_ps_cmd)) # processed an update ps_cmd
        if (num_iters)==0:
            assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)
        else:
            logger.info(f"orgAccountObj.min_node_cap:{orgAccountObj.min_node_cap} orgAccountObj.desired_num_nodes:{orgAccountObj.desired_num_nodes}")

    return response


def do_owner_ps_cmd(client,
                    orgAccountObj,
                    new_time,
                    view_name,
                    url_args,
                    data,
                    mock_tasks_enqueue_stubbed_out,
                    mock_views_enqueue_stubbed_out):
    url = reverse(view_name,args=url_args)
    logger.info(f"using url:{url}")
    EXPECTED_PS_CMD_PROCESSED = 1
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    s_OwnerPSCmd_cnt,s_OrgNumNode_cnt = getObjectCnts()
    s_orgAccountObj_num_owner_ps_cmd, s_orgAccountObj_num_ps_cmd, s_orgAccountObj_num_setup_cmd, s_orgAccountObj_num_ps_cmd_successful, s_orgAccountObj_num_setup_cmd_successful  = getOrgAccountObjCnts(orgAccountObj)
    logger.info(f"using new_time:{new_time.strftime(FMT)}") 
    with time_machine.travel(new_time,tick=True):
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            start_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
        response = client.post(url,data=data, HTTP_ACCEPT='application/json')
        logger.info(f"response.status_code:{response.status_code}")
        assert((response.status_code == 200) or (response.status_code == 302))
        # logger.info(f"dir(response):{dir(response)}")
        # logger.info(f"Response status code: {response.status_code}")
        # logger.info(f"Response content: {response.content}")
        # logger.info(f"Response headers: {response.headers}")        # json_data = json.loads(response.content)
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        assert(OwnerPSCmd.objects.count() == s_OwnerPSCmd_cnt + 1) # url was an owner ps_cmd always increments
        assert(OrgNumNode.objects.count() == (s_OrgNumNode_cnt))
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd) # only changes after we do a process_state_change 
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd) # only changes after we do a process_state_change 
        if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
            current_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
            call_process_state_change(orgAccountObj=orgAccountObj,expected_change_ps_cmd=1,start_cnt=start_cnt,current_cnt=current_cnt)

        orgAccountObj.refresh_from_db() 
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd + EXPECTED_PS_CMD_PROCESSED) # only changes if we did a process_state_change else no change just queued
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd + EXPECTED_PS_CMD_PROCESSED) # only changes if we did a process_state_change else no change just queued
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd + EXPECTED_PS_CMD_PROCESSED)


def verify_org_configure(  client,
                            orgAccountObj,
                            data,
                            expected_change_ps_cmd=2,
                            expected_change_setup_cmd=1,
                            mock_tasks_enqueue_stubbed_out=None,
                            mock_views_enqueue_stubbed_out=None,
                            new_time=None):
    url = reverse('org-configure',args=[orgAccountObj.id])
    logger.info(f"using url:{url}")
    orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    s_OwnerPSCmd_cnt,s_OrgNumNode_cnt = getObjectCnts()
    #num_owner_ps_cmd, num_ps_cmd, num_setup_cmd, num_ps_cmd_successful, num_setup_cmd_successful,
    s_orgAccountObj_num_owner_ps_cmd, s_orgAccountObj_num_ps_cmd, s_orgAccountObj_num_setup_cmd, s_orgAccountObj_num_ps_cmd_successful, s_orgAccountObj_num_setup_cmd_successful  = getOrgAccountObjCnts(orgAccountObj)
    if new_time is None:
        tm = datetime.now(timezone.utc)
    else:
        tm = new_time
    logger.info(f"using time:{tm.strftime(FMT)}") 
    with time_machine.travel(tm,tick=True):
        if mock_tasks_enqueue_stubbed_out and mock_views_enqueue_stubbed_out:
            start_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
            response = client.post(url,data=data, HTTP_ACCEPT='application/json')
            orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
            logger.info(f"response.status_code:{response.status_code}")
            assert((response.status_code == 200) or (response.status_code == 302))
            logger.info(f" mock_tasks_enqueue_stubbed_out.call_count:{mock_tasks_enqueue_stubbed_out.call_count} mock_views_enqueue_stubbed_out.call_count:{mock_views_enqueue_stubbed_out.call_count} expected_change_ps_cmd:{expected_change_ps_cmd} ")
            if mock_tasks_enqueue_stubbed_out is not None and mock_views_enqueue_stubbed_out is not None:
                current_cnt = mock_tasks_enqueue_stubbed_out.call_count + mock_views_enqueue_stubbed_out.call_count
                call_process_state_change(orgAccountObj=orgAccountObj,expected_change_ps_cmd=expected_change_ps_cmd,start_cnt=start_cnt,current_cnt=current_cnt)
        # logger.info(f"dir(response):{dir(response)}")
        # logger.info(f"Response status code: {response.status_code}")
        # logger.info(f"Response content: {response.content}")
        # logger.info(f"Response headers: {response.headers}")        
        # # json_data = json.loads(response.content)
        clusterObj.refresh_from_db()    # The client.post above updated the DB so we need this
        orgAccountObj.refresh_from_db() # The client.post above updated the DB so we need this
        logger.info(f"DONE processing org-configure --- checking counts")
        getOrgAccountObjCnts(orgAccountObj) # log them
        assert(OwnerPSCmd.objects.count() == s_OwnerPSCmd_cnt) 
        assert(OrgNumNode.objects.count() == (s_OrgNumNode_cnt))
        assert(orgAccountObj.num_owner_ps_cmd == s_orgAccountObj_num_owner_ps_cmd)  
        assert(orgAccountObj.num_ps_cmd_successful == s_orgAccountObj_num_ps_cmd_successful+expected_change_ps_cmd)
        assert(orgAccountObj.num_setup_cmd == s_orgAccountObj_num_setup_cmd+expected_change_setup_cmd)  
        assert(orgAccountObj.num_setup_cmd_successful == s_orgAccountObj_num_setup_cmd_successful+expected_change_setup_cmd) 
        assert(orgAccountObj.num_ps_cmd == s_orgAccountObj_num_ps_cmd + expected_change_ps_cmd) 
    return True

def verify_owner_ps_Destroy_cmd(client,
                                orgAccountObj,
                                new_time,
                                mock_tasks_enqueue_stubbed_out,
                                mock_views_enqueue_stubbed_out):
    return do_owner_ps_cmd(client=client,
                                orgAccountObj=orgAccountObj,
                                new_time=new_time,
                                view_name='org-destroy-cluster',
                                url_args=[orgAccountObj.id],
                                data=None,
                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

def verify_owner_ps_Refresh_cmd(client,
                                orgAccountObj,
                                new_time,
                                mock_tasks_enqueue_stubbed_out,
                                mock_views_enqueue_stubbed_out):
    return do_owner_ps_cmd(client=client,
                                orgAccountObj=orgAccountObj,
                                new_time=new_time,
                                view_name='org-refresh-cluster',
                                url_args=[orgAccountObj.id],
                                data=None,
                                mock_tasks_enqueue_stubbed_out=mock_tasks_enqueue_stubbed_out,
                                mock_views_enqueue_stubbed_out=mock_views_enqueue_stubbed_out)

def verify_schedule_process_state_change(mock_schedule_process_state_change,
                                         min_tm,
                                         max_tm):
    # Set up the scheduler
    scheduler = get_scheduler()

    call_args_list = mock_schedule_process_state_change.call_args_list
    # 'call_args_list' is a list of tuples, where each tuple contains the positional arguments and keyword arguments for a call.
    for call_args, call_kwargs in call_args_list:
        logger.info(f"Positional Arguments:{call_args} len:{len(call_args)}")
        logger.info(f"Keyword Arguments:{call_kwargs} len:{len(call_kwargs)}")
        logger.info(f"call_args[0]:{call_args[0]} >= min_tm:{min_tm} and call_args[0]:{call_args[0]} <= max_tm:{max_tm}")
        assert (call_args[0]) >= min_tm
        assert (call_args[0]) <= max_tm+timedelta(seconds=1)

def init_mock_ps_server(name=None,num_nodes=None):
    name = name or TEST_ORG_NAME
    num_nodes = num_nodes or 0
    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp = stub.Init(ps_server_pb2.InitReq(name=name,num_nodes=num_nodes))
        assert(rsp.success)
        assert(rsp.error_msg=='')

def verify_rsp_gen(rrsp_gen, name, ps_cmd,  logger):
    '''
    process the response generator
    '''
    done = False
    cnt = 0
    exception_cnt = 0
    stop_exception_cnt = 0
    ps_error_cnt = 0
    rrsp = None
    got_rsp_done = False
    stdout = ''
    stderr = ''
    while(not done):
        try:
            cnt += 1
            rrsp = next(rrsp_gen)  # grab the next one and process it
            logger.info(f"name:{name} ps_cmd:{ps_cmd} CNT:{cnt} {json_format.MessageToJson(rrsp, always_print_fields_with_no_presence=True)}")
            logger.info(f'rrsp.cli.valid: {rrsp.cli.valid}')
            logger.info(f'rrsp.cli.updating: {rrsp.cli.updating}')
            logger.info(f'rrsp.cli.cmd_args: {rrsp.cli.cmd_args}')
            logger.info(f'rrsp.cli.stdout: {rrsp.cli.stdout}')
            logger.info(f'rrsp.cli.stderr: {rrsp.cli.stderr}')
            stdout = rrsp.cli.stdout
            stderr = rrsp.cli.stderr
            assert rrsp.ps_cmd == ps_cmd
            assert rrsp.name == name
            assert hasattr(rrsp.cli, 'stderr')
            assert hasattr(rrsp.cli, 'stdout')
            if not rrsp.ps_server_error:
                assert rrsp.cli.valid
            if rrsp.done:
                done = True
                logger.info(f"rrsp.done:{rrsp.done}")
        except StopIteration:
            done = True
            stop_exception_cnt += 1
            logger.error(f'StopIteration at cnt:{cnt}? Should be able to read until get rrsp.done:True')    
        except Exception as ex:
            done = True
            exception_cnt += 1
            logger.error(f'Exception at cnt:{cnt} e:{ex} ')
        finally:
            logger.info(f'cnt:{cnt} exception_cnt:{exception_cnt} stop_exception_cnt:{stop_exception_cnt}')

            if rrsp == None:
                done = True
                logger.error(f"No rrsp at cnt:{cnt}")
            elif rrsp.ps_server_error:
                done = True
                ps_error_cnt += 1
                logger.error(f"rrsp.error_msg:{rrsp.error_msg}")
            elif rrsp.done:
                got_rsp_done = True
    return cnt, got_rsp_done, stop_exception_cnt, exception_cnt, ps_error_cnt, stdout, stderr

def call_SetUp(orgAccountObj):
    assert(orgAccountObj != None)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.provision_env_ready = False
    clusterObj.save()
    setup_req = ps_server_pb2.SetUpReq(name=orgAccountObj.name,version=orgAccountObj.version,is_public=orgAccountObj.is_public,now=datetime.now(timezone.utc).strftime(FMT),spot_allocation_strategy=orgAccountObj.spot_allocation_strategy,spot_max_price=orgAccountObj.spot_max_price)
    logger.info(f"SetUp setup_req:{setup_req}")
    rsp = None
    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rrsp_gen = stub.SetUp(setup_req)
        cnt, got_rsp_done, stop_exception_cnt, exception_cnt, ps_error_cnt, stdout, stderr = verify_rsp_gen(rrsp_gen,orgAccountObj.name,'SetUp',logger)
        logger.info(f"SetUp cnt:{cnt} got_rsp_done:{got_rsp_done} stop_exception_cnt:{stop_exception_cnt} exception_cnt:{exception_cnt} ps_error_cnt:{ps_error_cnt} stdout:{stdout} stderr:{stderr}")   
        assert(got_rsp_done == True)
        assert(stop_exception_cnt == 0)
        assert(exception_cnt == 0)
        assert(ps_error_cnt == 0)
        assert(f"{setup_req.name}" in stdout)
        assert(stderr == '')
        logger.info(f"SetUp stdout:{stdout}")
        rsp = stub.GetCurrentSetUpCfg(ps_server_pb2.GetCurrentSetUpCfgReq(name=orgAccountObj.name))
        logger.info(f"GetCurrentSetUpCfg rsp:{rsp}")
    assert(rsp is not None)
    assert(rsp.setup_cfg.name == setup_req.name)
    assert(rsp.setup_cfg.version == setup_req.version)
    assert(rsp.setup_cfg.is_public == setup_req.is_public)
    assert(rsp.setup_cfg.now == setup_req.now)
    assert(rsp.setup_cfg.spot_allocation_strategy == setup_req.spot_allocation_strategy)
    assert(rsp.setup_cfg.spot_max_price == setup_req.spot_max_price)
    return True

def fake_sync_clusterObj_to_orgAccountObj(orgAccountObj):
    '''
        put in quiescent state
    '''
    logger.info(f"fake_sync_clusterObj_to_orgAccountObj orgAccountObj:{orgAccountObj.name}")
    with ps_client.create_client_channel("control") as channel:
        stub = ps_server_pb2_grpc.ControlStub(channel)
        rsp = stub.GetCurrentSetUpCfg(ps_server_pb2.GetCurrentSetUpCfgReq(name=orgAccountObj.name))
    assert rsp.setup_cfg.name == orgAccountObj.name
    assert rsp.setup_cfg.version == orgAccountObj.version
    assert rsp.setup_cfg.is_public == orgAccountObj.is_public    
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    clusterObj.provision_env_ready = True
    clusterObj.is_public = orgAccountObj.is_public
    clusterObj.cur_version = orgAccountObj.version
    clusterObj.save()
    return True

def upload_json_string_to_s3(s3_client, s3_bucket, json_string, s3_key):
    """
    Uploads a JSON string to an S3 bucket.

    Args:
        s3_client: boto3 s3 client instance
        s3_bucket: the name of the s3 bucket
        json_string: the JSON string you wish to upload
        s3_key: the key (path including filename) in the s3 bucket where the data should be stored
    """

    try:
        # Convert JSON string to bytes
        json_bytes = json_string.encode('utf-8')

        # Upload the JSON bytes to S3 with content type set as JSON
        s3_client.put_object(Bucket=s3_bucket, Key=s3_key, Body=json_bytes, ContentType='application/json')
        
        logger.info(f"Successfully uploaded JSON to {s3_key} in bucket {s3_bucket}")

    except Exception as e:
        logger.error(f"Failed to upload JSON to {s3_key} in bucket {s3_bucket}. Error: {e}")

def verify_upload(s3_client, s3_bucket, s3_key, original_json_string):
    """
    Verifies the uploaded JSON string in an S3 bucket.

    Args:
        s3_client: boto3 s3 client instance
        s3_bucket: the name of the s3 bucket
        s3_key: the key (path including filename) in the s3 bucket
        original_json_string: the original JSON string you uploaded

    Returns:
        bool: True if the uploaded JSON matches the original, False otherwise
    """

    try:
        response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        uploaded_json_string = response['Body'].read().decode('utf-8')
        
        if original_json_string == uploaded_json_string:
            logger.info(f"Verification successful for {s3_key} in bucket {s3_bucket}")
            return True
        else:
            logger.warning(f"Verification failed for {s3_key} in bucket {s3_bucket}")
            return False

    except Exception as e:
        logger.error(f"Failed to verify JSON at {s3_key} in bucket {s3_bucket}. Error: {e}")
        return False
    
def set_ObjCost(orgAccountObj,gran,data):
    rsp = ps_server_pb2.CostAndUsageRsp(name=orgAccountObj.name, 
                                        granularity=gran,
                                        tm = data['tm'],
                                        cost = data['cost'],)
    rsp.ClearField('tm')
    rsp.tm.extend(data['tm'])
    rsp.ClearField('cost')
    rsp.cost.extend(data['cost'])
    oc = OrgCost.objects.get(org=orgAccountObj,gran=gran)
    json_data = MessageToJson(rsp)
    oc.ccr =json_data
    # set cost_refresh_time to now so it does not get updated for being stale
    oc.cost_refresh_time = datetime.now(timezone.utc)
    oc.save()
    logger.info(f"oc.ccr:{oc.ccr}")
    assert oc.ccr == json_data

def extend_ObjCost(orgAccountObj, gran, tm_data, cost_data):
    oc = OrgCost.objects.get(org=orgAccountObj, gran=gran)

    # Deserialize the JSON string into a Python dictionary
    ccr_dict = json.loads(oc.ccr) if oc.ccr else {}

    # Extend the 'tm' and 'cost' lists in the dictionary
    ccr_dict.setdefault('tm', []).extend(tm_data)
    ccr_dict.setdefault('cost', []).extend(cost_data)

    # Serialize the dictionary back into a JSON string
    oc.ccr = json.dumps(ccr_dict)

    # Set the cost refresh time and save the object
    oc.cost_refresh_time = datetime.now(timezone.utc)
    oc.save()

    # Logging
    logger.info(f"oc.ccr:{oc.ccr}")
