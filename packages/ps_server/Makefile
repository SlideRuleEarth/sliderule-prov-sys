ROOT = $(shell pwd)
DOCKER_REPO ?= icesat2sliderule
PS_SERVER_DOCKER_TAG ?= dev
PS_VERSION ?= dev
ENVVER = $(shell git --git-dir ../../.git --work-tree . describe --abbrev --dirty --always --tags --long)
DOCKER_EXEC_OPTS ?=
last_dir = $(shell basename $(ROOT))

# Conditional setting of PS_TEST_DIR
ifeq ($(last_dir),ps_server)
PS_TEST_DIR = $(ROOT)
LOCALSTACK_VOLUME_DIR = $(ROOT)/../../test/prov-sys
else
PS_TEST_DIR = $(ROOT)/../../packages/ps_server
LOCALSTACK_VOLUME_DIR = $(ROOT)
endif

all: docker

ps-server-clean-stage : # clean docker stage directory
	rm -rf docker/ps-server/stage

ps-server-stage : ps-server-clean-stage # stage the files for docker image
	mkdir -p docker/ps-server/stage
	# because we build latest and then tag it to PS_VERSION we use PS_VERSION here for PS_SERVER_DOCKER_TAG
	echo PS_SERVER_DOCKER_TAG=$(PS_VERSION) >> docker/ps-server/stage/.ps_server_versions
	echo PS_SERVER_GIT_VERSION=$(ENVVER) >> docker/ps-server/stage/.ps_server_versions
	cp docker/ps-server/docker-entrypoint.sh docker/ps-server/stage/
	cp docker/ps-server/Dockerfile docker/ps-server/stage/
	cp docker/ps-server/requirements.txt docker/ps-server/stage/
	cp ps_server.py docker/ps-server/stage/
	cp -R test_misc docker/ps-server/stage/
	cp -R protos docker/ps-server/stage/

docker-no-cache : ps-server-stage  ## build the container no cache and tag it with $(PS_SERVER_DOCKER_TAG) 
	cd docker/ps-server && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server:$(PS_SERVER_DOCKER_TAG) --no-cache . && \
	rm -rf stage && echo ENVVER=$(ENVVER)		

docker : ps-server-stage  ## build the container using cache and tag it with $(PS_SERVER_DOCKER_TAG) 
	cd docker/ps-server && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server:$(PS_SERVER_DOCKER_TAG) . && \
	rm -rf stage && echo ENVVER=$(ENVVER)		

docker-test : ps-server-stage  # build the container using cache and tag it with $(PS_SERVER_DOCKER_TAG) 
	cd docker/ps-server && \
	cp requirements.txt stage/requirements.txt && \
	cat requirements-additional-for-test.txt >> stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server:$(PS_SERVER_DOCKER_TAG) . && \
	rm -rf stage && echo ENVVER=$(ENVVER)		

docker-no-cache-no-versions : ps-server-stage  # build the container no cache and tag it with $(PS_SERVER_DOCKER_TAG) 
	cd docker/ps-server && \
	cp requirements.no-versions.txt stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server:$(PS_SERVER_DOCKER_TAG) --no-cache . && \
	rm -rf stage && echo ENVVER=$(ENVVER)		

docker-no-versions : ps-server-stage  # build the container using cache no version pinning and tag it with $(PS_SERVER_DOCKER_TAG) 
	cd docker/ps-server && \
	cp requirements.no-versions.txt stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server:$(PS_SERVER_DOCKER_TAG) . && \
	rm -rf stage && echo ENVVER=$(ENVVER)		

network : # One time set up of docker development network(this is persistent)
	docker network create ps_network

docker-prune: ## clean up all docker images and volumes
	docker system prune -a

update-s3-files-for-tests: # stage s3 files for unit tests to mount to localstack
	aws s3 sync --include "*" s3://sliderule/prov-sys/cluster_tf_versions/ test_misc/cluster_tf_versions
	python3 test_misc/replace_terraform_aws_provider.py test_misc/cluster_tf_versions
	python3 test_misc/remove_terraform_backend.py test_misc/cluster_tf_versions

upload-s3-files-to-localstack: ## upload test s3 files to localstack
	aws --endpoint-url=http://localhost:4566 s3 sync --include "*" test_misc/cluster_tf_versions/ s3://sliderule/prov-sys/cluster_tf_versions/

bld-and-run-unit-tests: down  # run the ps_server unit tests then exit
	make update-s3-files-for-tests && \
	make docker-test && \
	export PS_TEST_DIR=$(PS_TEST_DIR) && \
	export PS_SERVER_DIR=$(PS_SERVER_DIR) && \
	export DOCKER_REPO=$(DOCKER_REPO) && \
	export PS_SERVER_DOCKER_TAG=$(PS_SERVER_DOCKER_TAG) && \
	export LOCALSTACK_VOLUME_DIR=$(LOCALSTACK_VOLUME_DIR) && \
	docker compose up --detach && \
	docker logs ps-server && \
	docker exec $(DOCKER_EXEC_OPTS) --workdir /ps_server/test_misc ps-server pytest --log-cli-level=ERROR && \
	make down

bld-and-run-unit-test-dev: down  # run the ps_server unit tests then exit 
	make update-s3-files-for-tests && \
	make docker-test && \
	export PS_TEST_DIR=$(PS_TEST_DIR) && \
	export PS_SERVER_DIR=$(PS_SERVER_DIR) && \
	export DOCKER_REPO=$(DOCKER_REPO) && \
	export PS_SERVER_DOCKER_TAG=$(PS_SERVER_DOCKER_TAG) && \
	export LOCALSTACK_VOLUME_DIR=$(LOCALSTACK_VOLUME_DIR) && \
	docker compose up --detach && \
	docker logs ps-server && \
	docker exec $(DOCKER_EXEC_OPTS) --workdir /ps_server/test_misc ps-server pytest -m "dev" --log-cli-level=ERROR && \
	make down

unit-tests: ## build and run ps-server unit tests 
	DOCKER_EXEC_OPTS=-it make bld-and-run-unit-tests 

unit-tests-dev: ## build and run ps-server with the dev marker 
	DOCKER_EXEC_OPTS=-it make bld-and-run-unit-test-dev

down:
	export PS_TEST_DIR=$(PS_TEST_DIR) && \
	export PS_SERVER_DIR=$(PS_SERVER_DIR) && \
	docker compose down --timeout 1

.PHONY : ps-server-clean-stage

help: ## That's me!
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "# Makefile Help       "
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "#----target--------------------description------------------------------------------------"
	@grep -E '^[a-zA-Z_-].+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ENVVER:$(ENVVER)
	@echo PS_TEST_DIR:$(PS_TEST_DIR)
	@echo LOCALSTACK_VOLUME_DIR:$(LOCALSTACK_VOLUME_DIR)
	@echo ROOT:$(ROOT)
	@echo last_dir:$(last_dir)