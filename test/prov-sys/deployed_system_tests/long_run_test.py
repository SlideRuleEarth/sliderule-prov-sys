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


def set_onn_and_wait_for_transition(session, host, ps_username, ps_password, org_name, dnn, ttl, poll_tm, TIMEOUT):
    try:

        ###################################################
        token_url = host+'api/org_token/'
        #logger.info(f"data:{ps_username} {ps_password} {org_name}")
        logger.info(f"data:{ps_username} {org_name}")
        response = session.post(token_url, data={'username': ps_username, 'password': ps_password, 'org_name': org_name})
        json_data = response.json()
        logger.info(f"{token_url}---> rsp:{json_data}")
        token = json_data['access']

        headers = {
            'Authorization': f"Bearer {token}",
        }
        logger.info(f"Request Headers: {headers}")
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
        if response.status_code == 404:
            logger.error(f"Received 404 Not Found error for URL: {post_url}")
            return False
        try:
            json_data = response.json()
            logger.info(f"POST rsp:{json_data}")
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from response for URL: {post_url}. Response text: {response.text}")
            return False                
        ######################################
        get_url = host+f'api/org_num_nodes/{org_name}/'
        timeout = TIMEOUT # two minutes is MAX the time it should take to provision a new node
        poll_num = (timeout/poll_tm) + 1
        logger.info(f"Polling every {poll_tm} for org_num_nodes to be set to {dnn} for {timeout} seconds")
        while timeout > 0:
            response = session.get(get_url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Received {response.status_code} for URL: {get_url}")
                return False
            json_data = response.json()
            logger.info(f"Polling for current_nodes:{dnn} GET {get_url}---> rsp:{json_data} {timeout} seconds left")
            if json_data['current_nodes'] == dnn:
                logger.info(f"Successfully set org_num_nodes to {dnn} in {TIMEOUT} seconds")
                return True
            else:
                time.sleep(poll_tm) 
                poll_num -= 1 
                timeout -= poll_tm
        logger.error(f"Failed to set org_num_nodes to {dnn} in {TIMEOUT} seconds")     
        return False
    except Exception as e:
        logger.error(f"Exception:{e}")
        logger.exception(e)
        return False

def thread_target(session, host, ps_username, ps_password, org_name):
    if not set_onn_and_wait_for_transition(session=session, host=host, ps_username=ps_username,ps_password=ps_password, org_name=org_name, dnn=1, ttl=15, poll_tm=5, TIMEOUT=120):
        sys.exit(1)

def main(domain,org_names):
    try:
        ps_username = None
        ps_password = None
        session = requests.Session()
        session.trust_env = False
        org_name = 'unit-test-org'
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
            threads = []
            for org_name in org_names:  # Loop over the org_names
                t = threading.Thread(target=thread_target, args=(session, host, ps_username, ps_password, org_name))
                t.start()
                threads.append(t)
            
            # Join the threads to wait for their completion
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
