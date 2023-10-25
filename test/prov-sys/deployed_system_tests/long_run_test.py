#!/usr/bin/env python3
import sys
import os
import netrc
import json
import argparse
import requests
import time
import threading
import logging


def state_check(session, host, token, org_name, cnn, delay_tm, poll_tm, timeout):
    '''
    This routine will delay for delay_tm minutes and then poll for the org_num_nodes to be set to cnn
    '''
    ######################################
    headers = {
        'Authorization': f"Bearer {token}",
    }
    poll_tm = 5
    poll_num = (timeout/poll_tm) + 1
    logger.info(f"------ {org_name} Waiting for for {delay_tm} minutes before polling/checking for org_num_nodes to be set to {cnn} ------")
    delay_tm_secs = delay_tm * 60
    while delay_tm_secs > 0:
        time.sleep(poll_tm)
        delay_tm_secs -= poll_tm
        logger.info(f"------ {org_name} {delay_tm_secs} seconds left before polling/checking for org_num_nodes to be set to {cnn} ------")
    get_url = host+f'api/org_num_nodes/{org_name}/'
    current_timeout = timeout
    while current_timeout > 0:
        response = session.get(get_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"{org_name} Received {response.status_code} for GET: {get_url}")
            return False
        json_data = response.json()
        logger.info(f"{org_name} Polling for current_nodes:{cnn} GET {get_url}---> rsp:{json_data} {delay_tm} seconds left")
        if json_data['current_nodes'] == cnn:
            logger.info(f"------ {org_name} Successfully set org_num_nodes to {cnn} in {delay_tm} seconds ------")
            return True
        else:
            time.sleep(poll_tm) 
            poll_num -= 1 
            current_timeout -= poll_tm
    logger.error(f"{org_name} Failed to set org_num_nodes to {cnn} in {timeout} seconds")     
    return False

def set_dnns(session, host, token, org_name, dnn, ttl):
    '''
    This routine will set the desired number of nodes to dnn for org_name for ttl seconds
    '''
    try:
        headers = {
            'Authorization': f"Bearer {token}",
        }
        ###################################################
        get_url = host+f'api/org_num_nodes/{org_name}/'
        response = session.get(get_url, headers=headers)
        json_data = response.json()            
        logger.info(f"GET {get_url}---> rsp:{json_data}")
        ######################################
        post_url = host+f'api/desired_org_num_nodes_ttl/{org_name}/{dnn}/{ttl}/'
        logger.info(f"POST {post_url}")
        response = session.post(post_url, headers=headers)
        logger.info(f"Received status_code:{response.status_code} for URL: {post_url}")
        try:
            json_data = response.json()
            logger.info(f"{org_name} -- POST rsp:{json_data}")
            if response.status_code == 200:
                return True
        except json.JSONDecodeError:
            logger.error(f"{org_name} -- Failed to decode JSON from response for URL: {post_url}. Response text: {response.text}")
            return False                
    except Exception as e:
        logger.error(f"{org_name} --Exception:{e}")
        logger.exception(e)
        return False

def set_dnns_thread_target(session, host, token, org_name, dnn, ttl):
    if not set_dnns(session=session, host=host, token=token, org_name=org_name, dnn=dnn, ttl=ttl):
        logger.error(f"{org_name} -- Failed to make request for org_num_nodes to {dnn} for {ttl} seconds")
        sys.exit(1)

def state_check_thread_target(session, host, token, org_name, cnn, delay_tm, poll_tm, timeout):
    if not state_check(session=session, host=host, token=token, org_name=org_name, cnn=cnn, delay_tm=delay_tm, poll_tm=poll_tm, timeout=timeout ):
        logger.error(f"{org_name} -- Failed to set org_num_nodes to {cnn} after {delay_tm} seconds for {timeout}")
        sys.exit(1)

def run_test_case(threads, session, ps_username, ps_password, host, org_names, dnn_ttl_set_tuples, cnn_delay_check_tuples, poll_tm, timeout):
    for org_name in org_names:  # Loop over the org_names set identical dnn and ttl for each org_name

        ###################################################
        token_url = host+'api/org_token/'
        #logger.info(f"data:{ps_username} {ps_password} {org_name}")
        logger.info(f"username:{ps_username} org_name:{org_name}")
        response = session.post(token_url, data={'username': ps_username, 'password': ps_password, 'org_name': org_name})
        json_data = response.json()
        logger.info(f"{token_url}---> rsp:{json_data}")
        token = json_data['access']


        for dnn, ttl in dnn_ttl_set_tuples:
            t = threading.Thread(target=set_dnns_thread_target, args=(session, host, token, org_name, dnn, ttl))
            t.start()
            threads.append(t)
        for cnn, delay_tm in cnn_delay_check_tuples:
            t = threading.Thread(target=state_check_thread_target, args=(session, host, token, org_name, cnn, delay_tm, poll_tm, timeout))
            t.start()
            threads.append(t)

def main(domain,org_names):

    try:
        ps_username = None
        ps_password = None
        session = requests.Session()
        session.trust_env = False
        if not domain:
            domain = 'localhost'
        paritial_url = domain
        if not domain == 'localhost':
            paritial_url = "ps." + domain

        # attempt retrieving from environment
        if not ps_username or not ps_password:
            ps_username = os.environ.get("PS_USERNAME")
            ps_password = os.environ.get("PS_PASSWORD")

        # attempt retrieving from netrc file
        if not ps_username or not ps_password:
            try:
                netrc_file = netrc.netrc()
                login_credentials = netrc_file.hosts[paritial_url]
                ps_username = login_credentials[0]
                ps_password = login_credentials[2]
            except Exception as e:
                logger.warning("Unable to retrieve username and password from netrc file for machine: {}".format(e))
                sys.exit(1)

        # send authentication creds with request to provisioning system
        if ps_username and ps_password:
            if domain == 'localhost':
                host = f"http://{paritial_url}/"
            else:
                host = f"https://{paritial_url}/"

            ###################################################
            threads = []
            # Join the threads to wait for their completion
            run_test_case(  threads=threads, 
                            session=session, 
                            ps_username=ps_username,
                            ps_password=ps_password,
                            host=host,
                            org_names=ORG_NAMES, 
                            dnn_ttl_set_tuples=DNN_TTL_SET_TUPLES,
                            cnn_delay_check_tuples=CNN_DELAY_CHECK_TUPLES, 
                            poll_tm=POLL_TM, 
                            timeout=TIMEOUT)
            for t in threads:
                t.join()
            logger.info("Done!")
            sys.exit(0) # exit after all threads have completed

        else:
            logger.error("Unable to retrieve username and password from environment or netrc file")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Exception:{e}")
        logger.exception(e)
        sys.exit(1)

def load_test_case_params(test_case_name):
    with open("long_run_test_cfgs.json", "r") as f:
        config = json.load(f)

    for test_case in config["test_cases"]:
        if test_case["name"] == test_case_name:
            return test_case

    raise ValueError(f"No test case found with the name {test_case_name}")


if __name__ == "__main__":

    # Step 1: Get the current script's filename without extension
    log_filename = os.path.splitext(os.path.basename(__file__))[0] + ".log"

    # Set up the logger 
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_filename)  # Using the dynamic filename

    # Specify a format
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d:%(funcName)s] [%(message)s]",
        datefmt="%Y-%m-%d:%H:%M:%S",
    )    
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    parser = argparse.ArgumentParser(description='test processing of desired_org_num_nodes_ttl with various orgs and dnn/ttl values')
    parser.add_argument('--test_case', type=str, required=True, help='Test case name as defined in long_run_test_cfgs.json')
    args = parser.parse_args()

    # Load the test case parameters
    test_case_params = load_test_case_params(args.test_case)
    DNN_TTL_SET_TUPLES = test_case_params["DNN_TTL_SET_TUPLES"]
    CNN_DELAY_CHECK_TUPLES = test_case_params["CNN_DELAY_CHECK_TUPLES"]
    TIMEOUT = test_case_params["TIMEOUT"] # max time to wait for a transition to occur
    POLL_TM = test_case_params["POLL_TM"] # polling time to check for transition in seconds
    ORG_NAMES = test_case_params["ORG_NAMES"]  # Load org_names from the test case
    DOMAIN = test_case_params["DOMAIN"]  # Load domain from the test case
    sys.exit(main(DOMAIN,ORG_NAMES))