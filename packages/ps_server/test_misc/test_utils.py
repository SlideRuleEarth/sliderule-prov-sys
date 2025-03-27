import os
import shutil

import subprocess
import pprint
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from google.protobuf.json_format import MessageToDict
from google.protobuf import json_format
from datetime import date, datetime, timedelta, timezone, tzinfo
import hashlib

import time
import requests

import subprocess


def get_root_dir():
    return '/ps_server'

def get_terraform_dir(test_name):
    return os.path.join(get_root_dir(), test_name, 'terraform')

def chdir_parm(test_name):
    return f"-chdir={get_terraform_dir(test_name)}"

def get_cluster_root_dir(name):
    return os.path.join(get_root_dir(),name)

def run_subprocess_command(cmd, logger):
    """
    Run a command in a subprocess, and return the output.

    :param cmd: The command to run, as a list of strings.
    :return: None
    :raises: subprocess.CalledProcessError if the command returns a non-zero exit status.
    """
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        stdout_lines = None
        stderr_lines = None
        if stdout:
            stdout_str = stdout.decode().strip()
            stdout_lines = stdout_str.splitlines()
            logger.info('\n'.join(stdout_lines))
        if stderr:
            stderr_str = stderr.decode().strip()
            stderr_lines = stderr_str.splitlines()
            logger.error('\n'.join(stderr_lines))
        if process.returncode != 0:
            raise subprocess.CalledProcessError(returncode=process.returncode, cmd=cmd)
    except subprocess.CalledProcessError as e:
        stdout_message = '\n'.join(stdout_lines) if stdout_lines else ""
        stderr_message = '\n'.join(stderr_lines) if stderr_lines else ""
        logger.error(f"FAILED with error: {e} stdout:{stdout_message} stderr:{stderr_message}")
        raise
    logger.info(f"SUCCESS: {cmd}")
    return process.returncode, stdout_lines, stderr_lines

def run_terraform_cmd(test_name, tf_cmd_args, logger):
    """
    Run a terraform command in a subprocess, and return the output.

    :param cmd: The command to run, as a list of strings.
    :return: None
    :raises: subprocess.CalledProcessError if the command returns a non-zero exit status.
    """
    cmd = ['tflocal',chdir_parm(test_name)]
    cmd.extend(tf_cmd_args)
    logger.info(f"Running terraform command: {cmd} using {chdir_parm(test_name)}")
    return run_subprocess_command(cmd, logger)

def bucket_exists(s3_client,bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False

def s3_folder_exist(logger,s3_client, bucket_name, s3_folder):
    """
    Check if a folder exists in an S3 bucket
    Args:
        bucket_name: the name of the s3 bucket
        s3_folder: the folder path in the s3 bucket
    Returns:
        boolean: True if folder exists, False otherwise
    """
    
    # Ensure the folder path ends with '/'
    if not s3_folder.endswith('/'):
        s3_folder += '/'
    
    result = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=s3_folder)
    ret = 'Contents' in result
    if ret:
        # Use pprint.pformat to get a formatted string
        contents_str = pprint.pformat(result['Contents'])
        #logger.info(f'Bucket:{bucket_name} contains folder:{s3_folder} with contents:\n{contents_str}')
        logger.info(f'Bucket:{bucket_name} contains folder:{s3_folder}')
    else:
        logger.info(f'Bucket:{bucket_name} DOES NOT contain folder:{s3_folder}')
    return ret

def upload_folder_to_s3(logger,s3_client, bucket_name, local_directory, s3_folder):
    """
    Uploads the contents of a local directory to an S3 bucket
    Args:
        bucket_name: the name of the s3 bucket
        local_directory: a relative or absolute directory path in the local file system
        s3_folder: the folder path in the s3 bucket
    """
    logger.info(f"Uploading {local_directory} to bucket {bucket_name} in folder {s3_folder}")
    uploaded = False
    cnt = 0
    for root, dirs, files in os.walk(local_directory):
        logger.debug(f"root:{root} dirs:{dirs} files:{files}")
        for file in files:
            local_file = os.path.join(root, file)
            relative_path = os.path.relpath(local_file, local_directory)
            s3_file = os.path.join(s3_folder, relative_path)
            logger.debug(f"Uploading {local_file} to {s3_file} in bucket {bucket_name}")
            try:
                s3_client.upload_file(local_file, bucket_name, s3_file)
                uploaded = True
                cnt = cnt + 1
                logger.debug(f"Uploaded {local_file} to {s3_file} in bucket {bucket_name}")
            except NoCredentialsError:
                logger.error("No AWS credentials found")
                uploaded = False
    logger.info(f"Finished uploading {cnt} files from {local_directory} to bucket {bucket_name} in folder {s3_folder}" if uploaded else f"FAILED to upload {local_directory} to bucket {bucket_name} in folder {s3_folder}") 

    assert s3_folder_exist(logger, s3_client, bucket_name, s3_folder)
    logger.info(f"Verified s3 folder {s3_folder} exists in bucket {bucket_name}")
    s3_sub_folder = f'{s3_folder}latest'
    assert s3_folder_exist(logger, s3_client, bucket_name, s3_sub_folder)
    logger.info(f"Verified s3 folder {s3_sub_folder} exists in bucket {bucket_name}")   
    return uploaded

def count_subdirectories(directory):
    subdir_count = 0

    # Iterate over the entries in the directory
    for entry in os.scandir(directory):
        if entry.is_dir():
            subdir_count += 1

    return subdir_count

def get_tf_workspaces(logger,test_name):
    '''
        Gets the list of workspaces for the test org
    '''
    # get the list of workspaces
    cmd_args = ['tflocal', chdir_parm(test_name), "workspace", "list"]
    workspaces = []
    rc,stdout_lns,stderr_lns = run_subprocess_command(cmd_args, logger)
    #logger.info(f'rc:{rc}')
    assert rc == 0

    #logger.info(f'stdout_lns:{stdout_lns}') 
    #logger.info(f'stderr_lns:{stderr_lns}')
    assert stderr_lns is None
    for line in stdout_lns:
        logger.info(f'line:{line}')
        # the currently selected workspace name is preceded by '* '
        ws = line.lstrip("* ")
        workspaces.append(ws.strip())    
    #logger.info(f'workspaces:{workspaces}')
    return workspaces

def delete_workspace(logger, test_name, ws_name):
    tf_cmd_args = ["workspace", "select", "default"]
    run_terraform_cmd(tf_cmd_args, logger)
    tf_cmd_args = ["workspace", "delete", f'{ws_name}']
    run_terraform_cmd(tf_cmd_args, logger)
    return True

def copy_s3_objects(logger, s3_client, src_bucket, src_folder, dest_bucket, dest_folder):
    # Use paginator to handle more than 1000 objects
    # Use paginator to handle more than 1000 objects
    paginator = s3_client.get_paginator('list_objects_v2')

    # List all objects in the source bucket
    pages = paginator.paginate(Bucket=src_bucket, Prefix=src_folder)
    num_objects = 0
    # Loop through each page
    for page in pages:
        # Loop through each object
        for object in page.get('Contents', []):
            # Get the object key
            src_key = object['Key']
            # Get the base file name from the source key
            file_name = os.path.basename(src_key)
            # Create the destination key
            dest_key = os.path.join(dest_folder, file_name)
            # Copy the object to the new key
            s3_client.copy_object(Bucket=dest_bucket, CopySource={'Bucket': src_bucket, 'Key': src_key}, Key=dest_key)
            num_objects += 1
            #logger.info(f'Copied s3://{src_bucket}/{src_key} to s3://{dest_bucket}/{dest_key}')
    logger.info(f'Copied {num_objects} objects from s3://{src_bucket}/{src_folder} to s3://{dest_bucket}/{dest_folder}')
    return True

def delete_folder_from_s3(logger, s3_client, bucket, s3_folder):
    """
    Delete the contents of a folder from an S3 bucket
    Args:
        s3_client: S3 client to interact with AWS
        bucket_name: the name of the s3 bucket
        s3_folder: the folder path in the s3 bucket
    """
    logger.info(f"Deleting s3_folder:{s3_folder} in bucket:{bucket} ")
    deleted = False
    try:
        # Add trailing slash if not present
        if not s3_folder.endswith('/'):
            s3_folder += '/'

        # List all objects under the given S3 folder
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=s3_folder
        )

        # If there are no objects under the given S3 folder
        if response['KeyCount'] == 0:
            return False

        # Construct list of keys to delete
        objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]

        # Delete the objects
        s3_client.delete_objects(
            Bucket=bucket,
            Delete={'Objects': objects_to_delete}
        )
        deleted = True
    except Exception as e:
        logger.exception(f"FAILED to delete {s3_folder} from to bucket {bucket}")
    return deleted

def verify_rsp_generator(rrsp_gen, name, ps_cmd,  logger):
    '''
    process the response generator
    '''
    done = False
    cnt = 0
    exception_cnt = 0
    stop_exception_cnt = 0
    ps_error_cnt = 0
    while(not done):
        try:
            cnt += 1
            rrsp = next(rrsp_gen)  # grab the next one and process it
            logger.info(f" {ps_cmd} CNT:{cnt} {json_format.MessageToJson(rrsp, always_print_fields_with_no_presence=True)}")
            logger.info(f'rrsp.cli.valid: {rrsp.cli.valid}')
            logger.info(f'rrsp.cli.updating: {rrsp.cli.updating}')
            logger.info(f'rrsp.cli.cmd_args: {rrsp.cli.cmd_args}')
            logger.info(f'rrsp.cli.stdout: {rrsp.cli.stdout}')
            logger.info(f'rrsp.cli.stderr: {rrsp.cli.stderr}')
            assert rrsp.ps_cmd == ps_cmd
            assert rrsp.name == name
            assert hasattr(rrsp.cli, 'stderr')
            assert hasattr(rrsp.cli, 'stdout')
            assert (rrsp.cli.valid and not rrsp.ps_server_error)
            assert rrsp.cli.updating
            if rrsp.done:
                done = True
                logger.info(f"rrsp.done:{rrsp.done}")
        except StopIteration:
            done = True
            stop_exception_cnt += 1
            logger.error(f'StopIteration at cnt:{cnt}? Should be able to read until get rrsp.done:True')    
        except Exception as ex:
            exception_cnt += 1
            logger.error(f'Exception at cnt:{cnt} e:{ex} ')
        finally:
            logger.info(f'cnt:{cnt} exception_cnt:{exception_cnt} stop_exception_cnt:{stop_exception_cnt}')
            if rrsp.ps_server_error:
                ps_error_cnt += 1
                logger.error(f"rrsp.error_msg:{rrsp.error_msg}")
    return cnt,rrsp.done,stop_exception_cnt,exception_cnt,ps_error_cnt,rrsp.cli.stdout,rrsp.cli.stderr

def terraform_setup(ps_server_cntrl, s3_client, s3_bucket, version, is_public, name, logger):

    assert bucket_exists(s3_client, s3_bucket)
    rrsp_gen = ps_server_cntrl.setup_terraform_env(s3_client=s3_client,name=name,version=version,is_public=is_public,now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%Z"),spot_allocation_strategy='lowest-price',spot_max_price=0.17,asg_cfg='None',availability_zone='us-west-2a')

    cnt,done,stop_cnt,exc_cnt,error_cnt,stdout,stderr = verify_rsp_generator(rrsp_gen,name,'SetUp',logger)

    logger.info('done with terraform_env test')
    logger.info(f'cnt:{cnt} exception_cnt:{exc_cnt} stop_exception_cnt:{stop_cnt}')
    # normal exit shows this message
    assert exc_cnt==0 
    assert stop_cnt==0
    assert error_cnt==0
    assert done
    #assert ((cnt==22) or (cnt==16)) # this is the number of times rsp generator should be called for the 'SetUp' command either 22 or 16 depending on if it exists already
    assert cnt > 15
    s3_folder = f'prov-sys/cluster_tf_versions/{version}/'
    assert s3_folder_exist(logger, s3_client, s3_bucket, s3_folder)

    path = f'/ps_server/{name}/terraform'
    returncode,stdout_lns,stderr_lns = run_subprocess_command(['ls', '-al', path],logger)
    assert returncode == 0
    logger.info(f'path:{path} stdout_lns:{stdout_lns}')
    # Iterate over the list and check for the substring
    in_output = False
    for entry in stdout_lns:
        if 'vpc.tf' in entry:
            in_output = True
    assert in_output
    return True

def terraform_teardown(ps_server_cntrl, s3_client, s3_bucket, name, logger):

    rrsp_gen = ps_server_cntrl.teardown_terraform_env(s3_client,name)
    done = False
    cnt = 0
    exception_cnt = 0
    stop_exception_cnt = 0
    ps_error_cnt = 0
    while(not done):
        try:
            rrsp = next(rrsp_gen)  # grab the next one and process it
            assert rrsp is not None
            assert rrsp.ps_cmd == 'TearDown'
            logger.info(json_format.MessageToJson(rrsp, always_print_fields_with_no_presence=True))
            logger.info(f'rrsp.cli.valid: {rrsp.cli.valid}')
            logger.info(f'rrsp.cli.updating: {rrsp.cli.updating}')
            logger.info(f'rrsp.cli.cmd_args: {rrsp.cli.cmd_args}')
            logger.info(f'rrsp.cli.stdout: {rrsp.cli.stdout}')
            logger.info(f'rrsp.cli.stderr: {rrsp.cli.stderr}')
            assert rrsp.ps_cmd == 'TearDown'
            assert rrsp.name == name
            assert hasattr(rrsp.cli, 'stderr')
            assert hasattr(rrsp.cli, 'stdout')
            assert (rrsp.cli.valid and not rrsp.ps_server_error)
            assert rrsp.cli.updating
            if rrsp.done:
                done = True
                logger.info(f"rrsp.done:{rrsp.done} at cnt:{cnt}")
        except StopIteration:
            done = True
            stop_exception_cnt += 1
            logger.error(f'StopIteration at cnt:{cnt}? Should be able to read until get rrsp.done:True')    
        except Exception as ex:
            exception_cnt += 1
            logger.error(f'Exception at cnt:{cnt} e:{repr(ex)} ')
        finally:
            logger.info(f'cnt:{cnt} exception_cnt:{exception_cnt} stop_exception_cnt:{stop_exception_cnt}')
            if cnt > 0 and rrsp is not None and rrsp.ps_server_error:
                ps_error_cnt += 1
                logger.error(f"rrsp.error_msg:{rrsp.error_msg}")
            cnt += 1

    assert cnt > 0

    assert not os.path.isdir(get_cluster_root_dir(name))
    assert not s3_folder_exist(logger, s3_client, s3_bucket, f'prov-sys/localhost/current_cluster_tf_by_org/{name}') 
    logger.info(f'cnt:{cnt} exception_cnt:{exception_cnt} stop_exception_cnt:{stop_exception_cnt}')
    logger.info(f'Done teardown: terraform_env org:{name}')
    assert exception_cnt==0
    return True


def upload_file_to_s3(s3_client, bucket_name, local_file, s3_folder, logger):
    """
    Uploads a local file to an S3 bucket.
    
    Args:
        s3_client: boto3 s3 client instance
        bucket_name: the name of the s3 bucket
        local_file: path to the local file you wish to upload
        s3_folder: the folder path in the s3 bucket
    """
    
    logger.info(f"Uploading {local_file} to bucket {bucket_name} in folder {s3_folder}")
    uploaded = False
    try:
        relative_path = os.path.basename(local_file)
        s3_file = os.path.join(s3_folder, relative_path)

        s3_client.upload_file(local_file, bucket_name, s3_file)
        uploaded = True
        logger.info(f"Uploaded {local_file} to {s3_file} in bucket {bucket_name}")

    except NoCredentialsError:
        logger.error("No AWS credentials found")
        uploaded = False
    except Exception as e:
        logger.exception(f"FAILED to upload {local_file} to bucket {bucket_name} in folder {s3_folder}")
        uploaded = False

    if uploaded:
        logger.info(f"Finished uploading {local_file} to bucket {bucket_name} in folder {s3_folder}")
    else:
        logger.error(f"FAILED to upload {local_file} to bucket {bucket_name} in folder {s3_folder}")
    
    return uploaded

def upload_json_string_to_s3(s3_client, s3_bucket, json_string, s3_key,logger):
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

def have_same_elements(list1, list2):
    return set(list1) == set(list2)


def files_are_identical(file1_path, file2_path):
    def compute_md5(file_path):
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    return compute_md5(file1_path) == compute_md5(file2_path)

