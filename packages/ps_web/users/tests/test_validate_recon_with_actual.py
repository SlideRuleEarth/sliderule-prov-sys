'''ps-server unit testing'''
import boto3
import pytest
import logging
import sys
import os
import pathlib
import uuid
import json
from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from google.protobuf.json_format import MessageToJson
from django.test import tag
from users.tests.utilities_for_unit_tests import init_test_environ,dump_org_account
import ps_server_pb2
import ps_server_pb2_grpc
from users import ps_client
from users.utils import FULL_FMT
from users.utils import DAY_FMT
from users.utils import MONTH_FMT
import time_machine
import time

module_name = 'tasks'

# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
import tasks

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
    logger.info('------')
    

# teardown after running all tests 
def teardown_module(tasks_module):
    logger.info('------')


@pytest.mark.cost
@pytest.mark.real_ps_server
@pytest.mark.django_db
@pytest.mark.recon_sim
@tag('cost')
def test_validate_recon_sliderule_org(tasks_module,caplog):
    '''
        This procedure will connect to a locally run ps-server for cost explorer calls
        and can be used to dry-run a forced reconciliation of sliderule cluster
        by entering the current values for the sliderule cluster
        This procedure will incur some small costs 
        https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
    '''
    with caplog.at_level(logging.INFO, logger="django"):
        caplog.set_level(logging.DEBUG)
        orgAccountObj,owner = init_test_environ("sliderule",
                                                org_owner=None,
                                                max_allowance=10000, 
                                                monthly_allowance=2000,
                                                balance=5102.57,
                                                fytd_accrued_cost=0, 
                                                most_recent_charge_time=datetime.now(timezone.utc)-timedelta(days=365), 
                                                most_recent_credit_time=datetime.now(timezone.utc)-timedelta(days=365),
                                                most_recent_recon_time=datetime.now(timezone.utc)-timedelta(days=365))

        dump_org_account(orgAccountObj=orgAccountObj,level='info')
        tasks.reconcile_org(orgAccountObj)
        dump_org_account(orgAccountObj=orgAccountObj,level='info')


@pytest.mark.cost
@pytest.mark.recon_sim
@pytest.mark.real_ps_server
@pytest.mark.django_db
@tag('cost')
def test_validate_recon_sliderule_org_with_time_machine(tasks_module,caplog):
    '''
        This procedure will connect to a locally run ps-server for cost explorer calls
        for sliderule cluster 
        It use the time machine and it will walk thru from 10 days ago until 8 days ago and 
        call recon_org for each hour simulating that period' reconciliations every hour
        by entering the current values for the sliderule cluster
        This procedure will incur some costs 
        https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
    '''
    logger.critical(f" ---- START HERE ---- ")
    with caplog.at_level(logging.INFO, logger="django"):
        time_now = datetime.now(timezone.utc)
        dt = time_now - timedelta(days=10)
        logger.info(f"time_now:{time_now.strftime('%Y-%m-%d %H:%M:%S')} dt:{dt.strftime('%Y-%m-%d %H:%M:%S')}")
        with time_machine.travel(dt,tick=False):
            fake_now = datetime.now(timezone.utc)
            logger.info(f"fake_now:{fake_now} dt:{dt}")
            logger.info(f"calling init_test_environ ...")
            orgAccountObj,owner = init_test_environ("sliderule",
                                                    org_owner=None,
                                                    max_allowance=10000, 
                                                    monthly_allowance=2000,
                                                    balance=5000,
                                                    fytd_accrued_cost=0, 
                                                    most_recent_charge_time=datetime.now(timezone.utc)-timedelta(days=11), 
                                                    most_recent_credit_time=datetime.now(timezone.utc)-timedelta(days=11),
                                                    most_recent_recon_time=datetime.now(timezone.utc)-timedelta(days=11))

        #dump_org_account(orgAccountObj=orgAccountObj,level='info')
        logger.critical(f"<<<--- NOW:{time_now.strftime('%Y-%m-%d %H:%M:%S')} {orgAccountObj.name} bal:{orgAccountObj.balance:.2f} fytd:{orgAccountObj.fytd_accrued_cost:.2f} mrct:{orgAccountObj.most_recent_charge_time.strftime('%Y-%m-%d %H:%M:%S')} --->>>")
        while dt < time_now - timedelta(days=8):
            with time_machine.travel(dt,tick=False):
                logger.critical(f"<<<--- dt:{dt.strftime('%Y-%m-%d %H:%M:%S')} {orgAccountObj.name} bal:{orgAccountObj.balance:.2f} fytd:{orgAccountObj.fytd_accrued_cost:.2f} mrct:{orgAccountObj.most_recent_charge_time} --->>>")
                tasks.reconcile_org(orgAccountObj)
                #dump_org_account(orgAccountObj=orgAccountObj,level='info')
                logger.critical(f"{orgAccountObj.name} bal:{orgAccountObj.balance:.2f} fytd:{orgAccountObj.fytd_accrued_cost:.2f}")
                time.sleep(1) # ce is rate limited
            dt = dt + timedelta(hours=1)
 