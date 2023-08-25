from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.db import models
from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# Register your models here.
from .models import User, OrgAccount, Membership, Cluster, Cost, ClusterNumNode, PsCmdResult, OwnerPSCmd
from .models import GranChoice,PsCmdResult
from django.contrib.auth import get_user_model

# this will force use of allauth login throttle for admin logins as well
# i.e. ACCOUNT_LOGIN_ATTEMPTS_LIMIT and ACCOUNT_LOGIN_ATTEMPTS_TIMEOUT 
admin.site.login = login_required(admin.site.login)

class UserAdmin(admin.ModelAdmin):
    list_display = ['is_active', 'username', 'is_superuser',
                    'is_staff', 'first_name', 'last_name', 'email', 'date_joined']
    list_display_links = ['username']
    list_filter = ('is_active', 'is_superuser', 'is_staff', 'date_joined')
    search_fields = ['username', 'last_name', 'first_name', 'email']

admin.site.register(get_user_model(), UserAdmin)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user_full_name', 'user', 'org', 'active', 'creation_date', 'modified_date')
    list_display_links = ['user', 'org']
    list_filter = ('user', 'org', 'active', 'creation_date', 'modified_date')
    search_fields = ('user__username','user__first_name','user__last_name')
    def user_full_name(self, obj):
        return obj.user.get_full_name()
    user_full_name.short_description = 'User Full Name'

    def user_username(self, obj):
        return obj.user.username
    user_username.short_description = 'Username'

@admin.register(OrgAccount)
class OrgAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'max_allowance', 'monthly_allowance',
                    'balance', 'max_hrly', 'cur_hrly', 'min_hrly', 'min_ddt', 'cur_ddt', 'max_ddt',
                    'node_mgr_fixed_cost', 'node_fixed_cost',
                    'desired_num_nodes', 'min_node_cap', 'max_node_cap', 'admin_max_node_cap',
                    'most_recent_charge_time', 'most_recent_credit_time',
                    'creation_date', 'modified_date', 'is_public', 'version', 'loop_count')
    list_display_links = ['name']
    list_filter = ('name', 'owner', 'max_allowance', 'monthly_allowance',
                   'balance', 'max_hrly', 'cur_hrly', 'min_hrly', 'min_ddt', 'cur_ddt', 'max_ddt',
                   'node_mgr_fixed_cost', 'node_fixed_cost',
                   'desired_num_nodes', 'min_node_cap', 'max_node_cap', 'admin_max_node_cap',
                   'most_recent_charge_time', 'most_recent_credit_time',
                   'creation_date', 'modified_date', 'is_public', 'version', 'loop_count')
    #readonly_fields = ('id')


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ('org', 'creation_date', 'modified_date','cur_min_node_cap','cur_max_node_cap','cur_version',
                    'active_ps_cmd', 'mgr_ip_address', 'is_deployed', 'deployed_state',
                    'allow_deploy_by_token',)

    list_filter = ('org', 'creation_date', 'modified_date','cur_min_node_cap','cur_max_node_cap','cur_version',
                   'active_ps_cmd', 'mgr_ip_address', 'is_deployed', 'deployed_state',
                    'allow_deploy_by_token',)
    list_display_links = ['org']
    readonly_fields = ['org','cur_nodes']

@admin.register(Cost)
class ClusterCostAdmin(admin.ModelAdmin):
    list_display = ('org', 'creation_date', 'modified_date',
                    'gran', 'tm', 'cost_refresh_time', 'cnt', 'avg', 'min', 'max', 'std')
    list_filter = ('org', 'creation_date', 'modified_date',
                   'gran', 'tm', 'cost_refresh_time', 'cnt', 'avg', 'min', 'max', 'std')

@admin.register(ClusterNumNode)
class ClusterNumNodeAdmin(admin.ModelAdmin):
    list_display = ('cluster', 'desired_num_nodes', 'expiration', 'user')
    list_filter = ('cluster', 'desired_num_nodes', 'expiration', 'user')

# Hackalert use a data fixture to populate static data then remove this
@admin.register(GranChoice)
class GranChoiceAdmin(admin.ModelAdmin):
    list_display = ('granularity',)

class PsCmdResultAdmin(admin.ModelAdmin):
    list_display = ('org', 'creation_date', 'expiration', 'ps_cmd_summary_label_formatted', 'ps_cmd_output_formatted', 'error_formatted')
    list_filter = ('org','creation_date','expiration')
    search_fields = ('org__name', 'ps_cmd_summary_label', 'ps_cmd_output', 'error')
    list_display_links = ['org']
    readonly_fields = ['org','expiration','ps_cmd_summary_label_formatted', 'ps_cmd_output_formatted','error_formatted' ]

    def ps_cmd_summary_label_formatted(self, obj):
        return format_html('<div style="max-height: 30px; overflow: auto;">{}</div>', mark_safe(obj.ps_cmd_summary_label))
    ps_cmd_summary_label_formatted.short_description = 'PS Command'

    def ps_cmd_output_formatted(self, obj):
        return format_html('<div style="max-height: 100px; overflow: auto;">{}</div>', mark_safe(obj.ps_cmd_output))
    ps_cmd_output_formatted.short_description = 'PS Command Output'

    def error_formatted(self, obj):
        return format_html('<div style="max-height: 100px; overflow: auto;">{}</div>', obj.error)
    error_formatted.short_description = 'Errors'


admin.site.register(PsCmdResult, PsCmdResultAdmin)

@admin.register(OwnerPSCmd)
class OwnerPSCmdAdmin(admin.ModelAdmin):
    list_display = ('user','org','ps_cmd','deploy_values','create_time')
    list_display_links = ('user','org')
    list_filter = ('user','org','ps_cmd','deploy_values','create_time')
    readonly_fields = ('user','org','ps_cmd','deploy_values','create_time')
