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
from users.tests.utilities_for_unit_tests import init_test_environ

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

@pytest.mark.cost
@pytest.mark.real_ps_server
@pytest.mark.django_db
@tag('cost')
def test_validate_fytd_UofMDTest(tasks_module,caplog):
    '''
        This procedure will incur some small costs 
        https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
    '''
    with caplog.at_level(logging.CRITICAL, logger="django"):
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
        ccr,rsp = tasks_module.get_current_cost_report(orgAccountObj.name,'DAILY',time_now)
        logger.info(f"ccr:{ccr}")
        logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        cost = 0.00
        for c in rsp.cost:
            cost += c
        logger.info(f"cost:{cost}")
        total = Decimal(cost).quantize(Decimal('0.01'), ROUND_HALF_UP)
        logger.debug(f"fytd_total_cost:{total}")

@pytest.mark.cost
@pytest.mark.real_ps_server
@pytest.mark.django_db
@tag('cost')
def test_validate_fytd_sliderule_org(tasks_module,caplog):
    '''
        This procedure will incur some small costs 
        https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
    '''
    with caplog.at_level(logging.CRITICAL, logger="django"):
        time_now = datetime.now(timezone.utc)
        orgAccountObj,owner = init_test_environ("sliderule",
                                                org_owner=None,
                                                max_allowance=20000, 
                                                monthly_allowance=1000,
                                                balance=2000,
                                                fytd_accrued_cost=100, 
                                                most_recent_charge_time=time_now, 
                                                most_recent_credit_time=time_now,
                                                most_recent_recon_time=time_now)
        ccr,rsp = tasks_module.get_current_cost_report(orgAccountObj.name,'DAILY',time_now)
        logger.info(f"ccr:{ccr}")
        logger.info(f"rsp:{rsp}")
        assert(rsp.server_error == False)
        cost = 0.00
        for c in rsp.cost:
            cost += c
        logger.info(f"cost:{cost}")
        total = Decimal(cost).quantize(Decimal('0.01'), ROUND_HALF_UP)
        logger.debug(f"fytd_total_cost:{total}")

