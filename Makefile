ROOT = $(shell pwd)
STAGE = $(ROOT)/stage

PS_SERVER_SOURCE_DIR = $(ROOT)/packages/ps_server
PS_WEB_SOURCE_DIR = $(ROOT)/packages/ps_web
PS_NGINX_SOURCE_DIR = $(ROOT)/packages/ps_web # nginx docker is built in web directory

VERSION ?= latest
VERSION_TOKENS := $(subst ., ,$(lastword $(VERSION)))
DOMAIN ?= testsliderule.org
REGION ?= us-west-2
REPO ?= $(shell aws secretsmanager get-secret-value --secret-id $(DOMAIN)/secrets | jq -r '.SecretString' | jq -r '.prov_sys_repo')
ACCT_ID ?= $(shell aws secretsmanager get-secret-value --secret-id $(DOMAIN)/secrets | jq -r '.SecretString' | jq -r '.aws_account_id')
NOW = $(shell /bin/date +"%Y%m%d%H%M%S")
ENVVER = $(shell git --git-dir .git --work-tree . describe --abbrev --dirty --always --tags --long)
MFA_CODE ?= $(shell read -p "Enter MFA code: " code; echo $$code)
DOMAIN_ROOT = $(firstword $(subst ., ,$(DOMAIN)))
DOMAIN_NAME = $(subst .,-,$(DOMAIN))
DB_FINAL_SNAPSHOT_NAME = $(DOMAIN_NAME)-tf-applied-${NOW}
# This ugliness is due to the following issue: https://github.com/pennersr/django-allauth/issues/3026
# These must match the DB that the deployed code is using
# NOTE: these can be the same or different. If you change the DB site entries these must match those

# The ps-web log file will contain entries that look something like this.
# Use these log entries to verify the values in this makefile match the database running for that DOMAIN:
#  ... [DOMAIN:slideruleearth <class 'str'>]
#  ... [settings.SITE_ID:4 <class 'int'> must match one of the following site[n].id ...]
#  ... [urls.py:<nn>:<module>] [site[<n>] id:4 <class 'int'> name:slideruleearth domain:slideruleearth]
# In this example SITE_ID:4 matches the site entry for id:4 and DOMAIN:slideruleearth.io matches same entry's domain:slideruleearth.io
#
# If these don't match the site won't come up so change this Makefile CURRENT_SITE_ID_slideruleearth to match site.id then rebuild and redeploy
#
CURRENT_SITE_ID_slideruleearth := 4
CURRENT_SITE_ID_testsliderule  := 5
SITE_TITLE ?= 'SlideRule Earth'  # e.g. 'SlideRule Earth' or 'SlideRule Test'
ifeq ($(DOMAIN_ROOT),slideruleearth)
	SITE_ID = CURRENT_SITE_ID_slideruleearth
else
	SITE_ID = CURRENT_SITE_ID_testsliderule
endif

all: help

dump-params-used:
	@echo NOW $(NOW)
	@echo DB_FINAL_SNAPSHOT_NAME $(DB_FINAL_SNAPSHOT_NAME)
	@echo DOMAIN $(DOMAIN)
	@echo DOMAIN_NAME $(DOMAIN_NAME)
	@echo VERSION $(VERSION)
	@echo SITE_ID:$(SITE_ID)
	@echo SITE_ID value:$($(SITE_ID))
	@echo DOMAIN:$(DOMAIN)

############################
# Docker Utility Targets
############################

docker-login: ## login to docker command line to access Docker container registery
	docker login

docker-prune: ## clean up stale dangling docker images
	docker system prune

src-tag-build-and-deploy: # git tag the build and deploy src with $(VERSION)
	$(ROOT)/VERSION.sh $(VERSION) && git push --tags; git push


##############################
# Provisioning System Targets
##############################

ps_distclean:
	cd $(PS_WEB_SOURCE_DIR)    && make ps-web-clean-stage
	cd $(PS_NGINX_SOURCE_DIR)  && make ps-nginx-clean-stage
	cd $(PS_SERVER_SOURCE_DIR) && make ps-server-clean-stage

docker-no-cache: ps_distclean
	cd $(PS_NGINX_SOURCE_DIR)  && DOCKER_REPO=$(REPO) PS_NGINX_DOCKER_TAG=latest NGINX_CONF=fargate make ps-nginx-build-docker-no-cache && \
	cd $(PS_WEB_SOURCE_DIR)    && DOCKER_REPO=$(REPO) PS_WEB_DOCKER_TAG=latest                      make docker-no-cache && \
	cd $(PS_SERVER_SOURCE_DIR) && DOCKER_REPO=$(REPO) PS_SERVER_DOCKER_TAG=latest                   make docker-no-cache

# Note: the ps-nginx docker references the ps-web docker image so we have to build and push ps-web before building nginx
docker: # make the prov-sys docker image
	cd $(PS_WEB_SOURCE_DIR) && DOCKER_REPO=$(REPO) PS_WEB_DOCKER_TAG=latest PS_VERSION=$(VERSION) make docker
	docker tag $(REPO)/sliderule-ps-web:latest $(REPO)/sliderule-ps-web:$(VERSION)

	cd $(PS_NGINX_SOURCE_DIR) && NGINX_CONF=fargate DOCKER_REPO=$(REPO) PS_NGINX_DOCKER_TAG=latest make ps-nginx-build-docker
	docker tag $(REPO)/sliderule-ps-nginx:latest $(REPO)/sliderule-ps-nginx:$(VERSION)

	cd $(PS_SERVER_SOURCE_DIR) && DOCKER_REPO=$(REPO) PS_SERVER_DOCKER_TAG=latest PS_VERSION=$(VERSION) make docker
	docker tag $(REPO)/sliderule-ps-server:latest $(REPO)/sliderule-ps-server:$(VERSION)
	@echo VERSION:$(VERSION)

docker-push:
	docker push $(REPO)/sliderule-ps-web:$(VERSION)
	docker push $(REPO)/sliderule-ps-nginx:$(VERSION)
	docker push $(REPO)/sliderule-ps-server:$(VERSION)
	@echo VERSION:$(VERSION)

disable_provisioning:  ## disable provisioning for DOMAIN. Once you do this you MUST deploy something
	@echo "Disabling provisioning for domain: $(DOMAIN)"
	@read -p "Enter MFA code: " code; \
	port=$$(python3 $(ROOT)/scripts/disable_provisioning.py --domain $(DOMAIN) --mfa_code $$code); \
	echo "Port from script: $$port"; \
	echo $$port > .port.tmp

deploy: disable_provisioning # deploy prov-sys docker container tagged $(VERSION) (which defaults to latest) in terraform workspace $(DOMAIN) e.g. 'make deploy VERSION=v0.0.1 DOMAIN='testsliderule.org' SITE_TITLE='SlideRule Test''
	port=$$(cat .port.tmp); \
	mkdir -p terraform/prov-sys && cd terraform/prov-sys && terraform init && terraform workspace select $(DOMAIN)-prov-sys || terraform workspace new $(DOMAIN)-prov-sys && \
	terraform apply -var docker_image_url_ps-web=$(REPO)/sliderule-ps-web:$(VERSION) -var docker_image_url_ps-nginx=$(REPO)/sliderule-ps-nginx:$(VERSION)  -var docker_image_url_ps-server=$(REPO)/sliderule-ps-server:$(VERSION) -var rds_id=$(DOMAIN_NAME) -var rds_final_snapshot=$(DB_FINAL_SNAPSHOT_NAME) -var domain=$(DOMAIN) -var domain_root=$(DOMAIN_ROOT) -var ps_server_host=localhost -var ps_server_port=$$port -var ps_version=$(VERSION) -var ps_site_title='$(SITE_TITLE)' -var ps_bld_envver=$(ENVVER) -var site_id=$($(SITE_ID))
	@echo SITE_ID:$(SITE_ID)
	@echo SITE_ID value:$($(SITE_ID))
	@echo DOMAIN:$(DOMAIN)
	@echo VERSION:$(VERSION)
	@echo ENVVER:$(ENVVER)

destroy:  # destroy prov-sys defined in terraform workspace $(DOMAIN_NAME) e.g. 'make destroy DOMAIN=testsliderule.org'
	mkdir -p terraform/prov-sys && cd terraform/prov-sys && terraform init && terraform workspace select $(DOMAIN)-prov-sys || terraform workspace new $(DOMAIN)-prov-sys && \
	terraform destroy -var rds_final_snapshot=$(DB_FINAL_SNAPSHOT_NAME) -var rds_restore_with_snapshot=not_used -var domain=$(DOMAIN) -var domain_root=$(DOMAIN_ROOT) -var ps_version=$(VERSION) -var ps_site_title=$(SITE_TITLE) -var ps_bld_envver=$(ENVVER) -var site_id=$($(SITE_ID))
	@echo DOMAIN:$(DOMAIN)
	@echo VERSION:$(VERSION)
	@echo ENVVER:$(ENVVER)

destroy-testsliderule-org: ## terraform destroy domain testsliderule.org
	make destroy DOMAIN=testsliderule.org

build-and-deploy: # build and deploy prov-sys docker container tagged $(VERSION) in terraform workspace $(DOMAIN) e.g. 'make build-and-deploy VERSION=v0.0.1 DOMAIN=testsliderule.org SITE_TITLE='SlideRule Test'' NOTE:(VERSION defaults to latest)
	make docker
	make docker-push
	make deploy

release: src-tag-build-and-deploy # Tag, build and deploy provisioning system; e.g. make release VERSION=v0.0.1 DOMAIN='testsliderule.org' SITE_TITLE='SlideRule Test'
	cd $(ROOT) && make build-and-deploy

latest-to-testsliderule-org: ## build and deploy latest provisioning system to testsliderule.org; e.g. make latest-to-testsliderule-org
	make build-and-deploy DOMAIN=testsliderule.org VERSION=latest DOMAIN=testsliderule.org SITE_TITLE='SlideRule Test (${NOW})'

release-to-testsliderule-org: ## Tag, build and deploy provisioning system to testsliderule.org; e.g. make release-to-testsliderule-org VERSION=v1.7.9
	make release DOMAIN=testsliderule.org SITE_TITLE='SlideRule Test'

deploy-to-slideruleearth-io: ## deploy already built and tagged prov-sys docker container tagged $(VERSION) (which defaults to latest) in terraform workspace slideruleearth.io e.g. make deploy-to-slideruleearth-io VERSION=v0.0.1
	make deploy DOMAIN=slideruleearth.io SITE_TITLE='SlideRule Earth'

deploy-to-testsliderule-org: ## deploy already built and tagged prov-sys docker container tagged $(VERSION) (which defaults to latest) in terraform workspace testsliderule.org e.g. make deploy-to-testsliderule-org VERSION=v0.0.1
	make deploy DOMAIN=testsliderule.org SITE_TITLE='SlideRule Test'

####################
# Global Targets
####################

distclean: ## fully remove all non-version controlled files and directories
	- rm -Rf $(BUILD)
	- rm -Rf $(STAGE)

.PHONY: terraform terraform-select terraform-destroy tag-build-push release build-and-deploy docker src-tag docker

help: ## That's me!
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "# Makefile Help                                                                          |"
	@printf "\033[37m%-30s\033[0m %s\n" "#-----------------------------------------------------------------------------------------"
	@printf "\033[37m%-30s\033[0m %s\n" "#-target-----------------------description------------------------------------------------"
	@grep -E '^[a-zA-Z_-].+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ENVVER:$(ENVVER)