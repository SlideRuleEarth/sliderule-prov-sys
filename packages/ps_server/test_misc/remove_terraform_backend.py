import logging
import sys
import shutil
import os
import re

# def add_endpoint_to_terraform_config(filename):
#     # read the file
#     with open(filename, 'r') as file:
#         data = file.read()

#     # find the s3 backend section
#     backend_s3 = re.search(r'backend "s3" {([^}]+)}', data)

#     if backend_s3 is None:
#         print(f"No 'backend \"s3\"' section found in {filename}")
#         return

#     # check if the endpoint already exists in the s3 section
#     endpoint_line = 'endpoint = "http://s3.localhost.localstack.cloud:4566"'
#     if endpoint_line in backend_s3.group(0):
#         print(f"Endpoint already set in {filename}")
#         return

#     # insert the endpoint to this section
#     modified_s3 = backend_s3.group(0).rstrip('}') + f'\n  endpoint = "http://s3.localhost.localstack.cloud:4566"\n}}'

#     # replace the old section with the modified one
#     data = data.replace(backend_s3.group(0), modified_s3)

#     # add the comment to the data
#     script_name = os.path.basename(__file__)
#     data += f"\n# This file was edited by the Python script: {script_name}\n"

#     # write the modified data to the file
#     with open(filename, 'w') as file:
#         file.write(data)

def find_and_update(logger, search_directory, filename):
    cnt = 0
    for root, dirs, files in os.walk(search_directory):
        for file in files:
            if file == filename:
                file_path = os.path.join(root, file)
                new_file_path = os.path.join(root, f"{filename}.SAVE")
                os.rename(file_path, new_file_path)  # rename the file
                cnt += 1
                logger.info(f"Renamed: {file_path} to {new_file_path}")
    logger.info(f"Replaced {cnt} files with name: {filename}")
    return cnt


if __name__ == "__main__":
    # Assume we pass in the search directory as the first argument
    #
    #  old filename is providers.tf
    #  replacement file path is ./mock_aws_provider.tf
    search_directory        = sys.argv[1]
    filename           = "terraform.tf"

    # Setting up logger
    logger = logging.getLogger("find_and_update")
    logger.setLevel(logging.INFO)

    # replace the provider file in all subdirectories with this file
    find_and_update(logger, search_directory, 'terraform.tf')
