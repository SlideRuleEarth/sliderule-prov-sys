# sliderule-ps-server
sliderule-ps-server is a [gRpc](https://grpc.io/) server with services that provision infrastructure to [AWS](https://aws.amazon.com/) using [Terraform](https://www.terraform.io/) modules created for [SlideRule Earth](https://slideruleearth.io/). SlideRule Earth provisions these clusters which provide computing resources for users of their system. These different clusters are provisioned for separate organizations. 

sliderule-ps-server works in tandem with [sliderule-ps-web](https://github.com/ICESat2-SlideRule/sliderule-ps-web) which is a website that provides an interface to provision and manage multiple organizations, clusters and users. This system allows for cost tracking of different organizations' infrastructure within a single amazon account.


Detailed [documentation](https://slideruleearth.io/rtd/user_guide/prov-sys.html) on using sliderule-ps-server via sliderule-ps-web can be found at [SlideRule Earth](https://slideruleearth.io).

## Development environment
* To build this project it is assumed you have:
    * Docker desktop installed (https://www.docker.com/) which enables docker buildkit OR that you build explicitly with buildkit (https://docs.docker.com/build/buildkit/)
    * Valid credentials in .aws/credentials.
    * The credentials have sufficient privileges to run terraform deployments in your system
    * an .env file with these defined:

<pre>DOMAIN=localhost
CLUSTER_REPO={your account}.dkr.ecr.{your region}.amazonaws.com
DOCKER_REPO=icesat2sliderule
PS_SERVER_DOCKER_TAG=dev
TERRAFORM_CLI=tflocal
S3_FILES=/ps_server/test_misc/cluster_tf_versions
</pre>

* A docker compose file is included for development and testing
* Run 'make help' to list makefile targets
<pre>$ make help
#----------------------------------------------------------------------------------------- 
# Makefile Help                
#----------------------------------------------------------------------------------------- 
#----target--------------------description------------------------------------------------ 
docker                         build the container using cache and 
                               tag it with $(PS_SERVER_DOCKER_TAG) 
docker-no-cache                build the container no cache and 
                               tag it with $(PS_SERVER_DOCKER_TAG) 
docker-prune                   clean up all docker images and volumes
help                           That's me!
unit-tests-dev                 build and run ps-server with the dev marker 
unit-tests                     build and run ps-server unit tests 
</pre>
Detailed development notes for the entire provisioning system (ps-web and ps-server) can be found at [README-provisioning-system.md](https://github.com/ICESat2-SlideRule/sliderule-prov-sys/blob/main/README-provisioning-system.md)

## Notes on implementation
The ps-server Client/Server interface [ps_server.proto](https://github.com/ICESat2-SlideRule/sliderule-ps-server/blob/main/protos/ps_server.proto) is relatively generic. However, this system was implemented, developed and tested using [AWS](https://aws.amazon.com/) and [Terraform](https://www.terraform.io/) for [SlideRule Earth](https://slideruleearth.io/). Adding support for a different cloud provider or Infrastructure as code tool or for a new Host organization would mean creating an alternate version of [ps_server.py](https://github.com/ICESat2-SlideRule/sliderule-ps-server/blob/main/ps_server.py)

## Licensing
The following third-party libraries are used by slideRule-ps-server:
* terraform cli https://releases.hashicorp.com/terraform/ (MPL-2.0 license)
* __boto3__: https://github.com/boto/boto3 (Apache-2.0 license)
* __gRPC__: https://github.com/grpc/grpc (Apache-2.0 license)
* __Requests__: https://github.com/psf/requests (Apache-2.0 license)
* __pytz__: https://pypi.org/project/pytz/ (MIT License)
* __pyyml__:https://github.com/yaml/pyyaml (MIT License)