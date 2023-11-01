# BSD 3-Clause License
#
# Copyright (c) 2022, University of Washington
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Test client for Sliderule Provisioning System server """
from __future__ import print_function

import argparse
import contextlib
import logging

import grpc
import ps_server_pb2
import ps_server_pb2_grpc

import os

_LOGGER = logging.getLogger('__name__')
_LOGGER.setLevel(logging.INFO)

_SERVER_ADDR_TEMPLATE = "ps-server:%d"
_SIGNATURE_HEADER_KEY = "x-signature"


def _load_credential_from_file(filepath):
    real_path = os.path.join(os.path.dirname(__file__), filepath)
    with open(real_path, "rb") as f:
        return f.read()


## used certstrap
ROOT_CERTIFICATE = _load_credential_from_file("credentials/Ice2SlideRule.crt")


class AuthGateway(grpc.AuthMetadataPlugin):
    def __call__(self, context, callback):
        """Implements authentication by passing metadata to a callback.

        Implementations of this method must not block.

        Args:
          context: An AuthMetadataContext providing information on the RPC that
            the plugin is being called to authenticate.
          callback: An AuthMetadataPluginCallback to be invoked either
            synchronously or asynchronously.
        """
        # Example AuthMetadataContext object:
        # AuthMetadataContext(
        #     service_url=u'https://localhost:50051/helloworld.Greeter',
        #     method_name=u'SayHello')
        signature = context.method_name[::-1]
        callback(((_SIGNATURE_HEADER_KEY, signature),), None)


def send_rpcs(channel, name):
    try:
        sstub = ps_server_pb2_grpc.MonitorStub(channel)
        srequest = ps_server_pb2.StatusRequest(name=name)
        sresponses = sstub.StreamStatus(srequest)
        for sresponse in sresponses:
            _LOGGER.info("Status Response from server: %s", sresponse)
    except grpc.RpcError as rpc_error:
        _LOGGER.error("Status Received error: %s", rpc_error)
        return rpc_error
    else:
        _LOGGER.info("Completed Status Responses from server")


@contextlib.contextmanager
def create_client_channel(addr):
    # Call credential object will be invoked for every single RPC
    call_credentials = grpc.metadata_call_credentials(
        AuthGateway(), name="auth gateway"
    )
    # Channel credential will be valid for the entire channel
    channel_credential = grpc.ssl_channel_credentials(ROOT_CERTIFICATE)
    # Combining channel credentials and call credentials together
    composite_credentials = grpc.composite_channel_credentials(
        channel_credential,
        call_credentials,
    )
    channel = grpc.secure_channel(addr, composite_credentials)
    yield channel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", nargs="?", type=int, default=50051, help="the address of server"
    )
    parser.add_argument(
        "--cluster_name", nargs="?", type=str, help="name of the cluster"
    )

    args = parser.parse_args()

    try:
        _LOGGER.info(" port:%d name:%s", args.port, args.cluster_name)
        with create_client_channel(_SERVER_ADDR_TEMPLATE % args.port) as channel:
            send_rpcs(channel, args.cluster_name)

    except Exception as e:
        print("caught exception:", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
