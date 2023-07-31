import pytest
from datetime import datetime, timezone, timedelta
from unittest import mock
import logging
import boto3
import uuid
import json
import os
import pathlib
import sys
from test_utils import run_subprocess_command,run_terraform_cmd, bucket_exists, s3_folder_exist,upload_folder_to_s3,get_tf_workspaces,get_root_dir,get_terraform_dir,copy_s3_objects,delete_folder_from_s3,terraform_setup,terraform_teardown
import glob
import requests
from pathlib import Path
from google.protobuf import json_format

import time


# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
from ps_server import ps_server_pb2, poll_for_localstack_status,get_org_root_dir,delete_folder_from_s3
from importlib import import_module

from ps_server import Control  # Import the Control class

import subprocess

@pytest.fixture(scope='session', autouse=True)
def setup_logging():
    # Create a custom logger
    logger = logging.getLogger('unit-testing')
    # Set level of logging
    #logger.setLevel(logging.ERROR)
    logger.setLevel(logging.INFO)
    #logger.setLevel(logging.DEBUG)

    # Create handlers
    console_handler = logging.StreamHandler()
    #console_handler.setLevel(logging.ERROR)
    console_handler.setLevel(logging.INFO)
    #console_handler.setLevel(logging.DEBUG)

    # Create formatter and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)

    yield logger  # provide the fixture value

    # After the test session, remove the handler to avoid logging duplicate messages
    logger.removeHandler(console_handler)

@pytest.fixture(scope="session", autouse=True)
def localstack_setup(setup_logging):
    # wait for localstack to be ready
    start_time = time.time()
    logger = setup_logging
    assert poll_for_localstack_status(logger), "LocalStack is not running or failed to initialize"   
    
'''Mock the AWS services and environment variables before importing the module. 
Use a fixture to control the import. Otherwise import errors will occur. Refer 
to the pytest documentation to change the scope of the fixture'''
module_name = 'ps_server'
@pytest.fixture()
def ps_server_module():
    yield import_module(module_name)

@pytest.fixture(scope='session', autouse=True)
def test_org_name():
    return 'unit-test-org' 
 
@pytest.fixture(scope='session', autouse=True)
def test_public_org_name():
    return 'unit-test-public' 

 # TBD use Monkeypatch to mock this in env?
@pytest.fixture(scope='session', autouse=True)
def get_S3_BUCKET():
    return os.environ.get("S3_BUCKET",'sliderule')

@pytest.fixture(scope='session', autouse=True)
def root_dir():
    return get_root_dir()


@pytest.fixture(scope="function")
def terraform_env(setup_logging, s3, get_S3_BUCKET, root_dir,  test_org_name, control_instance, request):

    '''
    This fixture will setup and teardown a terraform environment for each test function that references it
    '''

    #
    #  ----- Setup -----
    #
    logger = setup_logging
    version,is_public = request.param
    logger.info(f'fixture setup for org:{test_org_name} and version:{version} is_public:{is_public}')
    assert terraform_setup(ps_server_cntrl=control_instance, s3_client=s3, s3_bucket=get_S3_BUCKET, version=version, is_public=is_public, org_name=test_org_name, logger=setup_logging)

    yield

    #
    #  ----- TearDown -----
    #
    logger.info(f'fixture teardown for org:{test_org_name} and version:{request.param[0]} is_public:{request.param[1]}')
    assert terraform_teardown(ps_server_cntrl=control_instance, s3_client=s3, s3_bucket=get_S3_BUCKET, org_name=test_org_name, logger=setup_logging)


@pytest.fixture
def UpdateReq(test_org_name):  # You can provide a default value here if necessary

    provision_req = ps_server_pb2.UpdateRequest(
        org_name=test_org_name,
        min_nodes=1,
        max_nodes=5,
        num_nodes=3,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )

    return provision_req

@pytest.fixture
def SetUpReq(test_org_name,setup_logging,request):  # You can provide a default value here if necessary
    version = request.param[0]  # This is where you get the version from
    logger = setup_logging

    setup_request = ps_server_pb2.SetUpReq(
        org_name=test_org_name,
        version=version,  # Use the version passed to the fixture
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    return setup_request

@pytest.fixture
def TearDownReq(test_org_name,setup_logging,request):  # You can provide a default value here if necessary
    version = request.param  # This is where you get the version from
    logger = setup_logging

    td_request = ps_server_pb2.TearDownReq(
        org_name=test_org_name,
        version=version,  # Use the version passed to the fixture
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    return td_request

@pytest.fixture
def control_instance(setup_logging):
    # Create an instance of the Control class
    logger = setup_logging
    yield Control()
    logger.info(f'control_instance teardown')

@pytest.fixture(scope="session")
def s3(setup_logging, get_S3_BUCKET):
    logger = setup_logging
    # uses localstack
    s3_client = boto3.client('s3', region_name='us-west-2',endpoint_url="http://localstack:4566")
    yield s3_client
    logger.info(f'verify teardown of mocked s3 with s3_client:{s3_client} s3 bucket:{get_S3_BUCKET}')

@pytest.fixture(scope="function")
def create_tf_dir_factory(root_dir, test_org_name, ps_server_module):
    '''
        This returns a function that creates the terrform directory for the test org.
    '''
    def _create_terraform_directory(logger,test_org_name,version):
        logger.info(f'_create_terraform_directory root_dir:{root_dir}  test_org_name:{test_org_name}')
        # staged terraform files are in test_misc/cluster_tf_versions for testing only
        src = os.path.join(root_dir, 'test_misc/cluster_tf_versions', f"{version}")
        logger.info(f'src:{src}')
        assert os.path.exists(src)
        files = glob.glob(os.path.join(src, '*'))
        logger.info(f'src:{src} has cnt:{len(files)} files')
        dst = os.path.join(root_dir, test_org_name, 'terraform')
        logger.info(f'dst:{dst}')
        run_subprocess_command(['mkdir', '-p', dst], logger)  # remember we are in a container
        assert os.path.exists(dst)
        for file in files:
            logger.debug(f'copying file:{file}')
            run_subprocess_command(['cp', '-rv', file, dst], logger)
        file_to_check = os.path.join(dst, 'vpc.tf')
        logger.info(f"file_to_check:{file_to_check} exists:{os.path.exists(file_to_check)}")   
        assert os.path.exists(file_to_check)
        # now add the currently_deployed_version.txt file with version in it
        currently_deployed_version_file = os.path.join(os.path.join(root_dir, test_org_name), ps_server_module.SETUP_JSON_FILE)   
        # Open the file in write mode and write the text
        with open(currently_deployed_version_file, "w") as file:
            file.write(f"{version}")
    return _create_terraform_directory

# @pytest.fixture(scope="function")
# def cluster_is_deployed_factory(root_dir, create_tf_dir_factory, test_org_name, ps_server_module):
#     '''
#         This returns a function that when executed emulates state of the real system when a cluster is deployed 
#         This fixture will copy from the test staged directory to 
#         the directory used for deployed current cluster for the test org.
#     '''

#     def _cluster_is_deployed(logger,test_org_name,version):
#         if not os.path.exists(get_terraform_dir(test_org_name)):
#             create_tf_dir = create_tf_dir_factory # get the function from the factory
#             create_tf_dir(logger,test_org_name,version)
        
#         run_terraform_cmd(test_org_name,['init'], logger)
#         ws_list = get_tf_workspaces(logger,test_org_name)
#         logger.info(f'ws_list:{ws_list}')
#         if f'localhost-{test_org_name}' not in ws_list:
#             logger.info(f'creating workspace localhost-{test_org_name}')
#             run_terraform_cmd(test_org_name,['workspace','new', f'localhost-{test_org_name}'], logger)
#         else:
#             logger.info(f'workspace localhost-{test_org_name} already exists')
#             run_terraform_cmd(test_org_name,['workspace','select', f'localhost-{test_org_name}'], logger)

#         # community version does not support creating our cluster
#         # run_terraform_cmd(test_org_name,['apply'], logger)
#         return True
#     return _cluster_is_deployed


@pytest.fixture(scope="function")
def clean_all_workspaces(setup_logging,test_org_name,control_instance):
    '''
        This fixture cleans up all the workspaces
    '''
    logger = setup_logging
    rc, stdout, stderr = run_subprocess_command(['terraform', 'workspace', 'list'], logger)
    logger.info(f'clean_workspaces')
    retStatus = True
    if os.path.exists(f"/ps_server/{test_org_name}"):
        # clean up the workspaces for the test org
        #   get the list of workspaces
        ws_list = get_tf_workspaces(logger,test_org_name)
        for ws_name in ws_list:
            if test_org_name in ws_name:
                logger.info(f'clean_workspace: deleting workspace for org:{test_org_name}')
                return control_instance.delete_workspace_for_org(test_org_name)
        cmd_args = ['rm', '-rf', 'ps_server/{test_org_name}']
        returncode, stdout_lines, stderr_lines = run_subprocess_command(cmd_args, logger)
        if returncode != 0:
            retStatus = False
        logger.info(f'clean_workspace: returncode:{returncode} stdout_lines:{stdout_lines} stderr_lines:{stderr_lines}')    
    return retStatus

@pytest.fixture(scope="function")
def init_s3_current_cluster_tf_by_org_factory(setup_logging, s3, get_S3_BUCKET, root_dir,  test_org_name, version, ps_server_module):
    '''
        This returns a function that when executed emulates state of the real system when a cluster is deployed 
        This fixture will initialize the bucket:sliderule s3_path:prov-sys/current_cluster_tf_by_org/<version> .
    '''
    s3_client = s3
    logger = setup_logging
    s3_bucket = get_S3_BUCKET
    def _init_s3_current_cluster_tf_by_org(logger,test_org_name,version):
        src_s3_folder = f'prov-sys/cluster_tf_versions/{version}'
        dest_s3_folder = f'prov-sys/current_cluster_tf_by_org/{test_org_name}'
        assert s3_folder_exist(logger, s3_client, s3_bucket, src_s3_folder)
        try:
            assert copy_s3_objects( logger=logger,
                                    s3_client=s3_client,
                                    src_bucket=s3_bucket, 
                                    src_folder=f'prov-sys/',
                                    dest_bucket=s3_bucket, 
                                    dest_folder=dest_s3_folder)
        except Exception as e:
            logger.error(f'Exception:{e}')
            assert False
        return True
    return _init_s3_current_cluster_tf_by_org
