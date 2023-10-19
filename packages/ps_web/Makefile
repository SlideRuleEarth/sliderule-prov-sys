ROOT = $(shell pwd)
DOCKER_REPO ?= icesat2sliderule
PS_WEB_DOCKER_TAG ?= dev
PS_NGINX_DOCKER_TAG ?= dev
NGINX_CONF ?= dev
DOCKER_EXEC_OPTS ?=
PS_WEB_SOURCE_DIR = $(ROOT)
PS_SERVER_SOURCE_DIR = $(ROOT)/../ps_server
PS_TEST_SOURCE_DIR = $(ROOT)/../test/prov-sys
ENVVER = $(shell git --git-dir ../../.git --work-tree . describe --abbrev --dirty --always --tags --long)
CURRENT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
SITE_ID = 1
PS_SERVER_DIR:=$(abspath $(PS_SERVER_SOURCE_DIR))
PS_WEB_DIR:=$(abspath $(PS_WEB_SOURCE_DIR))
PS_TEST_DIR:=$(abspath $(PS_TEST_SOURCE_DIR))

all: docker ps-nginx-build-docker

docker-login: ## login to docker command line to access Docker container registery
	docker login

clean_schema: ## clean the api schema
	rm -rf api/schema/schema.yml

api/schema/schema.yml: clean_schema ## generate the api schema used by swagger
	make ps-unit-test-build-docker && \
	export PWD=$(ROOT) && \
	docker compose up --detach && \
	docker exec ps-web ./manage.py spectacular --color --file /home/reg_user/ps/api/schema/schema.yml && \
	make down

#  NOTE:  the following targets are for building the swagger ui as a sepaerate container rather than including it in the ps-web container
# swagger-ui: 
# 	rm -rf swagger-ui && \
# 	git clone git@github.com:swagger-api/swagger-ui.git && \
# 	cd swagger-ui && \
# 	docker build --tag swaggerapi/swagger-ui:latest .

# ps-api-playground: api/schema/schema.yml swagger-ui ## run the swagger ui to test the api
# 	docker run --rm -p 80:8080 -e SWAGGER_JSON=/schema/schema.yml -v $(ROOT)/api/schema:/schema swaggerapi/swagger-ui
 
ps-web-clean-stage : # clean ps docker stage directory
	rm -rf docker/ps-web/stage

ps-nginx-clean-stage : # clean ps docker stage directory
	rm -rf docker/nginx/stage

ps-web-stage : ps-web-clean-stage
	mkdir -p docker/ps-web/stage
	echo DOCKER_TAG=$(PS_WEB_DOCKER_TAG) >> docker/ps-web/stage/.versions
	echo GIT_VERSION=$(ENVVER) >> docker/ps-web/stage/.versions
	cp docker/ps-web/Dockerfile docker/ps-web/stage/
	cp docker/ps-web/requirements.txt docker/ps-web/stage/
	cp docker/ps-web/docker-entrypoint.sh docker/ps-web/stage/
	cp manage.py docker/ps-web/stage/
	cp pytest.ini docker/ps-web/stage/
	cp conftest.py docker/ps-web/stage/
	cp -R static docker/ps-web/stage/
	cp -R ps_web docker/ps-web/stage/
	cp -R api docker/ps-web/stage/
	cp -R templates docker/ps-web/stage/
	cp -R users docker/ps-web/stage/
	cp -R ../ps_server/protos docker/ps-web/stage/
	cp -R ../../scripts docker/ps-web/stage/

ps-server-test-stub-clean-stage : # clean docker stage directory
	rm -rf docker/ps-server-test-stub/stage

ps-server-test-stub-stage : ps-server-test-stub-clean-stage # stage the files for docker image
	mkdir -p docker/ps-server-test-stub/stage
	echo PS_SERVER_DOCKER_TAG=django-unit-tests >> docker/ps-server-test-stub/stage/.ps_server_versions
	echo PS_SERVER_GIT_VERSION=$(ENVVER) >> docker/ps-server-test-stub/stage/.ps_server_versions
#	mkdir -p docker/ps-server-test-stub/stage/real_ps_server
#	touch docker/ps-server-test-stub/stage/real_ps_server/__init__.py
#	cp ../../packages/ps_server/ps_server.py docker/ps-server-test-stub/stage/real_ps_server/ps_server.py
	cp ../../packages/ps_server/docker/ps-server/Dockerfile docker/ps-server-test-stub/stage/Dockerfile
	awk '/COPY .\/stage\/ps_server.py \/ps_server\// { print; print "COPY ./stage/users/ /ps_server/users/"; next }1' docker/ps-server-test-stub/stage/Dockerfile > Dockerfile.tmp && mv Dockerfile.tmp docker/ps-server-test-stub/Dockerfile
#	awk '/COPY .\/stage\/ps_server.py \/ps_server\// { print; print "COPY ./stage/users/ /ps_server/users/"; print "COPY ./stage/real_ps_server/ /ps_server/real_ps_server/"; next }1' docker/ps-server-test-stub/stage/Dockerfile > Dockerfile.tmp && mv Dockerfile.tmp docker/ps-server-test-stub/Dockerfile
	cp -R ../../packages/ps_server/test_misc/ docker/ps-server-test-stub/stage/test_misc/
	cp docker/ps-server-test-stub/docker-entrypoint.sh docker/ps-server-test-stub/stage/
	cp docker/ps-server-test-stub/requirements.txt docker/ps-server-test-stub/stage/
	cp ps_server_test_stub/ps_server.py docker/ps-server-test-stub/stage/ps_server.py
	cp -R ../ps_server/protos docker/ps-server-test-stub/stage/
	mkdir -p docker/ps-server-test-stub/stage/users/tests
	cp ../../packages/ps_web/users/global_constants.py docker/ps-server-test-stub/stage/users/global_constants.py
	cp ../../packages/ps_web/users/tests/global_test_constants.py docker/ps-server-test-stub/stage/users/tests/global_test_constants.py
	touch docker/ps-server-test-stub/stage/users/__init__.py
	touch docker/ps-server-test-stub/stage/users/tests/__init__.py
#   this is to make sure imports of constants to the ps-server stub match current ps-web

ps-server-test-stub-build-docker : ps-server-test-stub-stage  ##  build the container for the ps-server stub
	cd docker/ps-server-test-stub && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-server-test-stub:dev . 
#	rm -rf stage && echo ENVVER=$(ENVVER)

docker : ps-web-stage  ##  build the container using cache and tag it with $(PS_WEB_DOCKER_TAG) defaulted to dev
	cd docker/ps-web && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-web:$(PS_WEB_DOCKER_TAG) .  && \
	rm -rf stage && echo ENVVER=$(ENVVER)			

docker-no-versions : ps-web-stage  ##  build the container using cache and tag it with $(PS_WEB_DOCKER_TAG) defaulted to dev
	cd docker/ps-web && \
	cp requirements.no-versions.txt stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-web:$(PS_WEB_DOCKER_TAG) .  && \
	rm -rf stage && echo ENVVER=$(ENVVER)			

docker-test: ps-web-stage 
	cd docker/ps-web && \
	cp requirements.txt stage/requirements.txt && \
	cat requirements-additional-for-test.txt >> stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-web:$(PS_WEB_DOCKER_TAG) .  && \
	rm -rf stage && echo ENVVER=$(ENVVER)			


docker-no-cache: ps-web-stage  ## build the container from scratch and tag it with $(PS_WEB_DOCKER_TAG) defaulted to dev
	cd docker/ps-web && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-web:$(PS_WEB_DOCKER_TAG) --no-cache . && \
	rm -rf stage && echo ENVVER=$(ENVVER)

docker-no-cache-no-versions: ps-web-stage  ## build the container from scratch and tag it with $(PS_WEB_DOCKER_TAG) defaulted to dev
	cd docker/ps-web && \
	cp requirements.no-versions.txt stage/requirements.txt && \
	docker build --tag $(DOCKER_REPO)/sliderule-ps-web:$(PS_WEB_DOCKER_TAG) --no-cache . && \
	rm -rf stage && echo ENVVER=$(ENVVER)

clean-coverage: ## clean up coverage files
	rm -rf htmlcov/*

ps-unit-test-build-docker: clean-coverage
	make ps-nginx-build-docker	
	make docker-test
	make ps-server-test-stub-build-docker

ps-nginx-build-docker: docker  ## build standard nginx with ps config file
	cp docker/nginx/conf/ps-nginx-$(NGINX_CONF).conf docker/nginx/ps-nginx.conf && cd docker/nginx  && docker build --build-arg REPO=$(DOCKER_REPO) --build-arg VERSION=$(PS_NGINX_DOCKER_TAG) --tag $(DOCKER_REPO)/sliderule-ps-nginx:$(PS_NGINX_DOCKER_TAG) . && echo ENVVER=$(ENVVER)	

ps-nginx-build-docker-no-cache: docker-no-cache ## build standard nginx with ps config file
	cp docker/nginx/conf/ps-nginx-$(NGINX_CONF).conf docker/nginx/ps-nginx.conf && cd docker/nginx  && docker build --build-arg REPO=$(DOCKER_REPO) --build-arg VERSION=$(PS_NGINX_DOCKER_TAG) --tag $(DOCKER_REPO)/sliderule-ps-nginx:$(PS_NGINX_DOCKER_TAG) --no-cache . && echo ENVVER=$(ENVVER)		

network: ## create a test network to connect to ps_server
	docker network create ps_network

docker-prune: ## clean up stale dangling docker images
	docker system prune

down:  ## bring down all the docker containers
	docker compose down

bld-and-run-unit-tests: down # build and run the unit tests against a running dev system then exit NOTE: for github actions the DOCKER_EXEC_OPTS is a null string
	make ps-unit-test-build-docker && \
	docker compose up --detach && \
	docker logs ps-server && \
	docker logs ps-web && \
	docker exec $(DOCKER_EXEC_OPTS) ps-web coverage run -m pytest -k "not TasksTestWithPSServer" -m "not real_ps_server and not ps_disable" && \
	docker exec $(DOCKER_EXEC_OPTS) ps-web coverage html
	make down

bld-and-run-unit-test-dev: down # build and run the unit tests against a running dev system then exit NOTE: for github actions the DOCKER_EXEC_OPTS is a null string
	make ps-unit-test-build-docker && \
	export PS_TEST_DIR=$(PS_TEST_DIR) && \
	export PS_SERVER_DIR=$(PS_SERVER_DIR) && \
	docker compose up --detach && \
	docker logs ps-server && \
	docker logs ps-web && \
	docker exec $(DOCKER_EXEC_OPTS) ps-web pytest -k "not TasksTestWithPSServer" -m "dev and not real_ps_server and not ps_disable"
	make down

unit-tests: clean-coverage ## build and run ps-web unit tests from interactive terminal
	DOCKER_EXEC_OPTS=-it make bld-and-run-unit-tests 

unit-tests-dev: ## build and run ps-web dev unit test
	DOCKER_EXEC_OPTS=-it make bld-and-run-unit-test-dev

.PHONY : down docker docker-no-cache ps-web-clean-stage ps-web-stage unit-tests bld-and-run-unit-tests

help: ## That's me!
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "# Makefile Help       "
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "#----target--------------------description------------------------------------------------"
	@grep -E '^[a-zA-Z_-].+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ENVVER:$(ENVVER)	
