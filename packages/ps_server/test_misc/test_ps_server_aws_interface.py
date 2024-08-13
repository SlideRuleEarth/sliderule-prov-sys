'''ps-server unit testing'''
import boto3
import pytest
import logging
import sys
import os
import pathlib
from pathlib import Path
import uuid
import json
import pprint
from unittest.mock import patch
from google.protobuf.text_format import MessageToString
from google.protobuf import json_format
from ps_server import ps_server_pb2,upload_current_tf_files_to_s3,get_terraform_dir,download_s3_folder,delete_folder_from_s3,get_versions_for_org,sort_versions,SETUP_JSON_FILE,get_cluster_root_dir
from test_utils import run_subprocess_command, bucket_exists, s3_folder_exist,verify_rsp_generator,terraform_teardown,files_are_identical 

# discover the src directory to import the file being tested
parent_dir = pathlib.Path(__file__).parent.resolve()
src_path = os.path.join(parent_dir, '..', '')
sys.path.append(src_path)
from conftest import *

#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('v3',False),('latest',True)], indirect=True)
def test_upload_current_tf_files_to_s3(s3, get_S3_BUCKET, terraform_env, root_dir, test_name,  control_instance, setup_logging):
    '''
        This tests the upload_current_tf_files_to_s3 function in the ps_server module 
    '''
    s3_client = s3
    s3_bucket = get_S3_BUCKET
    logger = setup_logging
    assert bucket_exists(s3_client, s3_bucket)
    # test the function that uploads the test org cluster's current tf files to s3
    assert upload_current_tf_files_to_s3(s3_client,test_name)

    s3_folder = f'prov-sys/localhost/current_cluster_tf_by_org/{test_name}/'
    assert s3_folder_exist(logger, s3_client, s3_bucket, s3_folder)


    tf_dir = get_terraform_dir(test_name)
    run_subprocess_command(['rm', '-rf', tf_dir],logger)
    assert not os.path.exists(tf_dir)

    s3_folder = os.path.join('prov-sys','localhost','current_cluster_tf_by_org',test_name)

    test_download_dir = os.path.join(tf_dir,'test_download_dir')
    assert download_s3_folder(s3_client, s3_bucket, s3_folder, test_download_dir)
    assert os.path.exists(os.path.join(test_download_dir,'terraform', 'vpc.tf'))

    # clean up
    run_subprocess_command(['rm', '-rf', test_download_dir],logger)
    assert not os.path.exists(test_download_dir)


#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('v3',False),('latest',True)], indirect=True)
def test_delete_folder_from_s3(s3, get_S3_BUCKET, terraform_env, root_dir, test_name,  control_instance, setup_logging):
    '''
        This tests the delete_folder_from_s3 function in the ps_server module 
    '''
    s3_client = s3
    s3_bucket = get_S3_BUCKET
    logger = setup_logging
    assert bucket_exists(s3_client, s3_bucket)

    # test the function that uploads the test org cluster's current tf files to s3
    assert upload_current_tf_files_to_s3(s3_client,test_name)

    s3_folder = f'prov-sys/localhost/current_cluster_tf_by_org/{test_name}/'

    assert s3_folder_exist(logger, s3_client, s3_bucket, s3_folder)

    tf_dir = get_terraform_dir(test_name)
    run_subprocess_command(['rm', '-rf', tf_dir],logger)
    assert not os.path.exists(tf_dir)


    assert download_s3_folder(s3_client, s3_bucket, s3_folder, os.path.join(tf_dir,'test_download_dir'))
    assert os.path.exists(os.path.join(tf_dir,'test_download_dir','terraform','vpc.tf'))

    assert delete_folder_from_s3(s3_client, s3_bucket, s3_folder)
    assert not s3_folder_exist(logger, s3_client, s3_bucket, s3_folder)

    # clean up
    tf_dir = get_terraform_dir(test_name)
    run_subprocess_command(['rm', '-rf', tf_dir],logger)
    assert not os.path.exists(tf_dir)


#@pytest.mark.dev
@pytest.mark.parametrize('terraform_env', [('v3',False),('latest',True)], indirect=True)
def test_process_Update_cmd(s3, test_name, setup_logging, root_dir, get_S3_BUCKET, control_instance, terraform_env,UpdateReq):
    '''
        This tests the process_Update_cmd in the ps_server module
    '''

    logger = setup_logging
    s3_client = s3
    s3_bucket = get_S3_BUCKET
    assert bucket_exists(s3_client, s3_bucket)
    
    cnt,done,stop_cnt,exc_cnt,error_cnt,stdout,stderr = verify_rsp_generator(control_instance.process_Update_cmd(UpdateReq,s3_client),test_name,'Update',logger)
    logger.info(f'done with process_Update_cmd cnt:{cnt} exception_cnt:{exc_cnt} stop_exception_cnt:{stop_cnt}')
    # normal exit shows this message
    assert 'unit-test-org Update Completed' in stdout
    assert stderr==''
    assert exc_cnt==1 # localstack cannot handle the 'Update' command
    assert stop_cnt==0
    assert error_cnt==1
    assert done
    assert cnt==5 # this is the number of times the next function should be called for the 'Update' command
    # when we do an apply the s3 state file gets updated and then we need to upload the current terraform files to s3
    assert s3_folder_exist(logger, s3_client, s3_bucket, f'prov-sys/localhost/current_cluster_tf_by_org/{test_name}') 

#@pytest.mark.dev
def test_get_versions(setup_logging, s3, test_name, root_dir, get_S3_BUCKET,localstack_setup):
    '''
        This tests the get_versions function in the ps_server module
    '''

    s3_client = s3
    logger = setup_logging
    s3_bucket = get_S3_BUCKET

    s3_folder = f'prov-sys/cluster_tf_versions/latest'
    assert s3_folder_exist(logger, s3_client, s3_bucket, s3_folder)

    versions = get_versions_for_org(s3_client, test_name)
    sorted_versions = sort_versions(versions)
    logger.info(f'sorted_versions:{sorted_versions}')
    assert False if sorted_versions is None else True
    assert len(sorted_versions) > 0
    assert sorted_versions[0] == 'latest'
    assert sorted_versions[-1] == 'unstable'
    assert 'v3' in sorted_versions

#@pytest.mark.dev
def test_download_dir_when_empty(setup_logging, s3, get_S3_BUCKET):
    s3_client = s3
    logger = setup_logging
    s3_bucket = get_S3_BUCKET
    assert bucket_exists(s3_client, s3_bucket)
    assert download_s3_folder(s3_folder="prov-sys/localhost/current_cluster_tf_by_org",
                local_dir="/ps_server/",
                bucket_name=s3_bucket,
                s3_client=s3_client)

#@pytest.mark.dev
@pytest.mark.parametrize('version', ['v3'])
def test_download_dir_when_deployed(setup_logging, s3, get_S3_BUCKET, test_name, test_public_name, init_s3_current_cluster_tf_by_org_factory, control_instance, version):
    '''
        This tests the download_dir function in the ps_server module initialization.
        When we are deploying a new provisioning system the new ps_server
        needs to initialize itself with the latest terraform 
        for currently deployed clusters by downloading the terraform files from S3.
    '''

    s3_client = s3
    logger = setup_logging
    s3_bucket = get_S3_BUCKET
    assert bucket_exists(s3_client, s3_bucket)
    init_s3_current_cluster_tf_by_org = init_s3_current_cluster_tf_by_org_factory # grab the factory function for the version
    assert init_s3_current_cluster_tf_by_org(logger,test_name,version=version) # execute the factory function
    assert init_s3_current_cluster_tf_by_org(logger,test_public_name,version=version) # execute the factory function
    assert download_s3_folder(s3_folder="prov-sys/localhost/current_cluster_tf_by_org",
                local_dir="/ps_server/",
                bucket_name=s3_bucket,
                s3_client=s3_client)
    assert Path(f'/ps_server/{test_name}/vpc.tf').exists()    
    assert Path(f'/ps_server/{test_public_name}/vpc.tf').exists()

    # must leave terraform env as we found it so other tests don't fail because of this test
    assert terraform_teardown(ps_server_cntrl=control_instance, s3_client=s3, s3_bucket=get_S3_BUCKET, name=test_name, logger=setup_logging)

#@pytest.mark.dev 
@pytest.mark.parametrize(
    "version, asg_cfg", 
    [
        ('v3', ''), 
        ('latest', ''), 
        ('unstable', ''),
        ('unstable', 'None'),
        ('unstable', 'aarch64'),
        ('unstable', 'aarch64_pytorch'),
    ]
)
def test_setup_teardown_terraform_env(setup_logging, s3, get_S3_BUCKET, test_name, control_instance, version, asg_cfg):
    '''
        This tests the setup_terraform_env and teardown_terraform_env functions in the ps_server module
        The ps_server will copy the terraform files from the selected version to the terraform directory
        Then it will copy the selected asg_cfg file from sliderule-asg-<asg_cfg>.tf.OPTION to sliderule-asg.tf
        In order to verify if the proper asg_cfg is being used we cheat and add a comment at the top of the files 
        with the name of the file.  This way we can verify that the correct file was copied.
    '''
    s3_client = s3
    s3_bucket = get_S3_BUCKET
    logger = setup_logging
    assert bucket_exists(s3_client, s3_bucket)  
    assert not s3_folder_exist(logger, s3_client, s3_bucket, f'prov-sys/localhost/current_cluster_tf_by_org/{test_name}') 
    
    cnt, done, stop_cnt, exc_cnt, error_cnt, stdout, stderr = verify_rsp_generator(
        control_instance.setup_terraform_env(
            s3_client, 
            test_name, 
            version, 
            is_public=False, 
            now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%Z"), 
            spot_allocation_strategy='lowest-price', 
            spot_max_price=0.16, 
            asg_cfg=asg_cfg 
        ), 
        test_name, 
        'SetUp', 
        logger
    )
    
    logger.info(f'done with setup_terraform_env cnt:{cnt} exception_cnt:{exc_cnt} stop_exception_cnt:{stop_cnt}')
    assert 'unit-test-org SetUp Completed' in stdout
    assert stderr == ''
    assert exc_cnt == 0 
    assert stop_cnt == 0
    assert error_cnt == 0
    assert done
    assert cnt > 15

    path = f'/ps_server/{test_name}/terraform'
    returncode, stdout_lns, stderr_lns = run_subprocess_command(['ls', '-al', path], logger)
    assert returncode == 0
    logger.info(f'path:{path} stdout_lns:{stdout_lns}')
    
    in_output = any('vpc.tf' in entry for entry in stdout_lns)
    assert in_output
    assert os.path.isdir(get_cluster_root_dir(test_name))

    if version == 'unstable' and asg_cfg != 'None' and asg_cfg != '':
        assert files_are_identical(f'{path}/sliderule-asg-{asg_cfg}.tf.OPTION', f'{path}/sliderule-asg.tf')

    cnt, done, stop_cnt, exc_cnt, error_cnt, stdout, stderr = verify_rsp_generator(
        control_instance.teardown_terraform_env(s3_client, test_name),
        test_name,
        'TearDown',
        logger
    )
    
    logger.info(f'done with teardown_terraform_env cnt:{cnt} exception_cnt:{exc_cnt} stop_exception_cnt:{stop_cnt}')
    assert not os.path.isdir(get_cluster_root_dir(test_name))
    assert 'unit-test-org TearDown Completed' in stdout
    assert stderr == ''
    assert exc_cnt == 0 
    assert stop_cnt == 0
    assert error_cnt == 0
    assert done
    assert cnt == 10
