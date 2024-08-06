from __future__ import print_function
import ps_server_pb2_grpc
import ps_server_pb2
import grpc
import pytz
import ast
import json
import os
import redis
from django.http import  HttpResponse
from datetime import timezone
from dateutil import tz
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render, redirect, HttpResponseRedirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.transaction import get_autocommit
from .models import Cluster, GranChoice, OrgAccount, OrgCost, Membership, User, OrgNumNode, PsCmdResult, OwnerPSCmd
from .forms import MembershipForm, OrgAccountForm, OrgAccountCfgForm, OrgProfileForm, UserProfileForm,OrgNumNodeForm
from .utils import has_admin_privilege,user_in_one_of_these_groups,disable_provisioning
from .tasks import get_db_org_cost,get_versions_for_org, get_asg_cfgs_for_all_versions, update_burn_rates, update_all_burn_rates, getGranChoice, sort_ONN_by_nn_exp,enqueue_process_state_change,remove_num_node_requests,get_PROVISIONING_DISABLED,process_num_nodes_api,update_ddt,create_all_forecasts,get_scheduled_jobs,reconcile_org,get_asg_cfgs_for_version
from django.core.mail import send_mail
from django.conf import settings
from django.forms import formset_factory
from django.template.defaulttags import register
import logging
from django.http import JsonResponse
from django.db.models import Q
from django.utils.timezone import is_aware
import datetime
from google.protobuf.json_format import MessageToJson
from users import ps_client
from users.global_constants import *
from django.db import transaction
from datetime import datetime, timedelta
from .tasks import cost_accounting, init_new_org_memberships
from django.contrib.auth import get_user_model
from allauth.account.decorators import verified_email_required
from oauth2_provider.models import Application
from django_rq import get_queue,enqueue
import requests
from django.http import JsonResponse


# logging.basicConfig(
#     format='%(asctime)s %(levelname)-8s %(message)s',
#     level=logging.INFO,
#     datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger('django')

def get_user_orgs(request):
    active_user = request.user
    if(request.user.is_authenticated):
        user_orgs = OrgAccount.objects.filter(owner=active_user)
    else:
        user_orgs = {}
    PS_BLD_ENVVER = settings.PS_BLD_ENVVER
    version_is_release = PS_BLD_ENVVER.startswith('v') and ('-0-' in PS_BLD_ENVVER) and not ('-dirty' in PS_BLD_ENVVER)
    if '-0-' in PS_BLD_ENVVER:
        PS_BLD_ENVVER =  PS_BLD_ENVVER.rsplit('-')[0]
    domain = os.environ.get("DOMAIN")
    return{ "user_orgs": user_orgs, 
            "active_user": active_user, 
            "DEBUG": settings.DEBUG, 
            "GIT_VERSION":settings.GIT_VERSION, 
            "DOCKER_TAG":settings.DOCKER_TAG,
            "PS_VERSION":settings.PS_VERSION, 
            "PS_SITE_TITLE":settings.PS_SITE_TITLE, 
            "PS_BLD_ENVVER":PS_BLD_ENVVER,
            "version_is_release":version_is_release,
            "domain": domain }

def get_orgAccountObj(pk):
    return OrgAccount.objects.get(id=pk)

def get_orgAccountObjByName(orgname):
    return OrgAccount.objects.get(name=orgname)


def get_orgAccountObjsForUser(active_user):
    return OrgAccount.objects.filter(owner=active_user)


def get_all_orgAccountObjs():
    return OrgAccount.objects.all()


def get_MembershipObj(pk):
    return Membership.objects.get(id=pk)


def get_MembershipObjsFiltered(pk, ruser):
    return Membership.objects.filter(org=pk, user=ruser)


def get_Memberships(orgAccountObj):
    return Membership.objects.filter(org=orgAccountObj.id)

def get_MembershipsForUser(active_user):
    return Membership.objects.filter(user=active_user)


def send_activation_email(request, orgname, user):
    domain = os.environ.get("DOMAIN")
    subject = f"Membership to {orgname}"
    message = f"{user.first_name} {user.last_name}, \nYour membership to {orgname} on https://{domain} has been activated.\nYou may use the system. To learn how to use the {orgname} cluster see the user guide: https://slideruleearth.io/web/rtd/"
    LOG.info("-----> sending email... %s", [user.email])
    from_email = f'support@mail.{domain}'

    try:
        send_mail(
            subject,
            message,
            from_email,
            [user.email],
            fail_silently=False,
        )
    except Exception as e:
        LOG.exception('Exception caught when sending activation email')
        messages.error(request, 'INTERNAL ERROR; FAILED to send activation email')


@login_required(login_url='account_login')
@verified_email_required
def orgManageMembers(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")
    if has_admin_privilege(request.user, orgAccountObj):
        memberships = get_Memberships(orgAccountObj)
        formset_initial = []
        for m in memberships:
            tuple = {'username':m.user.username,'firstname': m.user.first_name,
                    'lastname': m.user.last_name, 'active': m.active}
            formset_initial.append(tuple)
        MembershipFormSet = formset_factory(MembershipForm, extra=0)
        if request.method == "POST":
            formset = MembershipFormSet(request.POST, initial=formset_initial)
            if formset.is_valid():
                emails_sent=False
                for form in formset:
                    user_set = get_user_model().objects.filter(first_name=form.cleaned_data.get(
                        'firstname')).filter(last_name=form.cleaned_data.get('lastname'))
                    for m in memberships:  # TBD is there a more efficient way?
                        old_active_state = m.active
                        if (m.user.first_name == user_set[0].first_name) and (m.user.last_name == user_set[0].last_name):
                            m.active = form.cleaned_data.get('active')
                            if(m.active and not old_active_state):
                                m.activation_date = datetime.now(timezone.utc)
                                LOG.info("Member:%s is now active @ %s",
                                        m.user.last_name, m.activation_date.strftime("%a %b %d %I:%M:%S %p %Z"))
                                # maybe add an email col to org_manage_members to give owner control of sending email or not?
                                send_activation_email(request,orgAccountObj.name,m.user)
                                emails_sent = True
                            else:
                                LOG.info("Member:%s NOT active", m.user.last_name)
                            m.save()  # need to save active AND is not active
                msg = f"{request.user.username} your Organization account:{orgAccountObj.name} was updated successully"
                if emails_sent:
                    msg += ", emails were sent to notify newly activated users"
                messages.success(request, msg)
                return redirect('browse')
        else:
            formset = MembershipFormSet(initial=formset_initial)
        context = {'org': orgAccountObj,
                'memberships': memberships, 'formset': formset}
        return render(request, 'users/manage_memberships.html', context)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def getAsgConfigs(request):
    LOG.info(f"{request.method} {request.user.username} get_asg_configs_view")
    data = get_asg_cfgs_for_all_versions()
    return JsonResponse(data)

@login_required(login_url='account_login')
@verified_email_required
def orgManageCluster(request, pk):
    #LOG.info("%s %s",request.method,pk)
    orgAccountObj = get_orgAccountObj(pk)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    LOG.info(f"{request.method} {orgAccountObj.name} loop_count:{orgAccountObj.loop_count} ps:{orgAccountObj.num_ps_cmd} ops:{orgAccountObj.num_owner_ps_cmd}  autocommit:{get_autocommit()}")
    orgNumNodeObjs = sort_ONN_by_nn_exp(orgAccountObj)
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        try:
            filter_time = (datetime.now(timezone.utc)-timedelta(hours=orgAccountObj.pcqr_display_age_in_hours)).replace(microsecond=0)
            purge_time = (datetime.now(timezone.utc)-timedelta(days=orgAccountObj.pcqr_retention_age_in_days)).replace(microsecond=0)
            LOG.debug(f"{orgAccountObj.name} display filter_tm:{filter_time} current purge tm:{purge_time}")
            psCmdResultObjs = PsCmdResult.objects.filter(Q(expiration__gt=(filter_time)) | Q(expiration__isnull=True)).filter(org=orgAccountObj).order_by('-creation_date')
        except PsCmdResult.DoesNotExist:
            psCmdResultObjs = None
        #LOG.info("%s is_deployed?:%s  deployed_state:%s", orgAccountObj.name, clusterObj.is_deployed,clusterObj.deployed_state)
        update_burn_rates(orgAccountObj) # also updates clusterObj.version clusterObj.cur_nodes
        update_ddt(orgAccountObj) # ddt is drop dead times i.e. when the org runs out of money for min current and max node configurations
        if request.method == "POST":
            form_submit_value = request.POST.get('form_submit')
            LOG.info(f"form_submit_value:{form_submit_value}")
            if form_submit_value == 'add_onn':
                add_onn_form = OrgNumNodeForm(request.POST,min_nodes=orgAccountObj.min_node_cap,max_nodes=orgAccountObj.max_node_cap, prefix = 'add_onn')
                msg = ''
                if (add_onn_form.is_valid() and (int(add_onn_form.data['add_onn-desired_num_nodes']) >= 0)):
                    desired_num_nodes = add_onn_form.cleaned_data['desired_num_nodes']
                    LOG.info(f"desired_num_nodes:{desired_num_nodes}")
                    ttl_minutes = add_onn_form.cleaned_data['ttl_minutes']
                    if ttl_minutes != int(add_onn_form.data['add_onn-ttl_minutes']):
                        msg = f"Clamped ttl_minutes! - "
                    expire_time = datetime.now(timezone.utc)+timedelta(minutes=ttl_minutes)
                    jrsp,status = process_num_nodes_api(name=orgAccountObj.name, user=request.user, desired_num_nodes=desired_num_nodes, expire_time=expire_time, is_owner_ps_cmd=False)
                    if status == 200:
                        msg += jrsp['msg']
                        messages.success(request,msg)
                        enqueue_process_state_change(orgAccountObj.name)
                    else:
                        messages.error(request,jrsp['error_msg'])
                else:
                    emsg = f"Input Errors:{add_onn_form.errors.as_text}"
                    messages.error(request, emsg)
                    LOG.info(f"Did not create ONN for {orgAccountObj.name} {emsg}")
            else:
                add_onn_form = OrgNumNodeForm(min_nodes=orgAccountObj.min_node_cap,max_nodes=OrgAccount.admin_max_node_cap,prefix = 'add_onn')
        else:
            add_onn_form = OrgNumNodeForm(min_nodes=orgAccountObj.min_node_cap,max_nodes=OrgAccount.admin_max_node_cap,prefix = 'add_onn')
        LOG.info(f"{orgAccountObj.name} cluster current_version:{clusterObj.cur_version} provision_env_ready:{clusterObj.provision_env_ready}")
        #LOG.info(f"about to get versions")
        versions = get_versions_for_org(orgAccountObj.name)
        config_form = OrgAccountCfgForm(instance=orgAccountObj,available_versions=versions)

        domain = os.environ.get("DOMAIN")
        pending_refresh = None
        pending_destroy = None
        try:
            OwnerPSCmd.objects.get(org=orgAccountObj, ps_cmd='Refresh')
            pending_refresh = True
        except OwnerPSCmd.DoesNotExist:
            pending_refresh = False
        try:
            OwnerPSCmd.objects.get(org=orgAccountObj, ps_cmd='Destroy')
            pending_destroy = True
        except OwnerPSCmd.DoesNotExist:
            pending_destroy = False
        context = { 'org': orgAccountObj,
                    'cluster': clusterObj, 
                    'add_onn_form': add_onn_form,
                    'config_form': config_form, 
                    'ps_cmd_rslt_objs':psCmdResultObjs,
                    'cluster_mod_date_utc': clusterObj.modified_date.replace(tzinfo=pytz.utc),
                    'onn_objs':orgNumNodeObjs,
                    'domain':domain, 
                    'user_is_developer':request.user.groups.filter(name='PS_Developer').exists(), 'now':datetime.now(timezone.utc),
                    'PROVISIONING_DISABLED': get_PROVISIONING_DISABLED(),
                    'pending_refresh':pending_refresh,
                    'pending_destroy':pending_destroy,
                }
        
        LOG.info(f"{request.user.username} {request.method} {orgAccountObj.id} name:{orgAccountObj.name} is_public:{orgAccountObj.is_public} version:{orgAccountObj.version} min_node_cap:{orgAccountObj.min_node_cap} max_node_cap:{orgAccountObj.max_node_cap} allow_deploy_by_token:{orgAccountObj.allow_deploy_by_token} destroy_when_no_nodes:{orgAccountObj.destroy_when_no_nodes} pending_refresh:{pending_refresh} pending_destroy:{pending_destroy}")
        #LOG.info("rendering users/org_manage_cluster.html")
        return render(request, 'users/org_manage_cluster.html', context)
    else:
        LOG.info(f"{request.user.username} {request.method} {orgAccountObj.name} UNAUTHORIZED")
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def orgRefreshCluster(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if request.method == 'POST':
            status = 200
            task_id = ''
            emsg = ''
            msg = ''
            try:
                try:
                    owner_ps_cmd = OwnerPSCmd.objects.get(org=orgAccountObj, ps_cmd='Refresh')
                    msg = f" -- IGNORING -- Refresh {orgAccountObj.name} already queued for processing"
                except OwnerPSCmd.DoesNotExist:
                    owner_ps_cmd = OwnerPSCmd.objects.create(user=request.user, org=orgAccountObj, ps_cmd='Refresh', create_time=datetime.now(timezone.utc))
                    owner_ps_cmd.save()
                    msg = f"Refresh {orgAccountObj.name} queued for processing"
                messages.info(request, msg)             
                LOG.info(msg)
                enqueue_process_state_change(orgAccountObj.name)
            except Exception as e:
                status = 500
                LOG.exception("caught exception:")
                emsg = "Caught exception:"+repr(e)
        # GET just displays org_manage_cluster
        LOG.info("redirect to org-manage-cluster")
        for handler in LOG.handlers:
            handler.flush()
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def orgDestroyCluster(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if request.method == 'POST':
            orgAccountObj = OrgAccount.objects.get(id=orgAccountObj.id)
            status = 200
            task_id = ''
            emsg = ''
            msg=''
            try:
                try:
                    owner_ps_cmd = OwnerPSCmd.objects.get(org=orgAccountObj, ps_cmd='Destroy')
                    msg = f" -- IGNORING -- Destroy {orgAccountObj.name} already queued for processing"
                except OwnerPSCmd.DoesNotExist:
                    jrsp = remove_num_node_requests(request.user,orgAccountObj)
                    if jrsp['status'] == 'SUCCESS':
                        messages.info(request,jrsp['msg'])
                    else:
                        messages.error(request,jrsp['error_msg'])           
                    clusterObj = Cluster.objects.get(org=orgAccountObj)
                    if clusterObj.cnnro_ids is not None:
                        active_onns = OrgNumNode.objects.filter(id__in=clusterObj.cnnro_ids)
                        if active_onns.exists():
                            try:
                                for active_onn in active_onns:
                                    active_onn.delete()
                                messages.info(request,"Successfully deleted active Org Num Node requests")
                            except Exception as e:
                                LOG.exception("caught exception:")
                                messages.error(request, 'Error deleting active Org Num Node requests')
                    owner_ps_cmd = OwnerPSCmd.objects.create(user=request.user, org=orgAccountObj, ps_cmd='Destroy', create_time=datetime.now(timezone.utc))
                    owner_ps_cmd.save()
                    msg = f"Destroy {orgAccountObj.name} queued for processing"
                messages.info(request, msg)             
                LOG.info(msg)
                enqueue_process_state_change(orgAccountObj.name)
            except Exception as e:
                status = 500
                LOG.exception("caught exception:")
                messages.error(request, 'Error destroying cluster')
        # GET just displays org_manage_cluster
        LOG.info("redirect to org-manage-cluster")
        for handler in LOG.handlers:
            handler.flush()
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)


@login_required(login_url='account_login')
@verified_email_required
def orgReconcile(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if request.method == 'POST':
            orgAccountObj = OrgAccount.objects.get(id=orgAccountObj.id)
            try:
                reconcile_org(orgAccountObj)
            except Exception as e:
                status = 500
                LOG.exception("caught exception:")
                messages.error(request, f'Error Reconciling org {orgAccountObj.name}')
        # GET just displays org_manage_cluster
        LOG.info("redirect to org-manage-cluster")
        for handler in LOG.handlers:
            handler.flush()
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def clearOrgNumNodesReqs(request, pk):
    orgAccountObj = OrgAccount.objects.get(id=pk)
    LOG.info(f"{request.user.username} {request.method} {orgAccountObj.name} <owner:{orgAccountObj.owner.username}>")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if request.method == 'POST':
            jrsp = remove_num_node_requests(request.user,orgAccountObj)
            if jrsp['status'] == 'SUCCESS':
                messages.info(request,jrsp['msg'])
                LOG.info(jrsp['msg'])
                enqueue_process_state_change(orgAccountObj.name)
            else:
                messages.error(request,jrsp['error_msg']) 
                LOG.error(jrsp['error_msg'])          
        # GET just displays org_manage_cluster
        LOG.info("redirect to org-manage-cluster")
        for handler in LOG.handlers:
            handler.flush()
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def clearActiveNumNodeReq(request, pk):
    orgAccountObj = OrgAccount.objects.get(id=pk)
    clusterObj = Cluster.objects.get(org=orgAccountObj)
    LOG.info(f"request.POST:{request.POST} {request.user.username} {request.method} {orgAccountObj.name} <owner:{orgAccountObj.owner.username}>")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if request.method == 'POST':
            active_onns = OrgNumNode.objects.filter(id__in=clusterObj.cnnro_ids)
            if active_onns.exists():
                for active_onn in active_onns:
                    active_onn.delete()
                messages.info(request,"Successfully deleted active Org Num Node requests")
                clusterObj.cnnro_ids = []
                clusterObj.save(update_fields=['cnnro_ids'])
                enqueue_process_state_change(orgAccountObj.name)
            else:
                messages.info(request,"No active Org Num Node request to delete")
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def orgConfigure(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")

    if has_admin_privilege(user=request.user, orgAccountObj=orgAccountObj):
        try:
            available_versions = get_versions_for_org(orgAccountObj.name)
            all_available_asg_cfgs = get_asg_cfgs_for_all_versions()
            if request.method == 'POST':
                version = request.POST.get('version', None)
                asg_cfg = request.POST.get('asg_cfg', None)
                post_data = request.POST.copy()  # Create a mutable copy of the POST data
                if not post_data.get('asg_cfg'):
                    post_data['asg_cfg'] = 'None'  # Set default value if asg_cfg is empty

                # Create the form with modified POST data and the necessary choices
                config_form = OrgAccountCfgForm(
                    post_data, 
                    instance=orgAccountObj, 
                    available_versions=available_versions, 
                    available_asg_cfgs=all_available_asg_cfgs.get(version, []) # Get the available ASG configs for the selected version
                )
                if asg_cfg and asg_cfg in all_available_asg_cfgs:
                    LOG.info('config_form.fields[asg_cfg]: %s', config_form.fields['asg_cfg'])
                    config_form.fields['asg_cfg'].choices = [('None', 'None')] + [(v, v) for v in all_available_asg_cfgs[version]]
                    emsg = ''
   
                    if config_form.is_valid():
                        for field, value in config_form.cleaned_data.items():
                            LOG.info(f"Field: {field}, Value: {value}")
                        LOG.info(f"orgAccountObj:{orgAccountObj.id} name:{orgAccountObj.name} is_public:{orgAccountObj.is_public} version:{orgAccountObj.version} min_node_cap:{orgAccountObj.min_node_cap} max_node_cap:{orgAccountObj.max_node_cap} allow_deploy_by_token:{orgAccountObj.allow_deploy_by_token} destroy_when_no_nodes:{orgAccountObj.destroy_when_no_nodes}")
                        config_form.save()
                        # Force the cluster env to be reinitialized
                        clusterObj = Cluster.objects.get(org=orgAccountObj)
                        clusterObj.provision_env_ready = False
                        clusterObj.save()
                        LOG.info(f"saved clusterObj for orgAccountObj:{orgAccountObj.id} name:{orgAccountObj.name} is_public:{orgAccountObj.is_public} version:{orgAccountObj.version} ")
                        messages.success(request, f'org {orgAccountObj.name} cfg updated successfully')
                        enqueue_process_state_change(orgAccountObj.name)
                    else:
                        emsg = f"Input Errors:{config_form.errors.as_text()}"
                        messages.warning(request, emsg)
                        LOG.info(f"Did not save org_config for {orgAccountObj.name} {emsg}")
                        LOG.info("These are the fields as submitted:")
                        for field, value in config_form.data.items():
                            if field != 'csrfmiddlewaretoken':
                                LOG.info(f"Field: {field} - Value: {value}")
                        messages.error(request, emsg)
            else:
                config_form = OrgAccountCfgForm(
                    instance=orgAccountObj, 
                    available_versions=available_versions, 
                    available_asg_cfgs=all_available_asg_cfgs[orgAccountObj.version]
                )
                asg_cfg = None  # Ensure asg_cfg is initialized for GET requests
                if asg_cfg and asg_cfg in all_available_asg_cfgs:
                    config_form.fields['asg_cfg'].choices = [(v, v) for v in all_available_asg_cfgs[version]]
        except Exception as e:
            LOG.exception("caught exception:")
            emsg = "Server ERROR"
        LOG.info(f"{request.user.username} orgAccountObj:{request.method} {orgAccountObj.id} name:{orgAccountObj.name} is_public:{orgAccountObj.is_public} version:{orgAccountObj.version} min_node_cap:{orgAccountObj.min_node_cap} max_node_cap:{orgAccountObj.max_node_cap} allow_deploy_by_token:{orgAccountObj.allow_deploy_by_token} destroy_when_no_nodes:{orgAccountObj.destroy_when_no_nodes}")
        LOG.info("redirect to org-manage-cluster")
        for handler in LOG.handlers:
            handler.flush()
        return redirect('org-manage-cluster',pk=orgAccountObj.id)
    else:
        LOG.warning(f"{request.user.username} {request.method} {orgAccountObj.name} UNAUTHORIZED")
        messages.error(request, "Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def orgAccountHistory(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    LOG.info(f"{request.method} {orgAccountObj.name}")
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        cost_accounting(orgAccountObj)
        context = {'org': orgAccountObj,'today': datetime.now()} # TBD do we need tz=timezone.utc ?
        return render(request, 'users/org_account_history.html', context)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)


@login_required(login_url='account_login')
@verified_email_required
def ajaxOrgAccountHistory(request):
    orgAccountObj = get_orgAccountObj(request.GET.get("org_uuid", None))
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        if(request.headers.get('x-requested-with') == 'XMLHttpRequest') and (request.method == 'GET'):
            gran = request.GET.get("granularity", "undefined")
            LOG.info("%s %s %s", orgAccountObj.name,request.method, request.GET.get("granularity", "undefined"))
            orgCostObj = get_db_org_cost(gran, orgAccountObj)
            LOG.info(f"{orgAccountObj.name} {gran} cost refresh tm:{orgCostObj.cost_refresh_time}")
            if orgCostObj is not None:
                status = 200
                context = {'ccr': orgCostObj.ccr,'crt':  datetime.strftime(orgCostObj.cost_refresh_time, FMT_TZ)}
            else:
                status = 500
                context = {'ccr': {}}
            return JsonResponse(context, status=status)
        else:
            LOG.warning("%s %s redirected! browse",request.method,orgAccountObj.name)
            return redirect('browse')
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)


@login_required(login_url='account_login')
@verified_email_required
def orgAccountForecast(request, pk):
    orgAccountObj = get_orgAccountObj(pk)
    clusterObj = Cluster.objects.get(org__name=orgAccountObj.name)
    LOG.info("%s %s", request.method, orgAccountObj.name)
    if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
        update_burn_rates(orgAccountObj) # also updates clusterObj.version clusterObj.cur_nodes
        update_ddt(orgAccountObj) # ddt is drop dead times i.e. when the org runs out of money for min current and max node configurations
        create_all_forecasts(orgAccountObj)
        show_min_shutdown_date = (orgAccountObj.min_ddt <= (datetime.now(timezone.utc) + timedelta(days=DISPLAY_EXP_TM)))
        show_cur_shutdown_date = (orgAccountObj.cur_ddt <= (datetime.now(timezone.utc) + timedelta(days=DISPLAY_EXP_TM)))
        context = {'org': orgAccountObj, 'cluster':clusterObj, 'show_cur_shutdown_date': show_cur_shutdown_date, 'show_min_shutdown_date': show_min_shutdown_date}
        LOG.info('rendering org_account_forecast')
        return render(request, 'users/org_account_forecast.html', context)
    else:
        messages.error(request,"Unauthorized access")
        return HttpResponse('Unauthorized', status=401)

@login_required(login_url='account_login')
@verified_email_required
def ajaxOrgAccountForecast(request):
    if(request.headers.get('x-requested-with') == 'XMLHttpRequest') and (request.method == 'GET'):
        orgAccountObj = get_orgAccountObj(request.GET.get("org_uuid", None))
        LOG.info("%s %s %s", request.method, orgAccountObj.name,request.GET.get("granularity", "undefined"))
        gran = request.GET.get("granularity", "undefined")
        if gran == 'HOURLY':
            fc_min = orgAccountObj.fc_min_hourly
            fc_cur = orgAccountObj.fc_cur_hourly
            fc_max = orgAccountObj.fc_max_hourly
            br_min = orgAccountObj.min_hrly
            br_cur = orgAccountObj.cur_hrly
            br_max = orgAccountObj.max_hrly
            orgCostObj  = get_db_org_cost("HOURLY", orgAccountObj)
        elif gran == 'DAILY':
            fc_min = orgAccountObj.fc_min_daily
            fc_cur = orgAccountObj.fc_cur_daily
            fc_max = orgAccountObj.fc_max_daily
            br_min = orgAccountObj.min_hrly*24
            br_cur = orgAccountObj.cur_hrly*24
            br_max = orgAccountObj.max_hrly*24
            orgCostObj  = get_db_org_cost("DAILY", orgAccountObj)
        elif gran == 'MONTHLY':
            fc_min = orgAccountObj.fc_min_monthly
            fc_cur = orgAccountObj.fc_cur_monthly
            fc_max = orgAccountObj.fc_max_monthly
            br_min = orgAccountObj.min_hrly*24*30
            br_cur = orgAccountObj.cur_hrly*24*30
            br_max = orgAccountObj.max_hrly*24*30
            orgCostObj  = get_db_org_cost("MONTHLY", orgAccountObj)
        if orgCostObj is not None:
            cost_refresh_time = orgCostObj.cost_refresh_time
            cost_refresh_time_str = datetime.strftime(cost_refresh_time,"%Y-%m-%d %H:%M:%S %Z")
        #LOG.info("%s %s %s %s",gran,cost_refresh_time,cost_refresh_time_str)
        #LOG.info("gran:%s br_min:%2g br_cur:%2g br_max:%2g", gran, br_min, br_cur, br_max)
        context = {'br_min': br_min, 'br_cur': br_cur, 'br_max': br_max, 'gran': gran, 'fc_min': fc_min,
                   'fc_cur': fc_cur, 'fc_max': fc_max, 'cost_refresh_time': cost_refresh_time, 'cost_refresh_time_str': cost_refresh_time_str}
        status = 200
        # else:
        #     status = 500
        #     context = {'cost': {}}
        return JsonResponse(context, status=status)
    else:
        LOG.warning("%s %s redirected! browse",request.method,orgAccountObj.name)
        return redirect('browse')


@login_required(login_url='account_login')
@verified_email_required
def orgProfile(request, pk):
    try:
        # User must be in the PS_Developer group or the owner to modify the profile
        orgAccountObj = get_orgAccountObj(pk)
        LOG.info(f"{request.method} {orgAccountObj.name}")
        if has_admin_privilege(user=request.user,orgAccountObj=orgAccountObj):
            if request.method == "POST":
                # USING an Unbound form and setting the object explicitly one field at a time!
                f = OrgProfileForm(request.POST)
                LOG.info("Form")
                if(f.is_valid()):
                    orgAccountObj.point_of_contact_name = f.cleaned_data['point_of_contact_name']
                    orgAccountObj.email = f.cleaned_data['email']
                    orgAccountObj.save(update_fields=['point_of_contact_name','email'])
                    messages.success(request,'Profile succesfully saved')
                    LOG.info(f"Profile updated with point_of_contact_name:{orgAccountObj.point_of_contact_name} email:{orgAccountObj.email}")

                else:
                    LOG.error("Form error:%s", f.errors.as_text)
                    messages.warning(request, 'error in form')
            else:
                f = OrgProfileForm(instance=orgAccountObj)
            context = {'org': orgAccountObj, 'form': f}
            return render(request, 'users/org_profile.html', context)
        else:
            messages.warning(request, 'Insufficient privileges')
            LOG.warning("%s %s redirected! browse",request.method,orgAccountObj.name)
            return redirect('browse')

    except Exception as e:
        LOG.exception("caught exception:")
        emsg = "Caught exception:"+repr(e)
        messages.error(request, emsg)
        return redirect('browse')


@login_required(login_url='account_login')
@verified_email_required
@transaction.atomic
# atomic ensures org and cluster and orgCost are always created together
def orgAccountCreate(request):
    try:
        # User must be in the PS_Developer group
        if request.user.groups.filter(name='PS_Developer').exists():
            if request.method == 'POST':
                form = OrgAccountForm(request.POST)
                new_org,msg,emsg = add_org_cluster_orgcost(form,start=True)
                if msg != '':
                    messages.info(request,msg)
                    enqueue_process_state_change(new_org.name)
                if emsg != '':
                    messages.error(request,emsg)
                return redirect('browse')
            else:
                form = OrgAccountForm()
                return render(request, 'users/org_create.html', {'form': form})
        else:
            messages.warning(request, 'Insufficient privileges')
            return redirect('browse')

    except Exception as e:
        LOG.exception("caught exception:")
        emsg = "Caught exception:"+repr(e)
        messages.error(request, emsg)
        return redirect('browse')

@login_required(login_url='account_login')
def userProfile(request):
    LOG.info(request.method)
    try:
        userObj = request.user
        LOG.info("%s %s",request.method,userObj.username)
        if request.method == "POST":
            f = UserProfileForm(request.POST, instance=userObj)
            LOG.info("Form")
            if(f.is_valid()):
                LOG.info("Form save")
                f.save()
                messages.info(request, "Profile successfully updated")
                return redirect('browse')
            else:
                LOG.error("Form error:%s", f.errors.as_text)
                messages.warning(request, 'error in form')
        f = UserProfileForm(instance=userObj)
        context = {'user': userObj, 'form': f}
        return render(request, 'users/user_profile.html', context)

    except Exception as e:
        LOG.exception("caught exception:")
        emsg = "Caught exception:"+repr(e)
        LOG.error(emsg)
        messages.error(request, 'Server Error')
        LOG.warning("%s redirected! browse",request.user)
        return redirect('browse')

@login_required(login_url='account_login')
def browse(request):
    LOG.info(request.method)
    try:
        active_user = request.user
        if(active_user.is_superuser):
            LOG.error("Invalid access attempted by superuser")
            messages.error(request, 'Superusers should not access regular site')
            return redirect('/admin')
        else:
            org_member = {}
            is_member_of_org = {}
            org_pending = {}
            active_user = request.user
            org_cluster_is_deployed = {}
            org_cluster_deployed_state = {}
            org_cluster_cur_nodes = {}
            org_cluster_cur_version = {}
            org_cluster_connection_status = {}
            org_cluster_active_ps_cmd = {}
            user_is_owner = {}
            org_by_name = {}
            org_is_public = {}
            orgs = get_all_orgAccountObjs()
            user_is_org_admin = {}
            org_has_ddt = {}
            unaffiliated = 0
            any_memberships = False
            any_ownerships = False
            for o in orgs:
                try:
                    if o.name == 'uninitialized':
                        LOG.error(f"IGNORING org:{o.name}")
                        LOG.error(f"DELETING org:{o.name}")
                        o.delete()
                    else:    
                        update_ddt(o)
                        org_has_ddt.update({o.name:  (o.cur_ddt < datetime.now(timezone.utc)+timedelta(days=(10*365)))})
                        found_m = False
                        pend = False
                        members = get_MembershipsForUser(active_user)
                        clusterObj = Cluster.objects.get(org__name=o.name)
                        org_cluster_active_ps_cmd.update({o.name: clusterObj.active_ps_cmd})
                        org_cluster_deployed_state.update({o.name: clusterObj.deployed_state})
                        org_cluster_is_deployed.update({o.name: clusterObj.is_deployed})
                        org_cluster_cur_nodes.update({o.name: clusterObj.cur_nodes})
                        org_cluster_cur_version.update({o.name: clusterObj.cur_version})
                        org_cluster_connection_status.update({o.name: clusterObj.connection_status})
                        user_is_org_admin.update({o.name: request.user.groups.filter(name=f'{o.name}_Admin').exists()})
                        LOG.info(f"org:{o.name} user_is_org_admin:{request.user.groups.filter(name=f'{o.name}_Admin').exists()} is_public:{o.is_public} owner:{o.owner.username} active_user:{active_user.username}")
                        if o.owner == request.user:
                            any_ownerships = True
                        user_is_owner.update({o.name: (o.owner == request.user)})
                        org_by_name.update({o.name: o})
                        org_is_public.update({o.name: o.is_public})
                        for m in members:
                            if o is not None and m.org is not None:
                                if o.name == m.org.name:
                                    found_m = True
                                    if not o.is_public and not (o.owner == request.user):
                                        any_memberships = True
                                    org_member.update({o.name: m})
                                    pend = not m.active
                        if not found_m and not o.is_public:
                            unaffiliated = unaffiliated + 1
                        is_member_of_org.update({o.name: found_m})
                        org_pending.update({o.name: pend})
                except Exception as e:
                    LOG.exception("caught exception:")

        context = { 'org_member': org_member,
                    'is_member_of_org': is_member_of_org,
                    'user_is_org_admin': user_is_org_admin,
                    'org_by_name': org_by_name,
                    'org_pending': org_pending,
                    'org_has_ddt': org_has_ddt,
                    'org_accounts': orgs,
                    'org_cluster_deployed_state': org_cluster_deployed_state,
                    'org_cluster_is_deployed': org_cluster_is_deployed,
                    'org_cluster_cur_nodes': org_cluster_cur_nodes,
                    'org_cluster_cur_version': org_cluster_cur_version,
                    'org_cluster_connection_status': org_cluster_connection_status,
                    'org_cluster_active_ps_cmd': org_cluster_active_ps_cmd,
                    'user_is_owner': user_is_owner,
                    'user_is_developer': request.user.groups.filter(name='PS_Developer').exists(),
                    'any_unaffiliated': (unaffiliated>0),
                    'any_ownerships': any_ownerships,
                    'any_memberships': any_memberships,
                    'org_is_public': org_is_public,
                    'PROVISIONING_DISABLED': get_PROVISIONING_DISABLED(),
                    }

            # this filter 'get_item' is used inside the template
        @register.filter
        def get_item(dictionary, key):
            return dictionary.get(key)
        if(orgs.count() == 0):
            LOG.info("No orgs exist!")
            messages.info(
                request, 'No orgs exist yet; Have staff user create them')
        update_all_burn_rates()
    except Exception as e:
        LOG.exception("caught exception:")
        #emsg = "SW Error:%"+repr(e)
        return HttpResponse(status=500)
    for handler in LOG.handlers:
        handler.flush()
    return render(request, 'users/browse.html', context)

# @login_required(login_url='account_login')
# @verified_email_required
# def memberships(request):  # current session user
#     #LOG.info(request.method)
#     active_user = request.user
#     org_cluster_deployed_state = {}
#     org_cluster_connection_status = {}
#     org_cluster_active_ps_cmd = {}
#     user_is_owner = {}
#     membershipObjs = get_MembershipsForUser(active_user)
#     displayed_memberships = []
#     for m in membershipObjs:
#         if m.user.username.strip() == active_user.username.strip():
#             displayed_memberships.append(m)
#             o = get_orgAccountObjByName(m.org.name)
#             clusterObj = Cluster.objects.get(org__name=o.name)
#             org_cluster_deployed_state.update({o.name: clusterObj.deployed_state})
#             org_cluster_connection_status.update({o.name: clusterObj.connection_status})
#             org_cluster_active_ps_cmd.update({o.name: clusterObj.active_ps_cmd})
#             user_is_owner.update({o.name: (o.owner == request.user)})
#     #LOG.info(org_cluster_deployed_state)

#     context = { 'user': active_user,
#                 'memberships': displayed_memberships,
#                 'org_cluster_deployed_state': org_cluster_deployed_state,
#                 'org_cluster_connection_status': org_cluster_connection_status,
#                 'org_cluster_active_ps_cmd': org_cluster_active_ps_cmd,
#                 'is_developer': request.user.groups.filter(name='PS_Developer').exists(),
#                 'user_is_owner': user_is_owner
#                 }

#     # this filter 'get_item' is used inside the template
#     @register.filter
#     def get_item(dictionary, key):
#         return dictionary.get(key)
#     if(membershipObjs.count() > 0):
#         return render(request, 'users/memberships.html', context)
#     else:
#         messages.info(request,
#                       'You have no memberships; Find your organization then Click "Request Membership" ')
#         return redirect('browse')

@login_required(login_url='account_login')
@verified_email_required
def cancelMembership(request, pk):
    LOG.info(request.method)
    membershipObj = get_MembershipObj(pk)
    if request.method == 'POST':
        membershipObj.delete()
        return redirect('browse')
    context = {'object': membershipObj}
    return render(request, 'users/confirm_cancel_membership.html', context)

def add_org_cluster_orgcost(f,start=False):
    emsg=''
    msg=''
    new_org=None
    try:
        init_accounting_tm = datetime.now(timezone.utc)-timedelta(days=366) # force update
        if f.is_valid():
            new_org = f.save(commit=False)
            new_org.most_recent_charge_time=init_accounting_tm
            new_org.most_recent_credit_time=init_accounting_tm
            new_org.save()
            #LOG.info(new_org.most_recent_charge_time)
            cluster = Cluster.objects.create(org=new_org)
            cluster.save()
            granObjHr = getGranChoice(granularity="HOURLY")
            orgCostHr = OrgCost.objects.create(org=new_org, gran=granObjHr, tm=init_accounting_tm, cost_refresh_time=init_accounting_tm)
            #LOG.info(orgCostHr.tm)
            orgCostHr.save()
            granObjDay = getGranChoice(granularity="DAILY")
            orgCostDay = OrgCost.objects.create(org=new_org, gran=granObjDay, tm=init_accounting_tm, cost_refresh_time=init_accounting_tm)
            orgCostDay.save()
            granObjMonth = getGranChoice(granularity="MONTHLY")
            orgCostMonth = OrgCost.objects.create(org=new_org, gran=granObjMonth, tm=init_accounting_tm, cost_refresh_time=init_accounting_tm)
            orgCostMonth.save()
            LOG.info(f"added org:{new_org.name}")
            msg = init_new_org_memberships(new_org)
            # always add this to the OAUTH app (only one exists anyway)
            for app in Application.objects.all():
                domain = os.environ.get("DOMAIN")
                app.redirect_uris += '\n{}'.format(f"https://{new_org.name}.{domain}/redirect_uri/")
                app.save()
            enqueue_process_state_change(new_org.name)  # initializes the processing state
        else:
            emsg = f"Input Errors:{f.errors.as_text}"
    except Exception as e:
        LOG.exception("caught exception:")
        emsg = "Caught exception:"+repr(e)
    
    return new_org,msg,emsg



@login_required(login_url='account_login')
@verified_email_required
def reqNewMembership(request, pk):
    # create an instance
    q = get_MembershipObjsFiltered(pk, request.user)
    attempt_succeeded = True
    first_time = False
    try:
        if(q.count() == 0):
            m = Membership()
            m.user = request.user
            m.org = OrgAccount.objects.get(id=pk)
            m.save()
            first_time = True
            messages.success(
                request, f'{m.user.first_name} {m.user.last_name} your membership to {m.org} was recieved; We will review your request and if accepted we will send you an email with an activation notice')
        else:
            m = q.get()
        if(q.count() != 1):
            LOG.info(
                f"A membership record already exists for {m.user.username} {m.org}")

    except (OrgAccount.DoesNotExist, TypeError):
        attempt_succeeded = False
        messages.error(request, 'Membership request failed; Org does not exist or has no owner?')

    # Tell user what to do
    type = "Membership"
    context = {'m': m, 'user': request.user,
               'account_type': type, 'first_time': first_time}
    if(attempt_succeeded):
        # TBD change to message
        return render(request, 'users/req_new_account_notice.html', context)
    else:
        return render(request, 'users/req_new_account_failed_notice.html', context)

@login_required(login_url='account_login')
@verified_email_required
def provSysAdmin(request):

    if user_in_one_of_these_groups(user=request.user,groups=['PS_Developer']):
        jobs = get_scheduled_jobs()
        now = datetime.now(timezone.utc)
        context = {'now':now,'jobs':jobs,'PROVISIONING_DISABLED': get_PROVISIONING_DISABLED()}
        return render(request, 'prov_sys_admin.html', context=context)
    else:
        messages.error(request, 'You Do NOT have privileges to access this page')
        return redirect('browse')

@login_required(login_url='account_login')
@verified_email_required
def disableProvisioning(request): 
    req_msg = f"User:{request.user.username} requested disable provisioning"
    LOG.critical(f"{req_msg}")   
    error_msg, disable_msg, rsp_msg = disable_provisioning(request.user,req_msg)    
    if error_msg and error_msg != '':
        messages.error(request, error_msg)
    if disable_msg and disable_msg != '':
        messages.warning(request, disable_msg)
    if rsp_msg and rsp_msg != '':
        messages.warning(request, rsp_msg)
    return redirect('browse')