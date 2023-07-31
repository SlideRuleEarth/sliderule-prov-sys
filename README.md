# SlideRule provisioning system
This is the project repository for the ICESat2-Sliderule provisioning system

The provisioning system has two components:
* ps-web    (packages/ps-web)
* ps-server (packages/ps-server)

See the README located inside those packages for details related to them.

To get an overview of this build-and-deploy system for the provisioning system
<pre>
$ make help
aws-repo-docker-login          This authenticates the Docker CLI to use the aws ECR 
                               the asw Elastic Container Registry
deploy-to-slideruleearth-io    deploy already built and tagged prov-sys docker container
                               tagged '$(VERSION) 
                               (which defaults to latest) in terraform workspace slideruleearth.io 
                               e.g. make deploy-to-slideruleearth-io VERSION=v0.0.1
deploy-to-testsliderule-org    deploy already built and tagged prov-sys docker container tagged $(VERSION) 
                               (which defaults to latest) in terraform workspace testsliderule.org 
                               e.g. make deploy-to-testsliderule-org VERSION=v0.0.1
destroy-testsliderule-org      terraform destroy domain testsliderule.org
disable_provisioning           disable provisioning for DOMAIN. 
                               Once you do this you MUST deploy something
                               e.g. disable_provisioning DOMAIN=testsliderule.org.
                               Note: Must have Developer privileges to use this
distclean                      fully remove all non-version controlled files and directories
docker-login                   login to docker command line to access Docker container registery
docker-prune                   clean up stale dangling docker images
help                           That's me!
latest-to-testsliderule-org    build and deploy latest provisioning system 
                               to testsliderule.org; 
                               e.g. make latest-to-testsliderule-org
release-to-testsliderule-org   Tag, build and deploy provisioning system 
                               to testsliderule.org using VERSION; 
                               e.g. make release-to-testsliderule-org VERSION=v1.7.9
</pre>

For running this system locally with localstack acting as a proxy for AWS 
<pre>$cd test/prov-sys
$ make run</pre>

For running the ps-web unit tests
<pre>$cd test/prov-sys
$ make unit-tests-ps-web-only </pre>

For running the ps-server unit tests
<pre>$cd test/prov-sys
$ make unit-tests-ps-server-only </pre>

For running the ps-web/ps-server unit tests with localstack AWS emulation
<pre>$cd test/prov-sys
$ make unit-tests-localstack </pre>


