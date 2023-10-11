import grpc
import ps_server_pb2
import ps_server_pb2_grpc
import contextlib
from google.protobuf.json_format import MessageToJson
import os
from django.conf import settings

import logging

LOG = logging.getLogger('django')

def _load_credential_from_file(filepath):
    try:
        real_path = os.path.join(os.path.dirname(__file__), filepath)
        with open(real_path, 'rb') as f:
            return f.read()
    except:
        LOG.exception("caught exception when reading crt file:")
        return ''

@contextlib.contextmanager
def create_client_channel(name):
    # LOG.info("environ DEBUG:%s",os.environ.get("DEBUG"))
    # LOG.info("settings.DEBUG:%s",settings.DEBUG)
    host_str = os.environ.get("PS_SERVER_HOST", "ps-server")
    port_str = os.environ.get("PS_SERVER_PORT", "50051")
    hoststring = host_str+":"+port_str
    use_local_cert  = os.environ.get("PS_USE_LOCAL_CERT", "False")
    use_tls         = os.environ.get("PS_USE_TLS", "False")
    #LOG.info(f"GRPC ver:{grpc.__version__} Creating {name} channel with host string:{hoststring} use_local_cert?:{use_local_cert} use_tls?:{use_tls}")
    for handler in LOG.handlers:
       handler.flush()
    if use_tls == "True":
        channel_credentials = grpc.ssl_channel_credentials()
        if use_local_cert == "True":
            # we can test with a local cert by using this
            root_cert = _load_credential_from_file(os.path.join(
                settings.BASE_DIR, 'credentials/Ice2SlideRule.crt'))
            channel_credentials = grpc.ssl_channel_credentials(root_certificates=root_cert)
            #LOG.info("Secure channel:%s",hoststring)
            channel = grpc.secure_channel(hoststring, channel_credentials)
        else:
            # NOTE: for prod we use this insecure channel because the loadbalancer terminates the cert
            #LOG.info("Insecure channel:%s",hoststring)
            channel = grpc.secure_channel(hoststring, channel_credentials)
    else:
        channel = grpc.insecure_channel(hoststring)

    yield channel
