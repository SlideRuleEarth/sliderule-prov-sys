# match the version of .venv if you have one
FROM python:3.11

# upgrade PIP 
RUN pip install --upgrade pip

# send python output to terminal immediately without buffering
ENV PYTHONUNBUFFERED=1
WORKDIR /home
RUN mkdir -p logs
RUN wget https://releases.hashicorp.com/terraform/1.3.4/terraform_1.3.4_linux_arm64.zip
RUN unzip terraform_1.3.4_linux_arm64.zip
RUN install terraform /usr/local/bin/
WORKDIR /ps_server
COPY ./stage/requirements.txt /ps_server/
RUN pip install -r requirements.txt
RUN pip freeze > requirements.freeze.txt

COPY ./stage/docker-entrypoint.sh /ps_server/
RUN chmod a+x /ps_server/docker-entrypoint.sh
COPY ./stage/ps_server.py /ps_server/
COPY ./stage/protos/ /ps_server/protos/
COPY ./stage/test_misc/ /ps_server/test_misc/
COPY ./stage/.ps_server_versions /ps_server/

EXPOSE 50051/tcp
EXPOSE 50052/tcp
RUN python -m grpc_tools.protoc -I/ps_server/protos/ --python_out=. --grpc_python_out=. /ps_server/protos/ps_server.proto
ENTRYPOINT [ "/ps_server/docker-entrypoint.sh" ]
