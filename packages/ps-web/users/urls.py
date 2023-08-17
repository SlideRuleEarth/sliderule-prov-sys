from __future__ import absolute_import, unicode_literals

from django_celery_results import views as celery_views

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
from django.http import Http404
from django.urls import include, re_path
from django.urls import path
from . import views
from django.conf import settings
from django.views.generic.base import TemplateView
from django.contrib.sites.models import Site

import os
import logging

LOG = logging.getLogger('django')

urlpatterns = [
     path('cancel_membership/<str:pk>/', views.cancelMembership, name="cancel-membership"),
     path('browse/', views.browse, name="browse"),
     path('org_manage_members/<str:pk>/', views.orgManageMembers, name="org-manage-members"),
     path('org_manage_cluster/<str:pk>/', views.orgManageCluster, name="org-manage-cluster"),
     path('org_profile/<str:pk>/', views.orgProfile, name="org-profile"),
     path('org_account_forecast/<str:pk>/', views.orgAccountForecast, name="org-account-forecast"),
     path('ajax_org_account_forecast/', views.ajaxOrgAccountForecast, name="ajax-org-account-forecast"),
     path('org_account_history/<str:pk>/', views.orgAccountHistory, name="org-account-history"),
     path('ajax_org_account_history/', views.ajaxOrgAccountHistory, name="ajax-org-account-history"),
     path('create_org_account/', views.orgAccountCreate,  name="create-org-account"),
     path('clear_num_nodes_reqs/<str:pk>/', views.clearOrgNumNodesReqs, name='clear-num-nodes-reqs'),
     path('clear_active_num_node_req/<str:pk>/', views.clearActiveNumNodeReq, name='clear-active-num-node-req'),
     path('org_configure/<str:pk>/', views.orgConfigure, name="org-configure"),
     path('org_refresh_cluster/<str:pk>/', views.orgRefreshCluster, name="org-refresh-cluster"),
     path('org_destroy_cluster/<str:pk>/', views.orgDestroyCluster, name="org-destroy-cluster"),
     path('req_new_membership/<str:pk>/', views.reqNewMembership,name="req-new-membership-account"),
     path('accounts/profile/', views.userProfile, name="user-profile"),
     path('prov_sys_admin/', views.provSysAdmin, name="prov-sys-admin"),
     path('disable_provisioning/', views.disableProvisioning, name="disable-provisioning"),
     re_path(r'^(?P<task_id>[\w\d\-]+)/done/?$', celery_views.is_task_successful, name='celery-is-task-successful'),
     re_path(r'^(?P<task_id>[\w\d\-]+)/status/?$', celery_views.task_status, name='celery-task-status'),
     path('', views.browse, name="browse")
]

LOG.info("settings.DEBUG:%s",settings.DEBUG)
LOG.info("settings.GIT_VERSION:%s",settings.GIT_VERSION)
LOG.info("settings.DOCKER_TAG:%s",settings.DOCKER_TAG)
LOG.info("settings.PS_VERSION:%s",settings.PS_VERSION)
LOG.info("settings.PS_SITE_TITLE:%s",settings.PS_SITE_TITLE)
LOG.info("settings.PS_BLD_ENVVER:%s",settings.PS_BLD_ENVVER)
LOG.info("settings.ALLOWED_HOSTS:%s",settings.ALLOWED_HOSTS)
LOG.info("settings.CSRF_TRUSTED_ORIGINS:%s",settings.CSRF_TRUSTED_ORIGINS)
LOG.info("settings.LOGGING.handlers.console.level:%s",settings.LOGGING['handlers']['console']['level'])
LOG.info(f"settings.SITE_ID:{settings.SITE_ID} {type(settings.SITE_ID)} must match one of the following site[n].id ...")
ndx = 0
try:
     for site in Site.objects.all():
          LOG.info(f"site[{ndx}] id:{site.id} {type(site.id)} name:{site.name} domain:{site.domain}")
          ndx = ndx+1
except Exception as e:
     LOG.exception("caught exception:")
 