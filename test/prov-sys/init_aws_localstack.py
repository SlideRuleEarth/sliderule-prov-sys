#!/usr/bin/env python3

import boto3
import logging
import os
from botocore.exceptions import NoCredentialsError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = boto3.session.Session()

s3 = session.client(
    's3',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    region_name='us-west-2',
    endpoint_url='http://localstack:4566',
)

def re_create_s3_bucket(bucket_name):
    try:
        s3.head_bucket(Bucket=bucket_name)
        logger.info(f"Bucket {bucket_name} already exists")

        logger.info(f"Emptying bucket: {bucket_name}")
        paginator = s3.get_paginator('list_objects')
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                for obj in page['Contents']:
                    s3.delete_object(Bucket=bucket_name, Key=obj['Key'])

        logger.info(f"Deleting bucket: {bucket_name}")
        s3.delete_bucket(Bucket=bucket_name)
        logger.info(f"Deleted bucket: {bucket_name}")
    except boto3.exceptions.botocore.exceptions.ClientError:
        # The bucket does not exist or you have no access.
        pass
    logger.info(f"Creating new S3 bucket: {bucket_name}")
    response = s3.create_bucket(Bucket=bucket_name,CreateBucketConfiguration={'LocationConstraint': 'us-west-2'})
    #logger.info(f"Created new S3 bucket with response: {response}")
    return response

def upload_file_to_s3(bucket_name, local_file, s3_file):
    try:
        logger.info(f"uploading {local_file} to bucket:{bucket_name} s3_path:{s3_file}")
        s3.upload_file(local_file, bucket_name, s3_file)
        logger.debug(f"Uploaded {s3_file}")
    except NoCredentialsError:
        logger.error("AWS credentials not found!")
        return 


def upload_all_version_files_for_test_setup(bucket_name, local_directory, bucket_folder):
    cnt = 0
    base_dir_name = os.path.basename(local_directory)
    logger.info(f"Upload files to s3://{bucket_name}/{bucket_folder}/{base_dir_name}/")
    for root, dirs, files in os.walk(local_directory):
        #logger.info(f"root:{root} dirs:{dirs} files:{files}")
        for file in files:
            local_file = os.path.join(root, file)
            relative_path = os.path.join(base_dir_name, os.path.relpath(local_file, local_directory)).replace("\\", "/")
            s3_file = os.path.join(bucket_folder, relative_path)
            upload_file_to_s3(bucket_name, local_file, s3_file)
            cnt += 1
    return cnt

def upload_to_current_version_for_test_setup(bucket_name, local_directory, bucket_folder):
    cnt = 0
    logger.info(f"Upload files to s3://{bucket_name}/{bucket_folder}/")
    for root, dirs, files in os.walk(local_directory):
        for file in files:
            local_file = os.path.join(root, file)
            s3_file = os.path.join(bucket_folder, file)
            upload_file_to_s3(bucket_name, local_file, s3_file)
            cnt += 1
    return cnt

def main():
    bucket_name = 'sliderule'
    response = re_create_s3_bucket(bucket_name)
    #logger.info(f"Created S3 bucket with response: {response}")
    logger.info(f"Created S3 bucket:{bucket_name} from cwd:{os.getcwd()}")

    local_directory = os.getenv('S3_TEST_FILES')
    if local_directory is None or local_directory == "":
        raise Exception("S3_TEST_FILES environment variable is not set")
    bucket_folder = 'prov-sys'
    cnt = upload_all_version_files_for_test_setup(bucket_name, local_directory, bucket_folder)
    logger.info(f"Uploaded {cnt} files from {local_directory} to {bucket_name}/{bucket_folder}...")

    #
    # Now upload files to mimic the currently running cluster called devtest
    #
    logger.info(f"Now upload files to mimic the currently running cluster called devtest")
    bucket_folder = f'prov-sys/localhost/current_cluster_tf_by_org/devtest/terraform'
    base_directory = os.getenv('S3_TEST_FILES') # these are by version
    local_directory = os.path.join(base_directory, 'latest')
    if local_directory is None or local_directory == "":
        raise Exception(f"terraform files not found in {local_directory}")
    cnt = upload_to_current_version_for_test_setup(bucket_name, local_directory, bucket_folder)
    logger.info(f"Uploaded {cnt} files from {local_directory} to {bucket_name}/{bucket_folder}...")

    currently_deployed_version_file = os.path.join('/tmp', 'currently_deployed_tf_version.txt')   
    # Open the file in write mode and write the text
    with open(currently_deployed_version_file, "w") as file:
        file.write(f"latest")
    current_folder = f'prov-sys/localhost/current_cluster_tf_by_org/devtest'
    upload_file_to_s3(bucket_name, currently_deployed_version_file, f'{current_folder}/currently_deployed_tf_version.txt')
    logger.info(f"Done")

if __name__ == "__main__":
    main()