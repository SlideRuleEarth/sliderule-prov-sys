import json
import logging
import os
import socket
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
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
from .tasks import get_ps_versions, get_org_queue_name_str, loop_iter, getGranChoice, set_PROVISIONING_DISABLED, get_PROVISIONING_DISABLED, check_redis,hourly_processing,refresh_token_maintenance
from oauth2_provider.models import AbstractApplication
from users.global_constants import *
from django_rq import get_queue,get_worker

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

# def create_org_queue(orgAccountObj):
#     hostname = socket.gethostname()
#     LOG.info(f"hostname:{hostname}")
#     qn = get_org_queue_name_str(orgAccountObj.name)
#     LOG.info(f"creating queue {qn}")
#     SHELL_CMD=f"celery -A ps_web worker -n {orgAccountObj.name}@{hostname} -l error -E -Q {qn} --concurrency=1".split(" ")
#     LOG.info(f"subprocess--> {SHELL_CMD}")
#     return subprocess.Popen(SHELL_CMD)

# init_celery is run from docker-entrypoint.sh using Django manage.py custom command
# def init_celery():
#     LOG.critical("environ DEBUG:%s",os.environ.get("DEBUG"))
#     LOG.critical("environ DOCKER_TAG:%s",os.environ.get("DOCKER_TAG"))
#     LOG.critical("environ GIT_VERSION:%s",os.environ.get("GIT_VERSION"))
#     LOG.critical(f"environ PS_WEB_LOG_LEVEL:{os.environ.get('PS_WEB_LOG_LEVEL')}")
#     LOG.critical(f"DOMAIN:{os.environ.get('DOMAIN')} {type(os.environ.get('DOMAIN'))}")

#     f = open('requirements.freeze.txt')
#     LOG.info(f"{f.read()}")

#     hostname = socket.gethostname()
#     LOG.info(f"hostname:{hostname}")
#     domain = os.environ.get("DOMAIN")
#     check_redis(log_label="init_celery")
#     set_PROVISIONING_DISABLED('False')
#     LOG.info(f"get_PROVISIONING_DISABLED:{get_PROVISIONING_DISABLED()}")

#     if 'localhost' in domain: 
#         SHELL_CMD=f"celery -A ps_web flower --url_prefix=flower".split(" ")
#         LOG.info(f"subprocess--> {SHELL_CMD}")
#         subprocess.Popen(SHELL_CMD)

#     SHELL_CMD=f"celery -A ps_web worker -n default@{hostname} -l error -E -Q default".split(" ")
#     LOG.info(f"subprocess--> {SHELL_CMD}")
#     subprocess.Popen(SHELL_CMD)

#     SHELL_CMD = f"celery -A ps_web beat -l error --scheduler django_celery_beat.schedulers:DatabaseScheduler".split(" ")
#     LOG.info(f"subprocess--> {SHELL_CMD}")
#     subprocess.Popen(SHELL_CMD)

#     orgs_qs = OrgAccount.objects.all()
#     LOG.info("orgs_qs:%s", repr(orgs_qs))
#     for orgAccountObj in orgs_qs:
#         try:
#             if orgAccountObj.name == 'uninitialized':
#                 LOG.error(f"Ignoring uninitialized OrgAccount.id:{OrgAccount.id}")
#             else:
#                 p = create_org_queue(orgAccountObj)
#                 orgAccountObj.loop_count = 0 # reset this but not the others
#                 orgAccountObj.num_ps_cmd = 0
#                 orgAccountObj.num_ps_cmd_successful = 0
#                 orgAccountObj.num_owner_ps_cmd = 0
#                 orgAccountObj.num_onn = 0
#                 orgAccountObj.save(update_fields=['loop_count','num_ps_cmd','num_ps_cmd_successful','num_owner_ps_cmd','num_onn'])
#                 loop_count = orgAccountObj.loop_count
#                 LOG.info(f"Entering forever loop for {orgAccountObj.name} at loop_count:{orgAccountObj.loop_count} num_ps_cmd:{orgAccountObj.num_ps_cmd_successful}/{orgAccountObj.num_ps_cmd} num_onn:{orgAccountObj.num_onn}")
#                 clusterObj = Cluster.objects.get(org=orgAccountObj)
#                 clusterObj.provision_env_ready = False # this forces a SetUp 
#                 clusterObj.save(update_fields=['provision_env_ready'])
#                 LOG.info(f"Setting provision_env_ready to False to force initialization for {orgAccountObj.name} at loop_count:{orgAccountObj.loop_count} num_ps_cmd:{orgAccountObj.num_ps_cmd_successful}/{orgAccountObj.num_ps_cmd} num_onn:{orgAccountObj.num_onn}")
#                 forever_loop_main_task.apply_async((orgAccountObj.name,loop_count),queue=get_org_queue_name(orgAccountObj))
#         except Exception as e:
#             LOG.error(f"Caught an exception creating queues: {e}")
#         LOG.info(f"forked subprocess--> {SHELL_CMD}")


def get_redis_host():
    return os.environ.get("REDIS_HOST", "redis")
def get_redis_port():
    return os.environ.get("REDIS_PORT", "6379")
def get_redis_db():
    return os.environ.get("REDIS_DB", "0")

def log_job_status(job):
    # Get the job's status
    status = job.get_status()
    
    # Log and handle different statuses
    if status == 'finished':
        LOG.info("Job completed successfully!")
    elif status == 'failed':
        LOG.error("Job failed!")
    elif status == 'started':
        LOG.info("Job has started...")
    elif status == 'queued':
        LOG.info("Job is queued.")
    elif status == 'deferred':
        LOG.warning("Job is deferred.")
    else:
        LOG.warning("Job has an unknown status: %s" % status)
            

def schedule_forever(q, func, exit_func, args=None, kwargs=None, polling_interval=None):
    '''
    Schedule a job to run repeatedly forever, monitoring its status and handling it accordingly.
    '''
    polling_interval = polling_interval or 0.5
    args = args or []
    kwargs = kwargs or {}
    check_redis(log_label=f"schedule_forever name:{q.name}")
    while not exit_func():
        try:
            job = q.enqueue(func=func, args=args, kwargs=kwargs)
            last_status = None
            # Monitor the job status and log/handle accordingly
            while True:  
                status = job.get_status()
                if status != last_status:
                    log_job_status(job)
                last_status = status                
                if status in ['finished', 'failed']:
                    break  # Break the loop once we reach a terminal status                
                time.sleep(polling_interval)                
        except Exception as e:
            LOG.error(f"Caught an exception: {e}")
            break
    LOG.critical(f"Exiting schedule_forever name:{q.name}")

def create_org_queue(orgAccountObj):
    hostname = socket.gethostname()
    LOG.info(f"hostname:{hostname}")
    qn = get_org_queue_name_str(orgAccountObj.name)
    LOG.info(f"creating queue {qn}")
    # Create the RQ queue. It uses the defined cached connection
    return get_queue(name=orgAccountObj.name)

def create_org_worker(orgAccountObj):
    hostname = socket.gethostname()
    LOG.info(f"hostname:{hostname}")
    # Create the RQ worker. 
    return get_worker(queue=get_queue(name=orgAccountObj.name),name=orgAccountObj.name)

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
    check_redis(log_label="init_queues")
    set_PROVISIONING_DISABLED('False')
    LOG.info(f"get_PROVISIONING_DISABLED:{get_PROVISIONING_DISABLED()}")
    # uses the default queue
    SHELL_CMD=f"python manage.py rqworker".split(" ")
    LOG.info(f"subprocess--> {SHELL_CMD}")
    subprocess.Popen(SHELL_CMD)


    # Create the RQ scheduler. It uses the defined cached connection
    LOG.info("Creating RQ scheduler")
    default_queue = get_queue('default')
    scheduler = Scheduler(queue=default_queue, connection=default_queue.connection)

    scheduler.cron(
        cron_string="30 * * * *",   # A cron string (e.g. "0 0 * * 0")
        func=hourly_processing,     # Function to be queued
        repeat=None,                # Repeat this number of times (None means repeat forever)
        result_ttl=300,             # Specify how long (in seconds) successful jobs and their results are kept. Defaults to -1 (forever)
        ttl=200,                    # Specifies the maximum queued time (in seconds) before it's discarded. Defaults to None (infinite TTL).
    )

    scheduler.cron(
        cron_string="15 * * * *",       # A cron string (e.g. "0 0 * * 0")
        func=refresh_token_maintenance, # Function to be queued
        repeat=None,                    # Repeat this number of times (None means repeat forever)
        result_ttl=300,                 # Specify how long (in seconds) successful jobs and their results are kept. Defaults to -1 (forever)
        ttl=200,                        # Specifies the maximum queued time (in seconds) before it's discarded. Defaults to None (infinite TTL).
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
                q = create_org_queue(orgAccountObj)
                orgAccountObj.loop_count = 0 # reset this but not the others
                orgAccountObj.num_ps_cmd = 0
                orgAccountObj.num_ps_cmd_successful = 0
                orgAccountObj.num_owner_ps_cmd = 0
                orgAccountObj.num_onn = 0
                orgAccountObj.save(update_fields=['loop_count','num_ps_cmd','num_ps_cmd_successful','num_owner_ps_cmd','num_onn'])
                loop_count = orgAccountObj.loop_count
                LOG.info(f"Entering forever loop for {orgAccountObj.name} at loop_count:{orgAccountObj.loop_count} num_ps_cmd:{orgAccountObj.num_ps_cmd_successful}/{orgAccountObj.num_ps_cmd} num_onn:{orgAccountObj.num_onn}")
                clusterObj = Cluster.objects.get(org=orgAccountObj)
                clusterObj.provision_env_ready = False # this forces a SetUp 
                clusterObj.save(update_fields=['provision_env_ready'])
                LOG.info(f"Setting provision_env_ready to False to force initialization for {orgAccountObj.name} at loop_count:{orgAccountObj.loop_count} num_ps_cmd:{orgAccountObj.num_ps_cmd_successful}/{orgAccountObj.num_ps_cmd} num_onn:{orgAccountObj.num_onn}")
                schedule_forever(q, func=loop_iter, exit_func=get_PROVISIONING_DISABLED, kwargs={'name':orgAccountObj.name,'loop_count':loop_count})
        except Exception as e:
            LOG.error(f"Caught an exception creating queues: {e}")
        LOG.info(f"forked subprocess--> {SHELL_CMD}")

def disable_provisioning(user,req_msg):
    error_msg=''
    disable_msg=''
    rsp_msg=''
    if user_in_one_of_these_groups(user,groups=['PS_Developer']):
        try:
            if get_PROVISIONING_DISABLED():
                LOG.warning(f"User {user.username} attempted to disable provisioning but it was already disabled")
                rsp_msg = f"User {user.username} attempted to disable provisioning but it was already disabled"
            else:
                set_PROVISIONING_DISABLED('True')
                disable_msg = f"User:{user.username} has disabled provisioning!"
                LOG.critical(disable_msg)
        except Exception as e:
            error_msg = f"Caught Exception in requested shutdown"
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
   
