#!/usr/bin/env python3
import logging
import sys
import os
import json
import sys
import os
import netrc
import json
import argparse
import django
import requests
import time
import threading

logger = logging.getLogger(__name__)
format_str = '%(asctime)s - %(name)s - %(levelname)s - Line %(lineno)d - %(message)s'
logging.basicConfig(level=logging.INFO, format=format_str)

def state_check(session, host, token, org_name, cnn, delay_tm, poll_tm, TIMEOUT):
    '''
    This routine will delay for delay_tm minutes and then poll for the org_num_nodes to be set to cnn
    '''
    ######################################
    headers = {
        'Authorization': f"Bearer {token}",
    }
    poll_tm = 5
    poll_num = (TIMEOUT/poll_tm) + 1
    logger.info(f"------ {org_name} Waiting for for {delay_tm} minutes before polling/checking for org_num_nodes to be set to {cnn} ------")
    delay_tm_secs = delay_tm * 60
    while delay_tm_secs > 0:
        time.sleep(poll_tm)
        delay_tm_secs -= poll_tm
        logger.info(f"------ {org_name} {delay_tm_secs} seconds left before polling/checking for org_num_nodes to be set to {cnn} ------")
    timeout = TIMEOUT
    get_url = host+f'api/org_num_nodes/{org_name}/'
    while timeout > 0:
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
            delay_tm -= poll_tm
    logger.error(f"{org_name} Failed to set org_num_nodes to {cnn} in {TIMEOUT} seconds")     
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
        dnn = 1
        ttl = 60
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

def state_check_thread_target(session, host, token, org_name, cnn, delay_tm, poll_tm, TIMEOUT):
    if not state_check(session=session, host=host, token=token, org_name=org_name, cnn=cnn, delay_tm=delay_tm, poll_tm=poll_tm, TIMEOUT=TIMEOUT ):
        logger.error(f"{org_name} -- Failed to set org_num_nodes to {cnn} after {delay_tm} seconds for {TIMEOUT}")
        sys.exit(1)

def run_test_case(threads, session, ps_username, ps_password, host, org_names, dnn_ttl_set_tuples, cnn_delay_check_tuples, poll_tm, TIMEOUT):
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
            t = threading.Thread(target=state_check_thread_target, args=(session, host, token, org_name, cnn, delay_tm, poll_tm, TIMEOUT))
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
            dnn_ttl_set_tuples = [(1,30),(2,20),(3,15)] # list of desired num node and time to live tuples
            cnn_delay_check_tuples = [(3,0),(2,15),(1,20),(0,30)] # predicted transitions of cnn and times
            TIMEOUT = 120 # two minutes is MAX the time it should take to transition to a new num nodes
            poll_tm = 5 # poll every 5 seconds for transition
            # Join the threads to wait for their completion
            run_test_case(  threads=threads, 
                            session=session, 
                            ps_username=ps_username,
                            ps_password=ps_password,
                            host=host,
                            org_names=org_names, 
                            dnn_ttl_set_tuples=dnn_ttl_set_tuples,
                            cnn_delay_check_tuples=cnn_delay_check_tuples, 
                            poll_tm=poll_tm, 
                            TIMEOUT=TIMEOUT)
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Disable the provisioning in preparation for deploying a new provisioning system version.')
    parser.add_argument('--domain', type=str,  help='domain name e.g. localhost or testsliderule.org ')
    parser.add_argument('--org_names', type=str, nargs='+', default=['unit-test-org'], help='org names e.g. UofMDTest or unit-test-org. You can provide multiple names separated by space.')  
    args = parser.parse_args()
    sys.exit(main(args.domain, args.org_names)) 
