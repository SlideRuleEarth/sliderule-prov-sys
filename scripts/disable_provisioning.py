#!/usr/bin/env python3
import sys
import os
import netrc
import json
import time
import requests
import logging
import argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def main(domain, mfa_code):

    if mfa_code == 'skip': # Check if mfa_code is blank
        logger.info("skipping disable_provisioning") # Log the message
        return 0 # Exit with success code

    ps_username = None
    ps_password = None
    session = requests.Session()
    session.trust_env = False
    ps_url = domain
    if not domain == 'localhost':
        ps_url = "ps." + domain
    request_timeout = (10, 20) # (connection, read) in seconds

    # attempt retrieving from environment
    if not ps_username or not ps_password:
        ps_username = os.environ.get("PS_USERNAME")
        ps_password = os.environ.get("PS_PASSWORD")

    # attempt retrieving from netrc file
    if not ps_username or not ps_password:
        try:
            netrc_file = netrc.netrc()
            login_credentials = netrc_file.hosts[ps_url]
            ps_username = login_credentials[0]
            ps_password = login_credentials[2]
        except Exception as e:
            logger.warning("Unable to retrieve username and password from netrc file for machine: {}".format(e))
            sys.exit(1)

        # send authentication creds with request to provisioning system
        if ps_username and ps_password:
            try:
                rqst = {"username": ps_username, "password": ps_password, "mfa_code": mfa_code}
                headers = {'Content-Type': 'application/json'}
                if domain == 'localhost':
                    host = "http://localhost/api/disable_provisioning/"
                else:
                    host = "https://ps." + domain + "/api/disable_provisioning/"
                rsps = session.put(host, data=json.dumps(rqst), headers=headers, timeout=request_timeout)
                logger.info(' Provisioning system returned => {}'.format(rsps))
                try:
                    rsps_body = rsps.json()
                except json.JSONDecodeError:
                    logger.error(f' Failed to decode JSON response')
                    return 1
                except Exception as e:
                    logger.error(f' Failed to decode JSON response got "{e}"')
                    return 1
                rsps.raise_for_status()
                logger.info(' Provisioning system returned => {}'.format(rsps_body))
                # Check for alternate_port in response and print it to stdout
                alternate_port = rsps_body.get("alternate_port", None)
                if alternate_port:
                    print(alternate_port)
                    return 0
                else:
                    logger.error(f' Missing alternate_port => {rsps_body}')
                    print("50052")
                    return 0
            except requests.exceptions.HTTPError as e:
                logger.error(f' Provisioning system returned:{e} ===> Status:{rsps.status_code} {rsps_body["error_msg"]}')
                return 1
            except requests.exceptions.ConnectionError as e:
                logger.error(f' Provisioning system return ConnectionError ===> {e}')
                return 1
            except Exception as e:
                logger.error(f'Unexpected error occurred with {ps_username}: {e}')
                return 1
        else:
            logger.error(f"Unable to retrieve valid credentials from environment or netrc file. read username:{ps_username} and password:{ps_password} ")
            return 1
    return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Disable the provisioning in preparation for deploying a new provisioning system version.')
    parser.add_argument('--domain', type=str, required=True, help='domain name e.g. testsliderule.org or slideruleearth.io')
    parser.add_argument('--mfa_code', type=str, required=True, help='mfa code')
    args = parser.parse_args()
    sys.exit(main(args.domain, args.mfa_code))
