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
from ps_server import S3_BUCKET,ps_server_pb2,get_sorted_tm_cost,merge_ccrs,get_ps_versions,get_versions_for_org,read_SetUpCfg,ORGS_PERMITTED_JSON_FILE,get_domain_env,get_all_versions,get_asg_cfgs_for_all_versions
from conftest import *
from test_utils import *

def example_ccr(gran,tm,cost):
    ccr = ps_server_pb2.CostAndUsageRsp(
        name="test_org",
        granularity = gran,
        tm=tm,
        cost=cost,
        total=0.0,
        unit="",
        server_error=False,
        error_msg="",
    )
    return ccr

def HOURLY_FMT():
    return "%Y-%m-%dT%H:%M:%S%Z"

def DAILY_FMT():
    return "%Y-%m-%d%Z"

def datetime_range(start, end, delta):
    current = start
    while current < end:
        yield current
        current += delta

def fake_cost_range_days(logger,start,end):
    logger.info(f"st:{start} et:{end}")
    assert(start < end)
    cents = Decimal('0.01')
    current = start
    costs = []
    while current < end:
        cost = Decimal(Decimal(current.day) + Decimal((current.day) * cents)).quantize(cents, ROUND_HALF_UP)
        costs.append(float(cost))
        current += timedelta(days=1)
    return costs

def get_HOURLY_tms(st,et):
    return [dt.strftime(HOURLY_FMT()) for dt in  datetime_range(st, et, timedelta(hours=1))]

def get_DAILY_tms(st,et):
    return [dt.strftime(DAILY_FMT()) for dt in  datetime_range(st, et, timedelta(days=1))]

def get_DAILY_costs_tms(logger,st,et):
    tms = [dt.strftime(DAILY_FMT()) for dt in  datetime_range(st, et, timedelta(days=1))]
    costs = fake_cost_range_days(logger,st,et)
    return tms,costs

class TestMergeCCR:
    def test_get_HOURLY_tms(self,setup_logging):
        logger = setup_logging
        logger.info(type(get_HOURLY_tms))
        tms = get_HOURLY_tms(datetime(year=2023,month=1,day=1),datetime(year=2023,month=1,day=2))
        logger.info(f"tms:{tms}")
        assert(len(tms)==24)
        assert(tms[0]=='2023-01-01T00:00:00')
        assert(tms[23]=='2023-01-01T23:00:00')

    def test_get_DAILY_tms(self,setup_logging):
        logger = setup_logging
        tms = get_DAILY_tms(datetime(year=2023,month=1,day=1),datetime(year=2023,month=2,day=1))
        logger.info(f"tms:{tms}")
        assert(len(tms)==31)
        assert(tms[0]=='2023-01-01')
        assert(tms[30]=='2023-01-31')

    def test_fake_cost_range_days(self,setup_logging):
        logger = setup_logging
        costs = fake_cost_range_days(logger,datetime(year=2023,month=1,day=1),datetime(year=2023,month=2,day=1))
        assert(costs != None)

    def test_get_DAILY_costs_tms(self,setup_logging):
        logger = setup_logging
        tms,costs = get_DAILY_costs_tms(logger,datetime(year=2023,month=1,day=1),datetime(year=2023,month=2,day=1))
        logger.info(f"tms:{tms} costs:{costs}")
        assert(tms != None)
        assert(costs != None)
        assert(len(tms) == 31)
        assert(tms[0]=='2023-01-01')
        assert(len(costs) == 31)
        assert(costs[0] == 1.01)

    def get_sorted_tm_cost_daily(self, logger,st1,st2,et1,et2):
        ccr1 = ps_server_pb2.CostAndUsageRsp()
        tm1,cost1 = get_DAILY_costs_tms(logger,st1,et1)
        ccr1.tm.extend(tm1)
        ccr1.cost.extend(cost1)
        ccr2 = ps_server_pb2.CostAndUsageRsp()
        tm2,cost2 = get_DAILY_costs_tms(logger,st2,et2)
        ccr2.tm.extend(tm2)
        ccr2.cost.extend(cost2)
        return get_sorted_tm_cost(ccr1,ccr2)
    
    def test_get_sorted_tm_cost_daily_non_overlap(self, setup_logging):
        logger = setup_logging
        sorted1_tuple = self.get_sorted_tm_cost_daily(logger,
                                                st1=datetime(year=2023,month=1,day=1),
                                                et1=datetime(year=2023,month=2,day=1),
                                                st2=datetime(year=2023,month=3,day=1),
                                                et2=datetime(year=2023,month=4,day=1))
        
        sorted2_tuple = self.get_sorted_tm_cost_daily(logger,
                                                st1=datetime(year=2023,month=3,day=1),
                                                et1=datetime(year=2023,month=4,day=1),
                                                st2=datetime(year=2023,month=1,day=1),
                                                et2=datetime(year=2023,month=2,day=1))

        assert(sorted1_tuple == sorted2_tuple)
        assert(len(sorted1_tuple)==62)
        assert(sorted1_tuple[0][0]=='2023-01-01')
        assert(sorted1_tuple[0][1]==1.01)
        assert(sorted1_tuple[30][0]=='2023-01-31')
        assert(sorted1_tuple[30][1]==31.31)
        assert(sorted1_tuple[61][0]=='2023-03-31')
        assert(sorted1_tuple[61][1]==31.31)

    def test_get_sorted_tm_cost_daily_complete_overlap(self, setup_logging):
        logger = setup_logging
        sorted1_tuple = self.get_sorted_tm_cost_daily(  logger,
                                                        st1=datetime(year=2023,month=1,day=1),
                                                        et1=datetime(year=2023,month=2,day=1),
                                                        st2=datetime(year=2023,month=1,day=1),
                                                        et2=datetime(year=2023,month=2,day=1))
        logger.info(f"sorted1_tuple:{sorted1_tuple}")
        assert(len(sorted1_tuple)==31)
        assert(sorted1_tuple[0][0]=='2023-01-01')
        assert(sorted1_tuple[0][1]==1.01)
        assert(sorted1_tuple[30][0]=='2023-01-31')
        assert(sorted1_tuple[30][1]==31.31)
        
    
    def merge_ccrs_daily(self, logger, st1, et1, st2, et2):
        ccr = ps_server_pb2.CostAndUsageRsp()
        ccr1 = ps_server_pb2.CostAndUsageRsp()
        tm1,cost1 = get_DAILY_costs_tms(logger,st1,et1)
        ccr1.tm.extend(tm1)
        ccr1.cost.extend(cost1)
        logger.info(f"type(ccr1.tm):{type(ccr1.tm)} type(ccr1.cost):{type(ccr1.cost)}")
        ccr2 = ps_server_pb2.CostAndUsageRsp()
        tm2,cost2 = get_DAILY_costs_tms(logger,st2,et2)
        ccr2.tm.extend(tm2)
        ccr2.cost.extend(cost2)
        st1 = get_sorted_tm_cost(ccr1,ccr2)
        merged_ccr = merge_ccrs(ccr,ccr1,ccr2)
        assert(len(st1) == len(ccr.tm))
        assert(len(st1) == len(ccr.cost))
        logger.info(f"{MessageToJson(ccr)}")
        return merged_ccr

    def test_merge_ccrs_daily_non_overlap(self,setup_logging):
        logger = setup_logging
        merged_ccr = self.merge_ccrs_daily( logger=logger,
                                            st1=datetime(year=2023,month=1,day=1),
                                            et1=datetime(year=2023,month=2,day=1),
                                            st2=datetime(year=2023,month=3,day=1),
                                            et2=datetime(year=2023,month=4,day=1))
        assert(len(merged_ccr.tm) == 62)
        assert(merged_ccr.tm[0]=='2023-01-01')
        assert(merged_ccr.tm[30]=='2023-01-31')
        assert(merged_ccr.tm[61]=='2023-03-31')

        assert(len(merged_ccr.cost) == 62)
        assert(merged_ccr.cost[0]==1.01)
        assert(merged_ccr.cost[30]==31.31)
        assert(merged_ccr.cost[61]==31.31)

    def test_merge_ccrs_daily_complete_overlap(self, setup_logging):
        merged_ccr = self.merge_ccrs_daily( logger=setup_logging,
                                            st1=datetime(year=2023,month=1,day=1),
                                            et1=datetime(year=2023,month=2,day=1),
                                            st2=datetime(year=2023,month=1,day=1),
                                            et2=datetime(year=2023,month=2,day=1))
        assert(len(merged_ccr.tm) == 31)
        assert(merged_ccr.tm[0]=='2023-01-01')
        assert(merged_ccr.tm[30]=='2023-01-31')

        assert(len(merged_ccr.cost) == 31)
        assert(merged_ccr.cost[0]==1.01)
        assert(merged_ccr.cost[30]==31.31)

    def test_merge_ccrs_daily_partial_overlap(self, setup_logging):
        merged_ccr = self.merge_ccrs_daily( logger=setup_logging,
                                            st1=datetime(year=2023,month=1,day=1),
                                            et1=datetime(year=2023,month=2,day=15),
                                            st2=datetime(year=2023,month=2,day=1),
                                            et2=datetime(year=2023,month=4,day=1))
        assert(len(merged_ccr.tm) == 90)
        assert(merged_ccr.tm[0]=='2023-01-01')
        assert(merged_ccr.tm[30]=='2023-01-31')
        assert(merged_ccr.tm[31]=='2023-02-01')
        assert(merged_ccr.tm[32]=='2023-02-02')
        assert(merged_ccr.tm[89]=='2023-03-31')

        assert(len(merged_ccr.cost) == 90)
        assert(merged_ccr.cost[0]==1.01)
        assert(merged_ccr.cost[30]==31.31)
        assert(merged_ccr.cost[31]==1.01)
        assert(merged_ccr.cost[32]==2.02)
        assert(merged_ccr.cost[89]==31.31)

#@pytest.mark.dev
def test_get_ps_versions(setup_logging):
    logger = setup_logging
    ps_versions = get_ps_versions()
    logger.info(f'ps_server_versions:{ps_versions}')
    assert ('PS_SERVER_DOCKER_TAG=dev' in ps_versions)
    assert ('PS_SERVER_GIT_VERSION=' in ps_versions)

#@pytest.mark.dev
def test_get_asg_cfgs_for_all_versions(setup_logging,s3):
    logger = setup_logging
    asg_cfgs = get_asg_cfgs_for_all_versions(s3_client=s3)
    logger.info(f'asg_cfgs:{asg_cfgs}')
    assert ('latest' in asg_cfgs)
    assert ('v3' in asg_cfgs)
    assert( 'aarch64' in asg_cfgs['test'])
    assert( 'aarch64_pytorch' in asg_cfgs['test'])
    assert( 'x86_64' in asg_cfgs['test'])
    assert( 'x86_64_pytorch' in asg_cfgs['test'])


#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('v3',False),('latest',True)], indirect=True)
def test_get_versions(setup_logging,terraform_env,s3,test_name):
    logger = setup_logging
    versions_for_org = get_versions_for_org(s3_client=s3,org_to_check=test_name)
    logger.info(f'ps_versions:{versions_for_org}')
    assert ('latest' in versions_for_org)
    assert ('v3' in versions_for_org)

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('v3',False),('v3',True)], indirect=True)
def test_read_SetUpCfg_version_v3(setup_logging,terraform_env,test_name):
    logger = setup_logging
    cur_version = read_SetUpCfg(name=test_name).version
    logger.info(f'cur_version:{cur_version}')
    assert ('latest' != cur_version)
    assert ('v3' == cur_version)

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('latest',False),('latest',True)], indirect=True)
def test_read_SetUpCfg_version_latest(setup_logging,terraform_env,test_name):
    logger = setup_logging
    cur_version = read_SetUpCfg(name=test_name).version
    logger.info(f'cur_version:{cur_version}')
    assert ('latest' == cur_version)
    assert ('v3' != cur_version)

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('latest',False),('v3',False)], indirect=True)
def test_read_SetUpCfg_is_public_False(setup_logging,terraform_env,test_name):
    logger = setup_logging
    is_public = read_SetUpCfg(name=test_name).is_public
    logger.info(f'is_public:{is_public}')
    assert not is_public

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('latest',True),('v3',True)], indirect=True)
def test_read_SetUpCfg_is_public_True(setup_logging,terraform_env,test_name):
    logger = setup_logging
    is_public = read_SetUpCfg(name=test_name).is_public
    logger.info(f'is_public:{is_public}')
    assert is_public
import pytest
import os
import json

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('latest', True), ('v3', True)], indirect=True)
def test_read_PermittedOrg_included(setup_logging, s3, terraform_env, test_name):
    logger = setup_logging

    s3_key = os.path.join('prov-sys', 'cluster_tf_versions', 'latest', ORGS_PERMITTED_JSON_FILE)

    upload_json_string_to_s3(
        s3_client=s3,
        s3_bucket=S3_BUCKET,
        s3_key=s3_key,
        json_string=f'["{test_name}", "unit-test-private"]',
        logger=logger
    )

    # Log contents of ORGS_PERMITTED_JSON_FILE
    response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
    permitted_json = json.loads(response['Body'].read().decode('utf-8'))
    logger.info(f'Contents of {ORGS_PERMITTED_JSON_FILE}: {permitted_json}')

    versions_for_org = get_versions_for_org(s3_client=s3, org_to_check=test_name)
    logger.info(f'versions_for_org<{test_name}>: {versions_for_org}')

    all_versions = get_all_versions(s3_client=s3)
    logger.info(f'all_versions: {all_versions}')

    assert(not have_same_elements(versions_for_org, all_versions))
    missing = set(all_versions) - set(versions_for_org)
    assert(missing=={'v4.9.4'})
    extra = set(versions_for_org) - set(all_versions)
    logger.info('Element mismatch detected')
    if missing:
        logger.error(f'Missing from versions_for_org: {missing}')
    if extra:
        logger.error(f'Unexpected in versions_for_org: {extra}')

    assert 'latest' in versions_for_org
    assert 'v3' in versions_for_org
    assert 'unstable' in versions_for_org


#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('latest',True),('v3',True)], indirect=True)
def test_read_PermittedOrg_excluded(setup_logging,s3,terraform_env,test_name):
    logger = setup_logging
    upload_json_string_to_s3(s3_client=s3,
                             s3_bucket=S3_BUCKET,
                             s3_key=os.path.join('prov-sys','cluster_tf_versions','latest',ORGS_PERMITTED_JSON_FILE),
                             json_string=f'["{test_name}"]', # test_name is unit-test-org
                             logger=logger)
    versions_for_org = get_versions_for_org(s3_client=s3,org_to_check='unit-test-private')
    logger.info(f'versions_for_org:{versions_for_org}')
    all_versions = get_all_versions(s3_client=s3)
    logger.info(f'all_versions:{all_versions}')
    assert(not have_same_elements(versions_for_org,all_versions))
    assert ('latest' not in versions_for_org)
    assert ('v3' in versions_for_org)
    assert ('unstable' in versions_for_org)
    
#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('unstable',False),('v3',False)], indirect=True)
def test_read_SetUpCfg_is_public_False(setup_logging,terraform_env,test_name):
    logger = setup_logging
