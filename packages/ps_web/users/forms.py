from django import forms
from django.forms import ModelForm
from django.contrib.auth.forms import UserCreationForm, UsernameField, UserChangeForm
from .models import Membership, OrgAccount, Cluster, User, OrgNumNode
from captcha.fields import CaptchaField
from datetime import datetime,timedelta
from datetime import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from .global_constants import ONN_MIN_TTL, ONN_MAX_TTL

from allauth.account.forms import LoginForm
from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Layout, Div, Row, Column, Field
from django.core.exceptions import ValidationError
from django.forms.widgets import NumberInput
from django.forms import ModelForm, NumberInput, TextInput, CheckboxInput, Widget
import logging
LOG = logging.getLogger('django')


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(max_length=30, label='First Name')
    last_name = forms.CharField(max_length=30, label='Last Name')
    username = forms.CharField(max_length=150, label='Username')
    captcha = CaptchaField()

    def save(self, request):
        user = super(CustomSignupForm, self).save(request)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.username = self.cleaned_data['username']
        user.save()
        return user

class MyCustomSocialSignupForm(SocialSignupForm):
    first_name = forms.CharField(max_length=30, label='First Name')
    last_name = forms.CharField(max_length=30, label='Last Name')
    username = forms.CharField(max_length=150, label='Username')

    def save(self, request):
        # Ensure you call the parent class's save.
        # .save() returns a User object.
        user = super(MyCustomSocialSignupForm, self).save(request)

        # Add your own processing here.
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.username = self.cleaned_data['username']
        user.save()
        # You must return the original result.
        return user
    
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['username', 'first_name',
                  'last_name', 'email']
        field_classes = {'username': UsernameField}
        required = ['username']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

# def desired_num_nodes_validator(min_nodes,max_nodes):
#     def _desired_num_nodes_validator(value):
#         if min_nodes == 0:
#             min = 1
#         else:
#             min = min_nodes
#         if value < min or value > max_nodes:
#             raise ValidationError(f'desired_num_nodes must be between {min} and {max_nodes}')
#     return _desired_num_nodes_validator

class OrgNumNodeForm(forms.ModelForm):
    ttl_minutes = forms.IntegerField(required=True, min_value=0, label='TTL minutes')

    class Meta:
        model = OrgNumNode
        fields = ['desired_num_nodes']

    def __init__(self, *args, **kwargs):    
        self.min_nodes = kwargs.pop('min_nodes', None)
        self.max_nodes = kwargs.pop('max_nodes', None)
        super().__init__(*args, **kwargs)
        # self.fields['desired_num_nodes'].validators.append(desired_num_nodes_validator(self.min_nodes, self.max_nodes))
        if self.min_nodes == 0:
            self.fields['desired_num_nodes'].initial = 1
        else:
            self.fields['desired_num_nodes'].initial = self.min_nodes
        self.fields['ttl_minutes'].initial = 15

    def clean_ttl_minutes(self):
        ttl_minutes = self.cleaned_data['ttl_minutes']
        if ttl_minutes < ONN_MIN_TTL:
            ttl_minutes = ONN_MIN_TTL
        if ttl_minutes > ONN_MAX_TTL:
            ttl_minutes = ONN_MAX_TTL
        return ttl_minutes


class MembershipForm(forms.Form):
    username = forms.CharField(disabled=True)
    firstname = forms.CharField(disabled=True)
    lastname = forms.CharField(disabled=True)
    active = forms.BooleanField(required=False)
    delete = forms.BooleanField(required=False)


class OrgAccountForm(ModelForm):
    class Meta:
        model = OrgAccount
        fields = ['owner', 'name', 'point_of_contact_name', 'email', 'max_allowance',
                  'monthly_allowance', 'balance', 'admin_max_node_cap','is_public']

class OrgAccountCfgForm(ModelForm):
    version = forms.ChoiceField(widget=forms.Select(attrs={'id': 'version'}))
    is_public = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'id': 'is_public'}))
    spot_allocation_strategy = forms.ChoiceField(widget=forms.Select(attrs={'id': 'spot_allocation_strategy'}))
    asg_cfg = forms.ChoiceField(widget=forms.Select(attrs={'id': 'asg_cfg'}))  # Add this line
    def __init__(self, *args, **kwargs):
        available_versions = kwargs.pop('available_versions', None)
        available_asg_cfgs = kwargs.pop('available_asg_cfgs', None)
        LOG.info(f'available_asg_cfgs: {available_asg_cfgs}')
        super().__init__(*args, **kwargs)
        if available_versions:
            self.fields['version'].choices = [(v, v) for v in available_versions]
        if available_asg_cfgs:
            available_asg_cfgs_by_version = available_asg_cfgs.get(self.instance.version, {})
            self.fields['asg_cfg'].choices = [(v, v) for v in available_asg_cfgs_by_version]
        max_value = OrgAccount.ABS_MAX_NODES
        width = len(str(max_value))
        self.fields['min_node_cap'].widget = NumberInput(attrs={'style': f'width: {width}em'})
        self.fields['max_node_cap'].widget = NumberInput(attrs={'style': f'width: {width}em'})
        self.fields['spot_allocation_strategy'].choices = [
            ('lowest-price', 'lowest-price'), 
            ('capacity-optimized', 'capacity-optimized'), 
            ('capacity-optimized-prioritized', 'capacity-optimized-prioritized'), 
            ('price-capacity-optimized', 'price-capacity-optimized'),
        ]   
    class Meta:
        model = OrgAccount
        fields = ['provisioning_suspended', 'is_public', 'version', 'min_node_cap', 'max_node_cap', 'allow_deploy_by_token', 'destroy_when_no_nodes', 'spot_max_price', 'spot_allocation_strategy', 'asg_cfg']


class OrgProfileForm(ModelForm):
    class Meta:
        model = OrgAccount
        fields = ['point_of_contact_name', 'email', ]


class ClusterForm(ModelForm):
    class Meta:
        model = Cluster
        fields = '__all__'

class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super(CustomLoginForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_class = 'form-horizontal w-100'
        self.helper.label_class = 'col-lg-2 w-100'
        self.helper.field_class = 'col-lg-8 w-100'
