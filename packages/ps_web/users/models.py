from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import JSONField
from phonenumber_field.modelfields import PhoneNumberField
import django.utils.timezone
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from os import environ
from django_celery_results.models import TaskResult

class User(AbstractUser):
    list_display = ['is_active', 'username', 'is_superuser',
                    'is_staff', 'first_name', 'last_name',
                    'email', 'date_joined' ]


class Membership(models.Model):
    id = models.UUIDField(default=uuid.uuid4,
                          unique=True,
                          primary_key=True,
                          editable=False)
    user = models.ForeignKey('User',
                             null=True,
                             blank=True,
                             on_delete=models.SET_NULL,
                             editable=False,
                             related_name='fk_user')
    org = models.ForeignKey('OrgAccount',
                            on_delete=models.SET_NULL,
                            null=True,
                            blank=True,
                            editable=False,
                            related_name='fk_org')
    active = models.BooleanField(default=False, editable=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    delete_requested = models.BooleanField(default=False, editable=True)
    # print("created: ",creation_date)
    activation_date = models.DateTimeField(auto_now_add=True)

def __str__(self):  # TBD add validators
    username = self.user.username if self.user else 'N/A'
    
    if self.org:
        return f"{self.org.name.replace(' ', '_')}:{username}"
    return f"NoOrg?:{username}"

class OrgAccount(models.Model):
    # Validators limits:
    MIN_NODES = 0
    DEF_NODES = 2
    DEF_ADMIN_MAX_NODES = 10 # overrideable up to ABS_MAX_NODES
    ABS_MAX_NODES = 1000 # can be changed via ecs task template

    id = models.UUIDField(default=uuid.uuid4,
                          unique=True,
                          primary_key=True,
                          editable=False)
    owner = models.ForeignKey('User',
                              on_delete=models.CASCADE,
                              null=True,
                              blank=False)
    name = models.CharField(max_length=200,
                            default='uninitialized',
                            blank=False,
                            null=False)
    point_of_contact_name = models.CharField(max_length=200,
                                             default='support team',
                                             blank=False,
                                             null=False)
    email = models.EmailField(default='support@mail.slideruleearth.io')
    max_allowance = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)
    monthly_allowance = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)
    balance = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)
    fytd_accrued_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)
    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    node_mgr_fixed_cost = models.FloatField(default=0.153)  # Overhead==> (monitor is c6a.large, orchestrator is c6a.large;  c6a.large = 0.0765/hour)
    node_fixed_cost = models.FloatField(default=0.226)  # Per Node (r5a.xlarge = 0.226)
    desired_num_nodes = models.IntegerField(editable=True,  # this field can be edited in admin panel by user with admin privileges
                                            default=MIN_NODES,
                                            validators=[
                                                MinValueValidator(MIN_NODES),
                                                MaxValueValidator(ABS_MAX_NODES)])
    min_node_cap = models.IntegerField( editable=True,   # this field can be edited in admin panel by user with admin privileges
                                        default=MIN_NODES,
                                        validators=[
                                            MinValueValidator(MIN_NODES),
                                            MaxValueValidator(ABS_MAX_NODES)])
    max_node_cap = models.IntegerField( editable=True,   # this field is actual cluster state
                                        default=DEF_ADMIN_MAX_NODES,
                                        validators=[
                                            MinValueValidator(MIN_NODES),
                                            MaxValueValidator(ABS_MAX_NODES)])
    max_hrly = models.FloatField(default=0.0000001)
    cur_hrly = models.FloatField(default=0.0000001)
    min_hrly = models.FloatField(default=0.0000001)
    min_ddt = models.DateTimeField(editable=True,default=django.utils.timezone.now)
    cur_ddt = models.DateTimeField(editable=True,default=django.utils.timezone.now)
    max_ddt = models.DateTimeField(editable=True,default=django.utils.timezone.now)

    most_recent_charge_time = models.DateTimeField(editable=True,default=django.utils.timezone.now)  # from Cost Explorer
    most_recent_credit_time = models.DateTimeField(editable=True,default=django.utils.timezone.now)  # from utils.reconcile
    most_recent_recon_time = models.DateTimeField(editable=True,default=django.utils.timezone.now)  # from utils.reconcile


    fc_min_hourly = models.JSONField(default=dict)  # current forecast
    fc_min_daily = models.JSONField(default=dict)  # current forecast
    fc_min_monthly = models.JSONField(default=dict)  # current forecast

    fc_cur_hourly = models.JSONField(default=dict)  # current forecast
    fc_cur_daily = models.JSONField(default=dict)  # current forecast
    fc_cur_monthly = models.JSONField(default=dict)  # current forecast

    fc_max_hourly = models.JSONField(default=dict)  # current forecast
    fc_max_daily = models.JSONField(default=dict)  # current forecast
    fc_max_monthly = models.JSONField(default=dict)  # current forecast
    version = models.CharField( editable=True,   # includes the v if is a release like 'v1.4.1'
                                max_length=16, 
                                blank=False,
                                null=False,
                                default="latest") # version of terraform files
    mfa_code = models.CharField(editable=True,
                                        max_length=16, 
                                        blank=False,
                                        null=False,
                                        default="sliderule_1492") # mfa-code entered
    # this is an editable limit using admin privileges
    admin_max_node_cap = models.IntegerField(editable=True,   # this field can be edited in admin panel by user with admin privileges
                                                default=DEF_ADMIN_MAX_NODES,
                                                validators=[
                                                    MinValueValidator(MIN_NODES),
                                                    MaxValueValidator(ABS_MAX_NODES)])
    tokens = models.JSONField(default=dict)
    tokens_time =  models.DateTimeField(default=django.utils.timezone.now)
    time_to_live_in_mins = models.IntegerField(editable=True,default=60,validators=[MinValueValidator(15)]) 
    allow_deploy_by_token = models.BooleanField(default=True)
    destroy_when_no_nodes = models.BooleanField(default=True)
    is_public = models.BooleanField(editable=True,default=False)
    pcqr_display_age_in_hours = models.IntegerField(editable=True, default=72)
    pcqr_retention_age_in_days = models.IntegerField(editable=True, default=14)
    loop_count = models.BigIntegerField(editable=True,default=0)
    num_owner_ps_cmd = models.BigIntegerField(editable=True,default=0)
    num_ps_cmd = models.BigIntegerField(editable=True,default=0)
    num_ps_cmd_successful = models.BigIntegerField(editable=True,default=0)
    num_onn = models.BigIntegerField(editable=True,default=0) # deprecated
    provisioning_suspended = models.BooleanField(editable=True,default=False)
    num_setup_cmd = models.BigIntegerField(editable=True,default=0)
    num_setup_cmd_successful = models.BigIntegerField(editable=True,default=0)
    spot_max_price = models.FloatField(editable=True,default=0.17)
    spot_allocation_strategy = models.CharField(editable=True,max_length=32,default='lowest-price')
    asg_cfg = models.CharField(editable=True,max_length=32,default='unselected')

    def __str__(self):
        return str(self.name)


class Cluster(models.Model):
    org = models.OneToOneField(OrgAccount,
                               on_delete=models.CASCADE,
                               primary_key=True,
                               editable=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    mgr_ip_address = models.GenericIPAddressField(default='0.0.0.0', editable=True)
    active_ps_cmd = models.CharField(max_length=32,
                                     default='',
                                     blank=True,
                                     null=False,
                                     editable=True)
    is_deployed = models.BooleanField(editable=True,
                                      default=False)
    deployed_state = models.CharField(max_length=64,
                                      default='unknown',
                                      blank=False,
                                      null=False,
                                      editable=True)

    connection_status = models.CharField(max_length=64,
                                      default='unknown',
                                      blank=False,
                                      null=False,
                                      editable=True)

    version_query_log = models.TextField(editable=False, default="")
    cnnro_ids = JSONField(null=True, blank=True)  # This will store a list of UUIDs
    cur_nodes = models.IntegerField(default=0,editable=False)  # actual value seen from boto3
    cur_min_node_cap = models.IntegerField( editable=True,   # this field is actual cluster state
                                            blank=True,
                                            null=True)
    cur_max_node_cap = models.IntegerField( editable=True,   # this field is actual cluster state
                                            blank=True,
                                            null=True)
    cur_version = models.CharField( editable=True,   # includes the v if is a release like 'v1.4.1'
                                    max_length=16, 
                                    blank=True,
                                    null=True) # current version of sw terraform files
    is_public = models.BooleanField(editable=True,default=False)
    expire_time = models.DateTimeField(editable=True,blank=True,null=True)
    provision_env_ready = models.BooleanField(editable=True,default=False)
    prov_env_version = models.CharField(editable=True,   # includes the v if is a release like 'v1.4.1'
                                        max_length=16, 
                                        blank=True,
                                        null=True) # current version of sw terraform files
    prov_env_is_public = models.BooleanField(editable=True,default=False)

# use Migration to create a static table with one entry per choice for GranChoice (see REAMDME)

class GranChoice(models.Model):
    HOUR = 'HOURLY'  # NOTE these match ps_server enum
    DAY = 'DAILY'
    MONTH = 'MONTHLY'
    GRAN_CHOICES = [(HOUR, 'Hourly'), (DAY, 'Daily'), (MONTH, 'Monthly')]
    granularity = models.CharField(
        max_length=7, choices=GRAN_CHOICES, default=HOUR, primary_key=True)


class OrgCost(models.Model):  # Wrapper for Cost Explorer API
    org = models.ForeignKey('OrgAccount',
                            on_delete=models.CASCADE,
                            null=True,
                            blank=True,
                            editable=False,
                            related_name='fk_c_org')
    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    gran = models.ForeignKey(GranChoice, on_delete=models.PROTECT,
                             null=True,
                             blank=True,
                             editable=False,
                             related_name='fk_gran')
    tm = models.DateTimeField(editable=True,default=django.utils.timezone.now)
    cnt = models.IntegerField(default=0)
    avg = models.FloatField(default=0.0)
    min = models.FloatField(default=0.0)
    max = models.FloatField(default=0.0)
    std = models.FloatField(default=0.0)
    ccr = models.JSONField(default=dict)  # current cost report
    # last time we got hr/day/month cost reports for this org
    # from the aws cost explorer (minimize # calls to 3 a day per
    cost_refresh_time = models.DateTimeField(editable=True,default=django.utils.timezone.now)

class OrgNumNode(models.Model):
    id = models.UUIDField(default=uuid.uuid4,
                          unique=True,
                          primary_key=True,
                          editable=False)
    user = models.ForeignKey('User',
                             null=True,
                             blank=True,
                             on_delete=models.CASCADE,
                             editable=False,
                             related_name='fk_user_onn')
    org = models.ForeignKey('OrgAccount',
                            on_delete=models.CASCADE,
                            null=True,
                            blank=True,
                            editable=False,
                            related_name='fk_org_onn')
    desired_num_nodes = models.IntegerField(editable=True,  # this field can be edited in admin panel by user with admin privileges
                                            default=OrgAccount.MIN_NODES,
                                            validators=[
                                                MinValueValidator(OrgAccount.MIN_NODES),
                                                MaxValueValidator(OrgAccount.ABS_MAX_NODES)])
    expiration = models.DateTimeField(editable=True,null=True,blank=True)
    has_active_ps_cmd = models.BooleanField(default=False)

class PsCmdResult(models.Model):
    id = models.UUIDField(default=uuid.uuid4,
                          unique=True,
                          primary_key=True,
                          editable=False)
    org = models.ForeignKey('OrgAccount',
                            null=True,
                            on_delete=models.CASCADE,
                            blank=True,
                            editable=False,
                            related_name='fk_org_cr')
    ps_cmd_output = models.TextField(   help_text='Output from the provisioning system server',
                                        default='',
                                        editable=False,
                                        verbose_name='Provision Cmd Results')
    error = models.TextField(   help_text='Errors/Warnings processing cmd',
                                default='',
                                editable=False,
                                verbose_name='Provision Server Errors')
    creation_date = models.DateTimeField(auto_now_add=True)
    ps_cmd_summary_label = models.TextField(help_text='ps cmd task output',
                                            default='',
                                            editable=False,
                                            verbose_name='Provision Cmd')
    expiration = models.DateTimeField(editable=False,blank=True,null=True,default=django.utils.timezone.now)
   
class OwnerPSCmd(models.Model):
    id = models.UUIDField(default=uuid.uuid4,
                          unique=True,
                          primary_key=True,
                          editable=False)
    user = models.ForeignKey('User',
                             null=True,
                             blank=True,
                             on_delete=models.CASCADE,
                             editable=False,
                             related_name='fk_user_opscmd')
    org = models.ForeignKey('OrgAccount',
                            on_delete=models.CASCADE,
                            null=True,
                            blank=True,
                            editable=False,
                            related_name='fk_org_opscmd')
    ps_cmd = models.CharField(  max_length=32,
                                default='',
                                blank=True,
                                null=True,
                                editable=False)
    deploy_values = models.JSONField(default=dict,null=True,blank=True)
    create_time = models.DateTimeField(editable=True,blank=True,null=True)
    
