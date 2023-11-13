import json
import logging
import os
import socket
from redis import Redis
from rq import Queue, Worker
from rq.job import Job
from datetime import datetime
import time

from dateutil import tz
import environ
from pathlib import Path
from django.conf import settings
from datetime import date, datetime, timedelta, timezone, tzinfo
import subprocess

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from .models import Cluster, Membership, OrgAccount, OrgCost, User, OrgNumNode, PsCmdResult
import requests
from api.tokens import OrgRefreshToken
from api.serializers import MembershipSerializer
from rest_framework_simplejwt.settings import api_settings
from .tasks import get_ps_versions, enqueue_process_state_change, getGranChoice, set_PROVISIONING_DISABLED, get_PROVISIONING_DISABLED, check_redis,hourly_processing,refresh_token_maintenance,get_scheduler,schedule_process_state_change,log_scheduled_jobs
from oauth2_provider.models import AbstractApplication
from users.global_constants import *
from django_rq import get_queue
from django.core.cache import cache

LOG = logging.getLogger('django')
VERSIONS = []
FULL_FMT = "%Y-%m-%dT%H:%M:%SZ"
DAY_FMT = "%Y-%m-%d"
MONTH_FMT = "%Y-%m"



def paginateObjs(request, objs, results):
    page = request.GET.get('page')
    paginator = Paginator(objs, results)

    try:
        objs = paginator.page(page)
    except PageNotAnInteger:
        page = 1
        objs = paginator.page(page)
    except EmptyPage:
        page = paginator.num_pages
        objs = paginator.page(page)

    leftIndex = (int(page) - 4)

    if leftIndex < 1:
        leftIndex = 1

    rightIndex = (int(page) + 5)

    if rightIndex > paginator.num_pages:
        rightIndex = paginator.num_pages + 1

    custom_range = range(leftIndex, rightIndex)

    return custom_range, objs


def searchOrgAccounts(request):
    search_query = ''

    if request.GET.get('search_query'):
        search_query = request.GET.get('search_query')

    objs = OrgAccount.objects.distinct().filter(
        Q(name__icontains=search_query)
    )

    return objs, search_query


def searchMemberships(request):
    search_query = ''

    if request.GET.get('search_query'):
        search_query = request.GET.get('search_query')

    objs = Membership.objects.distinct().filter(
        Q(owner__icontains=search_query)
    )

    return objs, search_query

def get_db_org_cost(gran, orgAccountObj):
    granObj = getGranChoice(granularity=gran)
    LOG.info("%s %s", orgAccountObj.name,granObj.granularity)
    try:
        orgCost_qs0 = OrgCost.objects.filter(org=orgAccountObj)
        # LOG.info(repr(orgCost_qs0))
        # LOG.info(orgCost_qs0[0].org.id)
        # LOG.info(orgCost_qs0[0].org.name)
        # LOG.info(orgCost_qs0[0].tm)
        # LOG.info(orgCost_qs0[0].gran)
        # LOG.info(granObj.granularity)
        orgCostObj = orgCost_qs0.get(gran=granObj.granularity)
        #LOG.info(repr(orgCostObj))
        return True, orgCostObj
    except ObjectDoesNotExist as e:
        emsg = orgAccountObj.name + " " + gran+" report does not exist?"
        LOG.error(emsg)
        return False, None
    except Exception as e:
        emsg = orgAccountObj.name + " " + gran+" report does not exist?"
        LOG.exception(emsg)
        return False, None


def check_MFA_code(mfa_code,orgAccountObj):
    return (mfa_code == orgAccountObj.mfa_code) # TBD add two factor device stuff

 
def testit():
    try:
        LOG.info(datetime.now().astimezone().tzinfo)
        LOG.info(datetime.now())
        LOG.info(datetime.now(tz=datetime.now().astimezone().tzinfo))
        LOG.info(datetime.now(tz=timezone.utc))
    except Exception as e:
        LOG.error(f"Caught an exception: {e}")       

#####################################################################



def getConsoleText(orgAccountObj, rrsp):
    console_text = ''
    has_error = False
    if(rrsp.cli.valid):
        if(rrsp.cli.cmd_args != ''):
            console_text += rrsp.cli.cmd_args
        if(rrsp.cli.stdout != ''):
            console_text += rrsp.cli.stdout
        if(rrsp.cli.stderr != ''):
            console_text += rrsp.cli.stderr
    if(rrsp.ps_server_error):
        LOG.error("Error in server:\n %s", rrsp.error_msg)
        has_error = True
    return has_error, console_text

def get_new_tokens(org):
    #LOG.info(org.name)
    refresh     = OrgRefreshToken.for_user(org.owner,org.name)
    #LOG.info(str(refresh))
    this_org    = OrgAccount.objects.get(name=org)
    # this next line will throw and exception if membership does not exist
    membership  = Membership.objects.filter(org=this_org).get(user=org.owner)
    serializer  = MembershipSerializer(membership, many=False)
    #LOG.info(serializer.data['active'])
    if not serializer.data['active']:
        LOG.warning("Membership exists but user not an active member?")
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'refresh_lifetime': str(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        'access_lifetime': str(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
    }

                
def create_worker(worker_name,queue_name):
    hostname = socket.gethostname()
    LOG.info(f"hostname:{hostname}")
    LOG.info(f"creating worker {worker_name}")
    # Create an two default workers for each org. 
    SHELL_CMD=f"python manage.py rqworker {queue_name}".split(" ")
    LOG.info(f"subprocess--> {SHELL_CMD}")
    subprocess.Popen(SHELL_CMD)

def init_redis_queues():
    LOG.critical("environ DEBUG:%s",os.environ.get("DEBUG"))
    LOG.critical("environ DOCKER_TAG:%s",os.environ.get("DOCKER_TAG"))
    LOG.critical("environ GIT_VERSION:%s",os.environ.get("GIT_VERSION"))
    LOG.critical(f"environ PS_WEB_LOG_LEVEL:{os.environ.get('PS_WEB_LOG_LEVEL')}")
    LOG.critical(f"DOMAIN:{os.environ.get('DOMAIN')} {type(os.environ.get('DOMAIN'))}")
    LOG.critical(f"REDIS_HOST:{os.environ.get('REDIS_HOST')} {type(os.environ.get('REDIS_HOST'))}")
    LOG.critical(f"REDIS_PORT:{os.environ.get('REDIS_PORT')} {type(os.environ.get('REDIS_PORT'))}")
    LOG.critical(f"REDIS_DB:{os.environ.get('REDIS_DB')} {type(os.environ.get('REDIS_DB'))}")
    
    f = open('requirements.freeze.txt')
    LOG.info(f"{f.read()}")

    hostname = socket.gethostname()
    LOG.info(f"hostname:{hostname}")
    domain = os.environ.get("DOMAIN")
    if 'localhost' in domain:
        LOG.info("localhost in domain")
    check_redis(log_label="init_redis_queues")
    set_PROVISIONING_DISABLED('False')
    LOG.info(f"get_PROVISIONING_DISABLED:{get_PROVISIONING_DISABLED()}")

    log_scheduled_jobs()
    # uses the default queue
    SHELL_CMD=f"python manage.py rqworker".split(" ")
    LOG.info(f"subprocess--> {SHELL_CMD}")
    subprocess.Popen(SHELL_CMD)


    # Create the RQ get_scheduler(). It uses the defined cached connection

    get_scheduler().cron(
        cron_string="30 * * * *",   # A cron string (e.g. "0 0 * * 0")
        func=hourly_processing,     # Function to be queued
        repeat=None,                # Repeat this number of times (None means repeat forever)
        result_ttl=3600,             # Specify how long (in seconds) successful jobs and their results are kept. Defaults to -1 (forever)
    )

    get_scheduler().cron(
        cron_string="15 * * * *",       # A cron string (e.g. "0 0 * * 0")
        func=refresh_token_maintenance, # Function to be queued
        repeat=None,                    # Repeat this number of times (None means repeat forever)
        result_ttl=3600,                 # Specify how long (in seconds) successful jobs and their results are kept. Defaults to -1 (forever)
    )
    LOG.info("Running the RQ scheduler")
    # uses the default queue
    SHELL_CMD = f"python manage.py rqscheduler".split(" ")
    LOG.info(f"subprocess--> {SHELL_CMD}")
    subprocess.Popen(SHELL_CMD)

    orgs_qs = OrgAccount.objects.all()
    LOG.info("orgs_qs:%s", repr(orgs_qs))
    for orgAccountObj in orgs_qs:
        try:
            if orgAccountObj.name == 'uninitialized':
                LOG.error(f"Ignoring uninitialized OrgAccount.id:{OrgAccount.id}")
            else:
                orgAccountObj.loop_count = 0 # reset this but not the others
                orgAccountObj.num_ps_cmd = 0
                orgAccountObj.num_ps_cmd_successful = 0
                orgAccountObj.num_owner_ps_cmd = 0
                orgAccountObj.save(update_fields=['loop_count','num_ps_cmd','num_ps_cmd_successful','num_owner_ps_cmd'])
                loop_count = orgAccountObj.loop_count
                clusterObj = Cluster.objects.get(org=orgAccountObj)
                LOG.info(f"Setting provision_env_ready to False to force initialization for {orgAccountObj.name} at loop_count:{orgAccountObj.loop_count} num_ps_cmd:{orgAccountObj.num_ps_cmd_successful}/{orgAccountObj.num_ps_cmd}")
                clusterObj.provision_env_ready = False # this forces a SetUp 
                clusterObj.save(update_fields=['provision_env_ready'])
                enqueue_process_state_change(orgAccountObj.name)
        except Exception as ex:
            LOG.exception(f"Caught an exception creating queues for {orgAccountObj.name}: {str(ex)}")

    num_default_workers = os.environ.get("NUM_DEFAULT_WORKERS",5)
    for i in range(int(num_default_workers)):
        create_worker(f"default_worker_{i}",'default')

    num_sched_workers = os.environ.get("NUM_SCHED_WORKERS",5)
    for i in range(int(num_sched_workers)):
        create_worker(f"sched_worker_{i}",'scheduled')

    num_cmd_workers = os.environ.get("NUM_CMD_WORKERS",5)
    for i in range(int(num_cmd_workers)):
        create_worker(f"cmd_worker_{i}",'cmd')



    orgs_qs = OrgAccount.objects.all()
    LOG.info("orgs_qs:%s", repr(orgs_qs))
    for orgAccountObj in orgs_qs:
        LOG.info(f"Clearing provisioning_suspended for {orgAccountObj.name}")
        orgAccountObj.provisioning_suspended = False
        orgAccountObj.save(update_fields=['provisioning_suspended'])
        now =  datetime.now(timezone.utc)
        expired_cnt = 0
        for onn in OrgNumNode.objects.filter(org=orgAccountObj).order_by('expiration'):
            LOG.info(f"onn.expiration:{onn.expiration} tm(now):{now}")
            now = datetime.now(timezone.utc)
            if(onn.expiration > now):
                LOG.info(f"{orgAccountObj.name} {onn.expiration}")
                schedule_process_state_change(onn.expiration,orgAccountObj)
            else:
                expired_cnt = expired_cnt+1
        if expired_cnt > 0:
            tm = now+timedelta(seconds=1)
            LOG.info(f"expired_cnt:{expired_cnt} {orgAccountObj.name} {tm} (one second in future)")
            schedule_process_state_change(tm,orgAccountObj)

    log_scheduled_jobs()
    LOG.info("Finished init_redis_queues")

def disable_provisioning(user,req_msg):
    LOG.critical(f"{req_msg}")
    error_msg=''
    disable_msg=''
    rsp_msg=''
    if user_in_one_of_these_groups(user,groups=['PS_Developer']):
        try:
            if get_PROVISIONING_DISABLED():
                rsp_msg = f"User {user.username} attempted to disable provisioning but it was already disabled"
                LOG.warning(rsp_msg)
            else:
                set_PROVISIONING_DISABLED('True')
                disable_msg = f"User:{user.username} has disabled provisioning!"
                LOG.critical(disable_msg)
                orgs_qs = OrgAccount.objects.all()
                LOG.info("orgs_qs:%s", repr(orgs_qs))
                tmp_msg_hdr = 'Setting provisioning_suspended to True for the following orgs:\n'
                tmp_msg_body = ''
                for orgAccountObj in orgs_qs:
                    if orgAccountObj.name == 'uninitialized':
                        error_msg = f"Ignoring uninitialized OrgAccount.id:{OrgAccount.id}"
                        LOG.error(error_msg)
                    else:
                        orgAccountObj.provisioning_suspended = True
                        orgAccountObj.save(update_fields=['provisioning_suspended'])  
                        tmp_msg_body += f" {orgAccountObj.name}"
                if tmp_msg_body:
                    disable_msg += tmp_msg_hdr + tmp_msg_body
                    LOG.critical(disable_msg)
        except Exception as ex:
            error_msg = f"Caught an exception: {ex}"    
            LOG.exception(f"{error_msg}")
    else:
        LOG.warning(f"User {user.username} attempted to disable provisioning")
        error_msg = f"User {user.username} is not a Authorized to disable provisioning"
    return error_msg, disable_msg, rsp_msg

def get_ps_server_versions():
    '''
        This will call the ps_server and get GIT and sw versions then set env variable to use by views.py
    '''
    PS_SERVER_DOCKER_TAG="unknown"
    PS_SERVER_GIT_VERSION="unknown"
    try:
        #LOG.info(f"{os.environ}")
        EFILE=os.path.join('/tmp', '.ps_server_versions') # temporary file to store env vars
        open(file=EFILE,mode='w').write(str(get_ps_versions()))
        environ.Env.read_env(env_file=EFILE)
        PS_SERVER_DOCKER_TAG = os.environ.get("PS_SERVER_DOCKER_TAG")
        PS_SERVER_GIT_VERSION = os.environ.get("PS_SERVER_GIT_VERSION")
        LOG.info("environ PS_SERVER_DOCKER_TAG:%s",PS_SERVER_DOCKER_TAG)
        LOG.info("environ PS_SERVER_GIT_VERSION:%s",PS_SERVER_GIT_VERSION)
    except Exception as e:
        PS_SERVER_DOCKER_TAG ="unknown"
        PS_SERVER_GIT_VERSION = "unknown"
        LOG.exception("caught exception:")
    #LOG.info(f"{os.environ}")
    return PS_SERVER_DOCKER_TAG,PS_SERVER_GIT_VERSION

def get_ps_server_versions_from_env():
    '''
        This will call the ps_server and get GIT and sw versions then set env variable to use by views.py
    '''
    PS_SERVER_DOCKER_TAG="unknown"
    PS_SERVER_GIT_VERSION="unknown"
    EFILE=os.path.join('/tmp', '.ps_server_versions') # temporary file to store env vars
    try:
        environ.Env.read_env(env_file=EFILE)
        PS_SERVER_DOCKER_TAG = os.environ.get("PS_SERVER_DOCKER_TAG",'unknown')
        PS_SERVER_GIT_VERSION = os.environ.get("PS_SERVER_GIT_VERSION",'unknown')
        #LOG.info("environ PS_SERVER_DOCKER_TAG:%s",PS_SERVER_DOCKER_TAG)
        #LOG.info("environ PS_SERVER_GIT_VERSION:%s",PS_SERVER_GIT_VERSION)
    except FileNotFoundError:
        LOG.info(f"{EFILE} does not exist;  calling ps_server to get versions")
        try:
            # This should only happen once after the web server is started. 
            # The file is fetched in get_ps_server_versions() if it does not exist
            get_ps_server_versions()            
        except Exception as e:
            LOG.exception("caught exception:")
            raise
    except Exception as e:
        LOG.exception("caught exception:")

    #LOG.info(f"{os.environ}")
    return PS_SERVER_DOCKER_TAG,PS_SERVER_GIT_VERSION

def get_memberships(request):
    membershipObjs = Membership.objects.filter(user=request.user,active=True)
    memberships = []
    for m in membershipObjs:
        if m.org is not None:
            memberships.append(m.org.name)
    return memberships

def user_in_one_of_these_groups(user,groups):
    for group in groups:
        if user.groups.filter(name=group).exists():
            return True
    return False

def has_admin_privilege(user,orgAccountObj):
    has_privilege = user_in_one_of_these_groups(user,[f'{orgAccountObj.name}_Admin','PS_Developer']) or (user == orgAccountObj.owner)
    LOG.info(f"has_admin_privilege: {has_privilege} user:{user} orgAccountObj.owner:{orgAccountObj.owner} orgAccountObj.name:{orgAccountObj.name}")
    return has_privilege

def next_month_first_day():
    # Calculate the beginning of the next month
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month_first_day = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_first_day = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return next_month_first_day
   
