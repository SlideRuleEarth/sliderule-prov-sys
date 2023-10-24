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
logger = logging.getLogger(__name__)
format_str = '%(asctime)s - %(name)s - %(levelname)s - Line %(lineno)d - %(message)s'
logging.basicConfig(level=logging.INFO, format=format_str)


def main(domain):
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
                    org_name = 'UofMDTest'

                url = host+'api/org_token/'
                logger.info(f"data:{ps_username} {ps_password} {org_name}")
                response = session.post(url, data={'username': ps_username, 'password': ps_password, 'org_name': org_name})
                json_data = response.json()
                logger.info(f"{url}---> rsp:{json_data}")
                headers = {
                    'Authorization': f"Bearer {json_data['access']}",
                }
                logger.info(f"Request Headers: {headers}")

                url = host+f'api/org_num_nodes/{org_name}/'
                response = session.get(url, headers=headers)
                json_data = response.json()            
                logger.info(f"{url}---> rsp:{json_data}")
                dnn1 = 1
                ttl = 60
                url = host+f'api/desired_org_num_nodes/{org_name}/{dnn1}/{ttl}/'
                response = session.post(url, headers=headers)
                json_data = response.json()
                logger.info(f"{url}---> rsp:{json_data}")
                get_url = host+f'api/org_num_nodes/{org_name}/'
                poll_tm = 5
                timeout = 120 # two minutes is MAX the time it should take to provision a new node
                poll_num = (timeout/poll_tm) + 1
                logger.info(f"Polling for org_num_nodes to be set to {dnn1} in {poll_tm} seconds")
                while timeout > 0:
                    response = session.get(get_url, headers=headers)
                    json_data = response.json()
                    if json_data['num_nodes'] == dnn1:
                        done = True
                        logger.info(f"Successfully set org_num_nodes to {dnn1} in {timeout} seconds")
                        sys.exit(0)
                    else:
                        time.sleep(poll_tm) 
                        poll_num -= 1 
                        timeout -= poll_tm
                logger.error(f"Failed to set org_num_nodes to {dnn1} in {timeout} seconds")     
                exit(1)
            else:
                logger.error("Unable to retrieve username and password from environment or netrc file")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Exception:{e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Disable the provisioning in preparation for deploying a new provisioning system version.')
    parser.add_argument('--domain', type=str,  help='domain name e.g. localhost or testsliderule.org ')
    args = parser.parse_args()
    sys.exit(main(args.domain))
