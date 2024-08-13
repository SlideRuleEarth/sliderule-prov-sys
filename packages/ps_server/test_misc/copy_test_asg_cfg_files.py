import logging
import sys
import shutil
import os
import glob

if __name__ == "__main__":
    # Setting up logger
    logger = logging.getLogger("copy_test_asg_cfg_files")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Check if the root directory is passed as an argument
    if len(sys.argv) < 2:
        logger.error("Root directory not provided. Exiting.")
        sys.exit(1)  # Exit with an error code

    # Get the root directory from the first argument
    root_dir = sys.argv[1]
    
    # Define source and destination directories using the root directory
    source_dir = os.path.join(root_dir, "test_tf_option_files/")
    destination_dir = os.path.join(root_dir, "cluster_tf_versions/test/")

    # Check if destination directory exists
    if not os.path.exists(destination_dir):
        logger.error(f"Destination directory {destination_dir} does not exist. Exiting.")
        sys.exit(1)  # Exit with a status of 1 indicating an error

    # Get list of all files in the source directory
    files = glob.glob(os.path.join(source_dir, "*"))

    for file in files:
        try:
            # Copy each file to the destination directory
            shutil.copy(file, destination_dir)
            logger.info(f"Copied {file} to {destination_dir}")
        except Exception as e:
            logger.error(f"Failed to copy {file}: {str(e)}")
