'''ps-server unit testing'''
import boto3
import pytest
import logging
import sys
import os
import pathlib
import pytz

from importlib import import_module
from datetime import datetime, timezone, timedelta
from decimal import *
from google.protobuf.json_format import MessageToJson
from django.test import tag
from users.tests.utilities_for_unit_tests import init_test_environ,dump_org_account
import ps_server_pb2
import ps_server_pb2_grpc
from users import ps_client

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


FMT_Z  = "%Y-%m-%dT%H:%M:%SZ"
FMT    = "%Y-%m-%dT%H:%M:%S%Z"
FMT_z  = "%Y-%m-%dT%H:%M:%S%z" # %z is offset where Z is equivalent to +00:00
FMT_TZ = "%Y-%m-%d %H:%M:%S %Z"

FMT_MONTHLY = "%Y-%m"
FMT_DAILY = "%Y-%m-%d"
FMT_HOURLY = "%Y-%m-%dT%H:%M"



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
@tag('cost')
def test_experiment(tasks_module,caplog):
    '''
        This procedure will connect to a locally run ps-server for cost explorer calls
        and can be used to develop new test using cost explorer
        This procedure will incur some small costs 
        https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
    '''
    with caplog.at_level(logging.CRITICAL, logger="django"):
        global FMT, FMT_Z, FMT_DAILY
        with ps_client.create_client_channel("account") as channel:
            time_now,time_now_str = tasks.get_tm_now_tuple()
            ac = ps_server_pb2_grpc.AccountStub(channel)
            start= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)- timedelta(days=7)
            start_tm_str = datetime.strftime(start, FMT_Z) 
            logger.info(f"DailyHistCost start_tm_str:{start_tm_str}  using:{FMT_Z}")
            rsp = ac.DailyHistCost(ps_server_pb2.DailyHistCostReq(org_name="sliderule", start_tm=start_tm_str, end_tm=time_now_str))
            most_recent_tm_str = rsp.tm[len(rsp.tm)-1]
            logger.info(f"DailyHistCost most_recent_tm_str:{most_recent_tm_str} ")
            time_now,time_now_str = tasks.get_tm_now_tuple()
            rsp = ac.TodaysCost(ps_server_pb2.TodaysCostReq(org_name="sliderule",tm=time_now_str))
            most_recent_tm_str = rsp.tm[len(rsp.tm)-1]
            logger.info(f"TodaysCost most_recent_tm_str:{most_recent_tm_str} ")



