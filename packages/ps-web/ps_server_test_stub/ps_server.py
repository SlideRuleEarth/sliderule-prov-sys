# BSD 3-Clause License
#
# Copyright (c) 2022, University of Washington
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Provisioning System stubbed ps-server Test Driver for ps-web """
import sys
import os
# Get the path of the parent directory (Remember: we are in the container when running this)
#parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Add the parent directory to the Python path
#sys.path.append(parent_dir)
#print("After modification:", sys.path)
sys.path.append('/ps_server')

import argparse
from concurrent import futures
import contextlib
import logging
import unicodedata
import calendar
import time_machine
import grpc
import ps_server_pb2
import ps_server_pb2_grpc
import boto3
from statistics import mean, fmean, stdev

import pytz
from datetime import datetime, timezone, timedelta

import json
from pprint import pprint
import subprocess
import time
import requests
from time import sleep
from inspect import currentframe, getframeinfo
from collections import defaultdict
from google.protobuf.json_format import MessageToDict, MessageToJson
from requests.exceptions import HTTPError
from users.global_constants import *
from users.tests.global_test_constants import *
from google.protobuf.json_format import Parse
from google.protobuf.json_format import MessageToJson
from google.protobuf.text_format import MessageToString

domain_env = ""
cluster_repo = ""

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d:%(funcName)s] [%(message)s]",
    datefmt="%Y-%m-%d:%H:%M:%S",
)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.ERROR)

# file_handler = logging.FileHandler("/home/logs/ps-server-test-stub.log")
# file_handler.setFormatter(formatter)
# file_handler.setLevel(logging.ERROR)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.ERROR)

LOG.addHandler(console_handler)
#LOG.addHandler(file_handler)

SETUP_JSON_FILE = 'SetUp.json'
S3_BUCKET = os.environ.get("S3_BUCKET",'unit-test-bucket')


class shared_Mock_Clusters:
    '''
        This represents the state of the clusters that are being mocked.
    '''
    mocked_NUM_NODES_dict = {'':-1}  
    versions = ['v1', 'v2', 'v3', 'latest', 'unstable']
    deployed_dict = {False:-1}
    cluster_version_dict = {'':-1}   # SetUp version is in setup.json
    cluster_is_public_dict = {False:-1}   # SetUp version is in setup.json


def get_domain_env():
    return os.environ.get("DOMAIN",'localhost')

def get_terraform_cli():
    return os.environ.get("TERRAFORM_CLI", "terraform")

def get_root_dir():
    return '/ps_server'

def get_cluster_root_dir(name):
    return os.path.join(get_root_dir(),name)

def get_terraform_dir(name):
    return os.path.join(get_cluster_root_dir(name),"terraform")

def get_s3_client():
    return boto3.client("s3", region_name="us-west-2", endpoint_url= "http://localstack:4566")

def get_versions_for_org(name):
    VERSIONS =shared_Mock_Clusters.versions
    LOG.critical(VERSIONS)
    return VERSIONS

def get_ps_versions():
    versions = open('/ps_server/.ps_server_versions', 'r').read()
    LOG.debug(f'{versions}')
    return versions

## Hack These were cut-n-pasted from real ps-server.py... TBD what to do Here?
def read_SetUpCfg(name):
    LOG.info(f"read_SetUpCfg({name})")
    setup_json_file_path = os.path.join(get_cluster_root_dir(name),SETUP_JSON_FILE)
    setup_cfg = ps_server_pb2.SetUpReq()
    try:
        with open(setup_json_file_path, 'r') as json_file:
            json_str = json_file.read()
            # Parse the JSON string into the protobuf object
            Parse(json_str, setup_cfg)
    except FileNotFoundError:
        # Not always fatal....
        LOG.info(f"Uninitialized SetUp: FileNotFoundError reading :{setup_json_file_path}")  
    LOG.info(f"{setup_cfg} from {setup_json_file_path}")
    return setup_cfg


def write_SetUpCfg(name,setup_cfg):
    setup_json_file_path = os.path.join(get_cluster_root_dir(name),SETUP_JSON_FILE)
    # Ensure the directory exists
    os.makedirs(os.path.dirname(setup_json_file_path), exist_ok=True)
    json_str = MessageToJson(setup_cfg)
    with open(setup_json_file_path, 'w') as json_file:
        json_file.write(json_str)
        LOG.info(f"{MessageToString(setup_cfg)} to {setup_json_file_path} ")

def update_SetUpCfg(name,version,is_public,now):
    LOG.info(f"update_SetUpCfg: name:{name} version:{version} is_public:{is_public} now:{now}")
    try:
        setup_cfg = read_SetUpCfg(name) # might not exist
        LOG.info(f"FROM: {setup_cfg}")
        setup_cfg.name = name
        setup_cfg.version = version
        setup_cfg.is_public = is_public
        setup_cfg.now = now
        LOG.info(f"update_SetUpCfg: {MessageToString(setup_cfg,print_unknown_fields=True)}")
        write_SetUpCfg(name, setup_cfg)
    except Exception as e:
        LOG.exception(f" FAILED to read to read_SetUpCfg({name}) caught UNKNOWN exception:{repr(e)}")
        raise e
    LOG.info(f"  TO: {MessageToString(setup_cfg)}")


class Control(ps_server_pb2_grpc.ControlServicer):

    def Init(self, request, context): # Test only
        LOG.critical(f'Init request:{request}')
        try:
            if request.name == '': # set all orgs to this value
                for o in shared_Mock_Clusters.mocked_NUM_NODES_dict:
                    shared_Mock_Clusters.mocked_NUM_NODES_dict[o] = request.num_nodes
            else:
                shared_Mock_Clusters.mocked_NUM_NODES_dict[request.name] = request.num_nodes
        except Exception as e:
            LOG.critical(f'Exception in Init:{e}')
            return ps_server_pb2.InitRsp(success=False, error_msg=str(e))
        return ps_server_pb2.InitRsp(success=True, error_msg='')

    def GetVersions(self, request, context):
        return ps_server_pb2.GetVersionsRsp(versions=get_versions_for_org(name=request.name))

    def GetPSVersions(self, request, context):
        ps_server_versions = get_ps_versions()
        LOG.debug(f'ps server versions:{ps_server_versions}')
        return ps_server_pb2.GetPSVersionsRsp(ps_versions=ps_server_versions)

    def get_Response_Obj(
        self, name, ps_cmd, done=False, ps_server_error=False, error_msg=""
    ):
        rsp = ps_server_pb2.Response(
            name=name,
            ps_cmd=ps_cmd,
            done=done,
            ps_server_error=ps_server_error,
            error_msg=error_msg,
        )
        return rsp

    def check_for_fake_orgs(self, request, ps_cmd):

        if ps_cmd == 'Update':
            shared_Mock_Clusters.deployed_dict[request.name] = True
            shared_Mock_Clusters.mocked_NUM_NODES_dict[request.name] = request.num_nodes
            setup_cfg = read_SetUpCfg(request.name)
            shared_Mock_Clusters.cluster_version_dict[request.name] = setup_cfg.version
            shared_Mock_Clusters.cluster_is_public_dict[request.name] = setup_cfg.is_public
        if ps_cmd == 'Destroy':
            shared_Mock_Clusters.deployed_dict[request.name] = False
            shared_Mock_Clusters.cluster_version_dict[request.name] = ''
            shared_Mock_Clusters.cluster_is_public_dict[request.name] = ''

        cli_rsp = ps_server_pb2.cli_rsp(valid=True,updating=True,stdout=f'{ps_cmd} {request.name} testing 1..2...3...')
        state = ps_server_pb2.StateOfCluster(valid=True,deployed=shared_Mock_Clusters.deployed_dict[request.name],deployed_state=f'{ps_cmd} Testing....',ip_address='0.0.0.0')
        yield ps_server_pb2.Response(name=request.name,
                                        ps_cmd=ps_cmd,
                                        done=False,
                                        cli=cli_rsp,
                                        ps_server_error=False,
                                        error_msg='')
        if request.name == NEG_TEST_TERRAFORM_ERROR_ORG_NAME and ps_cmd != 'SetUp':
            state = ps_server_pb2.StateOfCluster(valid=True,deployed=False,deployed_state=f'{ps_cmd} Not Deployed (TEST)',ip_address='0.0.0.0')
            raise subprocess.CalledProcessError(returncode=1, cmd=NEG_TEST_TERRAFORM_ERROR_MSG, output='',stderr='dummy stderr')
        if request.name == NEG_TEST_GRPC_ERROR_ORG_NAME and ps_cmd != 'SetUp':
            state = ps_server_pb2.StateOfCluster(valid=True,deployed=False,deployed_state=f'{ps_cmd} Not Deployed (TEST)',ip_address='0.0.0.0')
            raise Exception(NEG_TEST_GRPC_ERROR_MSG)
        if request.name == NEG_TEST_STOP_ITER_ERROR_ORG_NAME and ps_cmd != 'SetUp':
            state = ps_server_pb2.StateOfCluster(valid=True,deployed=False,deployed_state=f'{ps_cmd} Not Deployed (TEST)',ip_address='0.0.0.0')
            raise StopIteration(NEG_TEST_STOP_ITER_ERROR_MSG)
        yield ps_server_pb2.Response(  name=request.name,
                                    ps_cmd=ps_cmd,
                                    state=state,
                                    cli=cli_rsp,
                                    done=True,
                                    ps_server_error=False,
                                    error_msg='')
    
    def fake_cmd(self, request, ps_cmd, st):
        try:
            yield from self.check_for_fake_orgs(request, ps_cmd)
        except Exception as e:
            emsg = (f" Processing fake_cmd {ps_cmd} {request.name} cluster caught this exception: ")
            LOG.exception(emsg)
            emsg += str(e)
            yield self.get_Response_Obj(
                name=request.name,
                ps_cmd=ps_cmd,
                ps_server_error=True,
                error_msg=emsg,)
        finally:
            # ALWAYS send a done!
            r = self.get_Response_Obj(
                name=request.name,
                ps_cmd=ps_cmd,
                done=True,
            )
            r.cli.valid = True
            r.cli.updating = True
            elapsed_tm = datetime.now(timezone.utc) - st
            r.cli.stdout = (
                "**************** "
                + request.name
                + " "
                + f'{ps_cmd}'
                + " Completed "
                + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                + " elasped:"
                + repr(elapsed_tm)
            )
            yield r
            LOG.info(f"{ps_cmd} {request.name} cluster completed")
            for handler in LOG.handlers:
                handler.flush()

    def FakeCMD(self, request, ps_cmd):
        '''
        This is the main entry point for the ps-server stubbed test driver.
        It is called by the GRPC framework when a client calls the ProvisionCmd
        RPC.  

        The real ps_server always catches exceptions and returns a valid Response
        Then finally always sends a done=True response.  This is to ensure that
        the client does not hang waiting for a response. 

        If that changes in the real ps_server, then this test driver will need to be updated.

        '''
        LOG.critical(f'STUBBED {ps_cmd} {request.name} cluster')
        with time_machine.travel(datetime.strptime(request.now,FMT),tick=False):
            try:
                LOG.critical(f'STUBBED {ps_cmd} {request} cluster in  domain:{domain_env}')
                st = datetime.now(timezone.utc)
                yield from self.fake_cmd(request,ps_cmd,st)
            except Exception as e:
                emsg = (f" Processing FAKE_CMD {ps_cmd} {request.name} cluster caught this exception: ")
                LOG.exception(emsg)
                emsg += str(e)
                yield self.get_Response_Obj(
                    name=request.name,
                    ps_cmd=f'{ps_cmd}',
                    ps_server_error=True,
                    error_msg=emsg,)

    def Refresh(self, request, context):  ## This is called by GRPC framework
        yield from self.FakeCMD(request,'Refresh')

    def Destroy(self, request, context):  ## This is called by GRPC framework
        yield from self.FakeCMD(request,'Destroy')

    def Update(self, request, context):  ## This is called by GRPC framework
        yield from self.FakeCMD(request,'Update')


    def SetUp(self, request, context):
        try:
            LOG.critical(f'STUBBED SetUp {request.name} version:{request.version} is_public:{request.is_public} cluster in  domain:{domain_env}')
            deployed = shared_Mock_Clusters.deployed_dict[request.name]
        except KeyError:
            shared_Mock_Clusters.deployed_dict[request.name] = False
            shared_Mock_Clusters.mocked_NUM_NODES_dict[request.name] = 0
        update_SetUpCfg(request.name, request.version, request.is_public, request.now)
        yield from self.FakeCMD(request,'SetUp')

    def GetCurrentSetUpCfg(self,request,context):
        '''
        This is the version of terraform files setup for the Org's cluster
        '''
        setup_cfg = read_SetUpCfg(request.name)
        return ps_server_pb2.GetCurrentSetUpCfgRsp(setup_cfg=setup_cfg)

class Account(ps_server_pb2_grpc.AccountServicer):

    FULL_FMT = "%Y-%m-%dT%H:%M:%SZ"
    DAY_FMT = "%Y-%m-%d"

    def CurrentCost(self, currentCostReq, context):  ## This is called by GRPC framework
        LOG.info("%s cluster", currentCostReq.name)
        retRsp = ps_server_pb2.CostAndUsageRsp( name=currentCostReq.name,
                                                total=0.0,
                                                unit="",
                                                server_error=True,
                                                error_msg="Response Not Set Yet")  

        try:
            LOG.info(f"{currentCostReq}")
            rsp_tm = []
            rsp_cost = []
            now = datetime.now(timezone.utc)
            retRsp = ps_server_pb2.CostAndUsageRsp(
                name=currentCostReq.name,
                granularity=currentCostReq.granularity,
                total=0.0,
                unit="",
                tm = rsp_tm,
                cost = rsp_cost,
                server_error=False,
                error_msg="")
            if currentCostReq.granularity == 'HOURLY':
                st = now.replace(hour=0,minute=0,second=0,microsecond=0) # begin of day
                hrs = int((now - st).total_seconds() / 3600)
                LOG.info(f"now:{now}")
                
                for h in range(0,hrs):
                    tm = st + timedelta(hours=h)
                    rsp_tm.append(tm.strftime(FMT_Z))
                    rsp_cost.append(float("0.45"))

            elif currentCostReq.granularity == 'DAILY':
                st = now.replace(hour=0,minute=0,second=0,microsecond=0) - timedelta(days=3) # begin of day
                days = int((now - st).total_seconds() / 3600)
                rsp_tm= [
                    (st+timedelta(days=1)).strftime(FMT_DAILY),
                    (st+timedelta(days=2)).strftime(FMT_DAILY),
                    (st+timedelta(days=3)).strftime(FMT_DAILY),
                    ]
                rsp_cost=[
                    float("2.51"),
                    float("10.80"),
                    float("2.40")
                    ]        
            elif currentCostReq.granularity == 'MONTHLY':
                rsp_tm= [
                    datetime(year=2023,month=1,day=1).strftime(FMT_DAILY), # uses DAILY
                    datetime(year=2023,month=2,day=1).strftime(FMT_DAILY),
                    datetime(year=2023,month=3,day=1).strftime(FMT_DAILY),
                    ]
                rsp_cost=[
                    float("50.51"),
                    float("100.80"),
                    float("233.40")
                    ]        

            retRsp = ps_server_pb2.CostAndUsageRsp(
                name=currentCostReq.name,
                granularity=currentCostReq.granularity,
                total=0.0,
                unit="",
                tm = rsp_tm,
                cost = rsp_cost,
                server_error=False,
                error_msg="")

        except Exception as e:
            emsg = (f" Processing for org: {currentCostReq.name} cluster caught this exception {e}")
            LOG.exception(emsg)
            return ps_server_pb2.CostAndUsageRsp(
                name=currentCostReq.name,
                total=0.0,
                unit="",
                server_error=True,
                error_msg=emsg)            
        LOG.critical(f"TodaysCost response: {MessageToJson(retRsp)}")
        return retRsp

    def TodaysCost(self, todaysCostReq, context):  ## This is called by GRPC framework
        retRsp = ps_server_pb2.CostAndUsageRsp( name=todaysCostReq.name,
                                                total=0.0,
                                                unit="",
                                                server_error=True,
                                                error_msg="Response Not Set Yet")  
        try:
            LOG.critical(f"todaysCostReq:{todaysCostReq}")
            rsp_tm = []
            rsp_cost = []
            if todaysCostReq.name=="test_reconcileOrg:Req1:2020-01-28 11:00:00+00:00":
                fake_now1 = datetime.now(timezone.utc)
                LOG.critical(f"fake now1:{fake_now1}")
                
                for h in range(1,11):
                    rsp_tm.append(datetime.strftime(datetime(year=2020,month=1,day=27,hour=h),FMT_Z))
                    rsp_cost.append(float("0.45"))
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=todaysCostReq.name,
                    granularity='HOURLY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")
            if todaysCostReq.name=="test_reconcileOrg:Req2:2020-01-29 11:00:00+00:00":
                fake_now1 = datetime.now(timezone.utc)
                LOG.critical(f"fake now1:{fake_now1}")
                
                for h in range(1,11):
                    rsp_tm.append(datetime.strftime(datetime(year=2020,month=1,day=28,hour=h),FMT_Z))
                    rsp_cost.append(float("0.45"))
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=todaysCostReq.name,
                    granularity='HOURLY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")
            if todaysCostReq.name=="test_reconcileOrg:Req3:2020-01-30 11:00:00+00:00":
                fake_now1 = datetime.now(timezone.utc)
                LOG.critical(f"fake now1:{fake_now1}")
                
                for h in range(1,11):
                    rsp_tm.append(datetime.strftime(datetime(year=2020,month=1,day=29,hour=h),FMT_Z))
                    rsp_cost.append(float("0.45"))
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=todaysCostReq.name,
                    granularity='HOURLY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

            if todaysCostReq.name=="test_reconcileOrg:Req4:2021-01-30 11:00:00+00:00":
                fake_now1 = datetime.now(timezone.utc)
                LOG.critical(f"fake now1:{fake_now1}")
                
                for h in range(1,11):
                    rsp_tm.append(datetime.strftime(datetime(year=2021,month=1,day=29,hour=h),FMT_Z))
                    rsp_cost.append(float("0.45"))
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=todaysCostReq.name,
                    granularity='HOURLY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

            if todaysCostReq.name=="test_reconcileOrg:Req5:2021-01-31 11:00:00+00:00":
                fake_now1 = datetime.now(timezone.utc)
                LOG.critical(f"fake now1:{fake_now1}")
                
                for h in range(1,11):
                    rsp_tm.append(datetime.strftime(datetime(year=2021,month=1,day=30,hour=h),FMT_Z))
                    rsp_cost.append(float("0.45"))
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=todaysCostReq.name,
                    granularity='HOURLY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")


        except Exception as e:
            emsg = (f" Processing for org: {todaysCostReq.name} cluster caught this exception {e}")
            LOG.exception(emsg)
            retRsp = ps_server_pb2.CostAndUsageRsp(
                name=todaysCostReq.name,
                total=0.0,
                unit="",
                server_error=True,
                error_msg=emsg)  
        LOG.critical(f"TodaysCost response: {MessageToJson(retRsp)}")
        return retRsp

    def DailyHistCost(self, dailyHistCostReq, context):
        retRsp = ps_server_pb2.CostAndUsageRsp( name=dailyHistCostReq.name,
                                                total=0.0,
                                                unit="",
                                                server_error=True,
                                                error_msg="Response Not Set Yet")  
        try:
            LOG.critical(f"{dailyHistCostReq}")
            if dailyHistCostReq.name=="test_ps_server_stub":
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    total=0.0,
                    unit="",
                    server_error=False,
                    error_msg="")
            if dailyHistCostReq.name=="test_reconcileOrg:Req1:2020-01-28 11:00:00+00:00":
                rsp_tm= [
                    datetime.strftime(datetime(year=2020,month=1,day=25),FMT_DAILY),
                    datetime.strftime(datetime(year=2020,month=1,day=26),FMT_DAILY),
                    datetime.strftime(datetime(year=2020,month=1,day=27),FMT_DAILY),
                    ]
                rsp_cost=[
                    float("2.51"),
                    float("10.80"),
                    float("2.40")
                ]
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    granularity='DAILY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

            if dailyHistCostReq.name=="test_reconcileOrg:Req2:2020-01-29 11:00:00+00:00":
                rsp_tm= [
                    datetime.strftime(datetime(year=2020,month=1,day=28),FMT_DAILY),
                    ]
                rsp_cost=[
                    float("3.00"),
                ]
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    granularity='DAILY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

            if dailyHistCostReq.name=="test_reconcileOrg:Req3:2020-01-30 11:00:00+00:00":
                rsp_tm= [
                    datetime.strftime(datetime(year=2020,month=1,day=29),FMT_DAILY),
                    ]
                rsp_cost=[
                    float("3.00"),
                ]
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    granularity='DAILY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

            if dailyHistCostReq.name=="test_reconcileOrg:Req4:2021-01-30 11:00:00+00:00":
                rsp_tm= [
                    datetime.strftime(datetime(year=2021,month=1,day=29),FMT_DAILY),
                    ]
                rsp_cost=[
                    float("3.00"),
                ]
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    granularity='DAILY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")


            if dailyHistCostReq.name=="test_reconcileOrg:Req5:2021-01-31 11:00:00+00:00":
                rsp_tm= [
                    datetime.strftime(datetime(year=2021,month=1,day=30),FMT_DAILY),
                    ]
                rsp_cost=[
                    float("3.00"),
                ]
                retRsp = ps_server_pb2.CostAndUsageRsp(
                    name=dailyHistCostReq.name,
                    granularity='DAILY',
                    total=0.0,
                    unit="",
                    tm = rsp_tm,
                    cost = rsp_cost,
                    server_error=False,
                    error_msg="")

        except Exception as e:
            emsg = (f" Processing for org: {dailyHistCostReq.name} cluster caught this exception {e}")
            LOG.exception(emsg)
            retRsp = ps_server_pb2.CostAndUsageRsp(
                name=dailyHistCostReq.name,
                total=0.0,
                unit="",
                server_error=True,
                error_msg=emsg)  
        LOG.critical(f"DailyHistCost response: {MessageToJson(retRsp)}")
        return retRsp

    def NumNodes(self,numNodesReq, context):
        LOG.critical(f"{numNodesReq.region} {numNodesReq.name} {numNodesReq.version}")
        try:
            num_nodes = shared_Mock_Clusters.mocked_NUM_NODES_dict.get(numNodesReq.name,0) 
        except KeyError:
            num_nodes=-1
            LOG.error(f"INVALID name:{numNodesReq.name}")
            raise KeyError
        rsp = ps_server_pb2.NumNodesRsp(name = numNodesReq.name,version=numNodesReq.version,region=numNodesReq.region,num_nodes = num_nodes)
        LOG.critical(f"NumNodes response: {rsp}")
        return rsp


@contextlib.contextmanager
def run_server(host, port, use_tls):
    hoststring = host + ":" + str(port)

    LOG.info("running server listening on:%s use_tls:%s", hoststring, use_tls)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    ps_server_pb2_grpc.add_ControlServicer_to_server(Control(), server)
    ps_server_pb2_grpc.add_AccountServicer_to_server(Account(), server)

    LOG.info("Insecure port:%s",hoststring)
    port = server.add_insecure_port(hoststring)

    server.start()
    try:
        yield server, host, port, use_tls
    finally:
        server.stop(0)

def main():
    global domain_env
    global cluster_repo
    os.environ['TZ'] = 'UTC'
    time.tzset()
    LOG = logging.getLogger("ps_logger")
    LOG.info(f"Starting ps-server @ {datetime.now().astimezone()}")
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--host", nargs="?", type=str, default="[::]", help="the listening host"
        )
        parser.add_argument(
            "--port", nargs="?", type=int, default=50051, help="the listening port"
        )
        parser.add_argument(
            "--use_tls",
            default="False",
            help="secured with tls certs?",
        )
        args = parser.parse_args()

        #LOG.info(repr(get_num_nodes("us-west-2","Developers","latest")))
        #LOG.info(repr(get_num_nodes("us-west-2","esr","")))
        cluster_repo = os.environ.get("CLUSTER_REPO")
        if cluster_repo == "":
            emsg = "CLUSTER_REPO env not set!"
            LOG.error(emsg)
            for handler in LOG.handlers:
               handler.flush()
            raise RuntimeError(emsg)
        domain_env = os.environ.get("DOMAIN")
        if domain_env == "":
            emsg = "DOMAIN env not set!"
            LOG.error(emsg)
            for handler in LOG.handlers:
               handler.flush()
            raise RuntimeError(emsg)

        #LOG.info("calling run_server")
        with run_server(args.host, args.port, args.use_tls) as (
            server,
            host,
            port,
            use_tls,
        ):
            LOG.critical(
                "\n\n------------------- Server is READY listening at %s:%s use_tls?:%s-----CLUSTER_REPO:%s--- domain: %s--------\n\n",
                host,
                port,
                use_tls,
                cluster_repo,
                domain_env
            )
            #for handler in LOG.handlers:
            #   handler.flush()
            server.wait_for_termination()

    except HTTPError as http_err:
        LOG.error(f"HTTP error occurred getting Org names from website: {http_err}")
    except Exception as e:
        LOG.error(f"Caught an exception in main: {e}")
    LOG.info("Exiting ps-server ")


if __name__ == "__main__":
    main()
