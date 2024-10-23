from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework_simplejwt.settings import api_settings
from allauth.socialaccount.models import SocialAccount

from rest_framework.decorators import api_view
from api.serializers import MembershipSerializer, OrgTokenObtainPairSerializer, OrgTokenObtainPairGitHubSerializer, OrgTokenRefreshSerializer
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken
from datetime import datetime, timezone, timedelta
from users.models import Membership, OrgAccount, User, Cluster, OrgNumNode
from users.ps_errors import ClusterDeployAuthError
import logging
import json
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenBackendError
from users.tasks import process_num_nodes_api,update_cur_num_nodes,remove_num_node_requests,set_PROVISIONING_DISABLED,enqueue_process_state_change
from users.utils import user_in_one_of_these_groups,disable_provisioning
from users.global_constants import *
from oauth2_provider.views.generic import ProtectedResourceView
from django.http import JsonResponse
from django.contrib.auth import authenticate, login
from django.conf import settings
import requests

LOG = logging.getLogger('django')
JWT_authenticator = JWTAuthentication()


class DummySerializer(serializers.Serializer):
    pass



def get_user_in_token(request):
    """
    Authenticate the user based on the JWT token provided in the request.
    
    Parameters:
        request: The HTTP request object containing the JWT token.
    
    Returns:
        tuple: A tuple containing a response dictionary, HTTP status code,
        and user object extracted from the token.
    """
    jrsp = {'status': '','error_msg': "", 'msg': ""}
    try:
        LOG.info(f"request: {request}")
        #if settings.DEBUG:
        LOG.info(f"Request headers: {request.headers}")

        status = 200
        msg = ''
        user_in_token = None

        # authenitcate() verifies and decode the token
        # if token is invalid, it raises an exception and returns 401
        response = JWT_authenticator.authenticate(request)
        if response is not None:
            # unpacking
            user_in_token , token = response
            jrsp = {'status': 'Success','error_msg': "", 'msg': f'User {user_in_token.username} is authenticated'}
            #LOG.info(f"token claims: {token.payload}")
        else:
            msg = "No token is provided in the header or the header is missing"
            LOG.error(msg)
            jrsp = {'status': "FAILED","error_msg":msg}
            status = 400
    except KeyError as v:
        LOG.exception("caught KeyError exception:")
        jrsp = {'status': "FAILED","error_msg":"invalid token ke"}
        status=400
    except ValidationError as v:
        LOG.exception("caught ValidationError exception:")
        jrsp = {'status': "FAILED","error_msg":"invalid token ve"}
        status=400
    except InvalidToken as e:
        LOG.info(f"{request}")
        LOG.error(f"caught InvalidToken exception:{str(e)}")
        LOG.exception("caught InvalidToken exception:")
        jrsp = {'status': "FAILED","error_msg":"invalid token"}
        status=401
    except Exception as e:
        LOG.exception("caught exception:")
        jrsp = {'status': "FAILED","error_msg":"Server Error"}
        status = 500
    LOG.info(f" returns status:{status} jrsp:{jrsp} user_in_token:{user_in_token.username if user_in_token is not None else None}")
    return jrsp,status,user_in_token

def get_token_org_active_membership(request,org_name):
    try:
        #LOG.info(f"{org_name} {request}")
        status = 200
        msg = ''
        active = False
        user_in_token = None
        now = datetime.now(timezone.utc)
        token_expire_date = now

        jrsp,status,user_in_token = get_user_in_token(request)
        if status != 200:
            LOG.warning(f"get_user_in_token returned {status}")
            return jrsp,status,active,user_in_token,token_expire_date

        try:
            orgAccountObj = OrgAccount.objects.get(name=org_name)
        except (OrgAccount.DoesNotExist):
            msg = f"Unknown org:{org_name}"
            LOG.warning(msg)
            jrsp = {'status': "FAILED","error_msg":msg}
            return jrsp,400,False,'',token_expire_date
        try:
            token = request.META.get('HTTP_AUTHORIZATION', " ").split(' ')[1]
            # Always verify=False for HMAC algorithm
            valid_data = TokenBackend(algorithm='HS256').decode(token, verify=False)
        except TokenBackendError as e:
            LOG.exception(e)
            jrsp = {'status': "FAILED","error_msg":"INVALID token"}
            return jrsp,400,False,'',token_expire_date  
        except Exception as e:
            LOG.exception(e)
            jrsp = {'status': "FAILED","error_msg":"INVALID token"}
            return jrsp,400,False,'',token_expire_date  

        token_expires = float(valid_data['exp'])
        jti = valid_data['jti']
        token_expire_date = datetime.fromtimestamp(token_expires,tz=timezone.utc).replace(microsecond=0)
        LOG.info(f"exp:{token_expire_date} <= now:{now}?")
        if(token_expire_date <= now): # Framework should catch this ... just in case
            msg = "Token is expired"
            LOG.warning(msg)
            jrsp = {'status': "FAILED","error_msg":"Token is expired"}
            status=400
        else:
            LOG.info(f"token_expire_time: {datetime.strftime(datetime.fromtimestamp(token_expires,tz=timezone.utc), FMT)}")
            org_name_in_token = valid_data['org_name']
            user_id_in_token = valid_data['user_id']
            try:
                user_in_token = User.objects.get(id=user_id_in_token)
            except (User.DoesNotExist):
                LOG.exception("caught exception:")
                jrsp = {'status': "FAILED","error_msg":"user id in token is invalid"}
                status=400
                return jrsp,status,False,'',token_expire_date                 
            try:
                membership  = Membership.objects.filter(org=orgAccountObj).get(user=user_in_token)               
            except (Membership.DoesNotExist):
                LOG.exception("caught exception:")
                jrsp = {'status': "FAILED","error_msg":f"user{user_in_token.username} is not a member of {orgAccountObj.name}?"}
                status=400
                return jrsp,status,False,'',token_expire_date   
            try:
                if org_name == org_name_in_token:
                    serializer  = MembershipSerializer(membership, many=False)
                    #LOG.info('serializer_data:%s',serializer.data)
                    active = serializer.data['active']
                    LOG.info(active)
                    jrsp = {'active': active}
                    status = 200
                else:
                    jrsp = {'active': "false"}
                    emsg = f"Token claim org:{org_name_in_token} does not match organization given:{org_name} "
                    LOG.warning(emsg)
                    jrsp = {'status': "FAILED","error_msg":emsg}
                    status=400
            except ClusterDeployAuthError as e:
                msg = f"Org {orgAccountObj.name} is not configured to allow auto-deploy by token"
                LOG.exception(msg)
                jrsp = {'status': "FAILED","error_msg":msg}
                status = 401
            except Exception as e:
                LOG.exception("caught exception:")
                jrsp = {'status': "FAILED","error_msg":"Server Error"}
                status = 500
    except KeyError as v:
        LOG.exception("caught KeyError exception:")
        jrsp = {'status': "FAILED","error_msg":"invalid token ke"}
        status=400
    except ValidationError as v:
        LOG.exception("caught ValidationError exception:")
        jrsp = {'status': "FAILED","error_msg":"invalid token ve"}
        status=400
    except Exception as e:
        LOG.exception("caught exception:")
        jrsp = {'status': "FAILED","error_msg":"Server Error"}
        status = 500
    LOG.info(f" returns status:{status} active:{active} jrsp:{jrsp} username:{user_in_token.username}")
    return jrsp,status,active,user_in_token,token_expire_date 

class MembershipStatusView(generics.RetrieveAPIView):
    '''
        Takes an org_name and returns the membership status ("Active": True/False ) of the user in organization contained in the claims of the token.
        Users membership is controlled by the organization's admins.
        NOTE: the org_name passed as a parameter must match the organization of the claim in the token that is used for authorization.
    '''
    serializer_class = DummySerializer
    def get(self, request, org_name, *args, **kwargs):
        jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
        return Response(jrsp, status=http_status)   

class DesiredNumNodesView(generics.UpdateAPIView):
    '''
        Takes an org_name and desired_num_nodes and creates an OrgNumNode request for the org. 
        This will go into the pool of requests for the org.
        This request will expire when the token expires (one hour). 
        The msg field of the JSON response will contain the this expiration date/time.
        The current highest number of nodes in the pool of all the requests that are not expired will be deployed to the org. 
        Expired entries are immediately removed from the pool and the number of nodes are adjusted if needed.
    '''
    serializer_class = DummySerializer
    def update(self, request, org_name, desired_num_nodes, *args, **kwargs):
        try:
            jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
            if http_status == status.HTTP_200_OK:
                if active:
                    LOG.info(f"type(token_expire_date):{type(token_expire_date)}")
                    LOG.info(f"token_expire_date:{token_expire_date}")
                    jrsp, http_status = process_num_nodes_api(org_name, user, desired_num_nodes, token_expire_date, False)
            else:
                return Response(jrsp, status=http_status)
        except Exception as e:
            LOG.exception("caught exception:")
            jrsp = {'status': "FAILED", "error_msg": "Server Error"}
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(jrsp, status=http_status)

class DesiredNumNodesTTLView(generics.CreateAPIView):
    '''
        Takes an org_name, desired_num_nodes and ttl ("time to live" in minutes) and creates an OrgNumNode request for the org.
        NOTE: If the ttl is not provided, the time to live will be set the the minimum (15 minutes). The maximum ttl is 720 minutes (i.e. 12 hours).
        This request will go into the pool of requests for the org.
        The msg field of the JSON response will contain the this expiration date/time.
        The current highest number of nodes in the pool of all the requests that are not expired will be deployed to the org. 
        Expired entries are immediately removed from the pool and the number of nodes are adjusted if needed.
    '''
    serializer_class = DummySerializer
    def create(self, request, org_name, desired_num_nodes, ttl, *args, **kwargs):
        try:
            LOG.info(f"{org_name} {desired_num_nodes} {ttl}")
            jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
            if http_status == status.HTTP_200_OK:
                if active:
                    if ttl is not None and (int(ttl) < ONN_MIN_TTL or int(ttl) > ONN_MAX_TTL):
                        http_status = status.HTTP_400_BAD_REQUEST
                        max_ttl_hrs = ONN_MAX_TTL/60
                        jrsp = {'status': "FAILED","error_msg":f"TTL mins must be greater than or equal to 15 and less than or equal to {ONN_MAX_TTL} (i.e. ({max_ttl_hrs} hrs)"}
                    else:
                        orgAccountObj = OrgAccount.objects.get(name=org_name)
                        clusterObj = Cluster.objects.get(org=orgAccountObj)
                        if ttl is None:
                            ttl_exp_tm = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=ONN_MIN_TTL)
                        else:
                            ttl_exp_tm = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=int(ttl))
                        LOG.info(f"type(ttl_exp_tm):{type(ttl_exp_tm)} ttl_exp_tm:{ttl_exp_tm} ttl:{ttl}")
                        if clusterObj.is_deployed or orgAccountObj.allow_deploy_by_token:
                            jrsp,http_status = process_num_nodes_api(org_name,user,desired_num_nodes,ttl_exp_tm,False)
                        else:
                            jrsp = {'status': "FAILED","error_msg":f"cluster for {orgAccountObj.name} is not deployed and is not configured to be deployed with this request (See admin for details)"}
                            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
                else:
                    http_status = status.HTTP_401_UNAUTHORIZED
                    jrsp = {'status': "FAILED","error_msg":f"{user.username} is Not an Active Member of {org_name}"}           
        except Exception as e:
            LOG.exception("caught exception:")
            jrsp = {'status': "FAILED","error_msg":"Server Error"}
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(jrsp, status=http_status)

class OrgIpAdrView(generics.RetrieveAPIView):
    '''
        Takes an org_name and returns the IP address of the cluster manager for the org.
    '''
    serializer_class = DummySerializer
    def get(self, request, org_name, *args, **kwargs):
        try:
            jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
            if http_status == status.HTTP_200_OK:
                if active:
                    orgAccountObj = OrgAccount.objects.get(name=org_name)
                    clusterObj = Cluster.objects.get(org=orgAccountObj)
                    if clusterObj.is_deployed:
                        jrsp = {'status': "SUCCESS",'ip_address':clusterObj.mgr_ip_address}
                        http_status = status.HTTP_200_OK
                    else:
                        jrsp = {'status': "FAILED","error_msg":f"cluster for {orgAccountObj.name} is not deployed."}
                        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            else:
                return Response(jrsp, status=http_status)
        except Exception as e:
            LOG.exception("caught exception:")
            jrsp = {'status': "FAILED","error_msg":"Server Error"}
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(jrsp, status=http_status)
    
class RemoveUserNumNodesReqsView(generics.UpdateAPIView):
    '''
        Removes all OrgNumNode requests for the org from this user from the active pool of requests. 
    '''
    serializer_class = DummySerializer
    def update(self, request, org_name, *args, **kwargs):
        LOG.info(f"{request.user.username} {org_name}")
        status = 200
        try:
            orgAccountObj = OrgAccount.objects.get(name=org_name)
        except:
            jrsp = {'status': "FAILED","error_msg":f"Unknown org:{org_name}"}
            status=400
        jrsp,status,active,user,token_expire_date = get_token_org_active_membership(request,org_name)
        if status == 200:
            if active:
                jrsp = remove_num_node_requests(request.user,orgAccountObj,only_owned_by_user=True)
        return Response(jrsp,status = status)


class RemoveAllNumNodesReqsView(generics.UpdateAPIView):
    '''
        Removes all OrgNumNode requests for the org from the active pool of requests.  Must be a developer or owner of the org to remove ALL the requests.
    '''
    serializer_class = DummySerializer
    def update(self, request, org_name, *args, **kwargs):
        LOG.info(f"{request.user.username} {org_name}")
        status = 200
        try:
            orgAccountObj = OrgAccount.objects.get(name=org_name)
        except:
            jrsp = {'status': "FAILED","error_msg":f"Unknown org:{org_name}"}
            status=400
        jrsp,status,active,user,token_expire_date = get_token_org_active_membership(request,org_name)
        if status == 200:
            if active:
                jrsp,status,user_in_token = get_user_in_token(request)
                if user_in_token is not None:
                    if user_in_token.groups.filter(name='PS_Developer').exists() or orgAccountObj.owner==user_in_token:
                        jrsp = remove_num_node_requests(request.user,orgAccountObj,only_owned_by_user=False)
                    else:
                        status = 400
                        jrsp = {'status': "FAILED","error_msg":f"{user_in_token.username} is not an admin of {org_name}"}
                else:
                    status = 400
                    jrsp = {'status': "FAILED","error_msg":"Invalid Token (invalid user in token)"}
            else:
                status = 401
                jrsp = {'status': "FAILED","error_msg":f"{user.username} is Not an Active Member of {org_name}"}
        return Response(jrsp,status = status)

class ClusterConfigView(generics.UpdateAPIView):
    '''
    Takes an org_name min_nodes and max_nodes and updates the cluster's min and max nodes.
    These are the limits that regular users can request.
    NOTE: Must be a developer or owner of the org to update the config.
    '''
    serializer_class = DummySerializer

    def update(self, request, org_name, min_nodes, max_nodes, *args, **kwargs):

        LOG.info(f"{request.user.username} {org_name} min:{min_nodes} max:{max_nodes}")

        try:
            orgAccountObj = OrgAccount.objects.get(name=org_name)
        except:
            jrsp = {'status': "FAILED","error_msg":f"Unknown org:{org_name}"}
            return Response(jrsp, status=status.HTTP_400_BAD_REQUEST)

        jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
        if http_status == status.HTTP_200_OK:
            if active:
                if user is not None:
                    if user.groups.filter(name='PS_Developer').exists() or orgAccountObj.owner==user:
                        LOG.info(f'configuring min-max nodes for {orgAccountObj.name} {user.username} ')
                        error_msg = ''
                        if max_nodes > 0 and max_nodes <= orgAccountObj.admin_max_node_cap:
                            if min_nodes >= 0 and min_nodes <= max_nodes:
                                orgAccountObj.min_node_cap = min_nodes
                                orgAccountObj.max_node_cap = max_nodes
                                orgAccountObj.save(update_fields=['min_node_cap', 'max_node_cap'])
                                jrsp = {'status': "SUCCESS","msg":f"updated min-max nodes for {org_name} {user.username} to {orgAccountObj.min_node_cap}-{orgAccountObj.max_node_cap}"}
                                enqueue_process_state_change(orgAccountObj.name)
                            else:
                                http_status = status.HTTP_400_BAD_REQUEST
                                error_msg = f"INVALID min_nodes provided:{min_nodes} must be >= 0 and <= max_node given (i.e. {max_nodes}) and <= {orgAccountObj.admin_max_node_cap}"
                        else:
                            http_status = status.HTTP_400_BAD_REQUEST
                            error_msg = f"INVALID max_nodes provided:{max_nodes} must be > 0 and <= {orgAccountObj.admin_max_node_cap}"
                        if error_msg != '':
                            jrsp = {'status': "FAILED","error_msg":f"{error_msg}"}
                    else:
                        http_status = status.HTTP_400_BAD_REQUEST
                        jrsp = {'status': "FAILED","error_msg":f"{user.username} is not an admin of {org_name}"}
                else:
                    http_status = status.HTTP_400_BAD_REQUEST
                    jrsp = {'status': "FAILED","error_msg":f"Invalid user"}
            else:
                http_status = status.HTTP_400_BAD_REQUEST
                jrsp = {'status': "FAILED","error_msg":f"{user.username} is not an active member of {org_name}"}
        return Response(jrsp, status=http_status)
    

class NumNodesView(generics.RetrieveAPIView):
    '''
    Takes an org_name and returns the min-current-max number of nodes and the version and is_public from the cluster for the org.
    '''
    serializer_class = DummySerializer
    def get(self, request, org_name, *args, **kwargs):
        try:
            orgAccountObj = OrgAccount.objects.get(name=org_name)
        except:
            jrsp = {'status': "FAILED","error_msg":f"Unknown org:{org_name}"}
            return Response(jrsp, status=status.HTTP_400_BAD_REQUEST)        
        jrsp, http_status, active, user, token_expire_date = get_token_org_active_membership(request, org_name)
        if http_status == status.HTTP_200_OK:
            if active:
                try:
                    update_cur_num_nodes(orgAccountObj)
                    clusterObj = Cluster.objects.get(org=orgAccountObj)
                    if clusterObj.is_deployed:
                        jrsp = {'status': "SUCCESS",'min_nodes':orgAccountObj.min_node_cap,'current_nodes': clusterObj.cur_nodes, 'max_nodes':orgAccountObj.max_node_cap, 'version':clusterObj.cur_version, 'is_public':clusterObj.is_public}
                    else:
                        jrsp = {'status': "SUCCESS",'min_nodes':orgAccountObj.min_node_cap,'current_nodes': 0, 'max_nodes':orgAccountObj.max_node_cap, 'version':clusterObj.cur_version, 'is_public':clusterObj.is_public}
                    http_status = status.HTTP_200_OK
                except:
                    LOG.exception("caught exception:")
                    jrsp = {'status': "FAILED","error_msg":"server Error"}
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            else:
                jrsp = {'status': "FAILED","error_msg":"user is not an ACTIVE member?"}
                http_status=status.HTTP_400_BAD_REQUEST
        return Response(jrsp, status=http_status)

class DisableProvisioningSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    mfa_code = serializers.CharField()

@extend_schema(
    exclude=True
)
class DisableProvisioningView(generics.UpdateAPIView):
    '''
    USED BY PROVISIONING SYSTEM DEVELOPERS ONLY!
    Takes a username, password and mfa_code and disables provisioning for ALL clusters in the domain.
    This is used when provisioning a new Provisioining System cluster.
    This can only be done by a PS_Developer. 
    Once this endpoint is called, the PS_Developer will need to re-deploy the provisioning system cluster in order for the provisioning system to accept any new provisioning requests.
    '''
    serializer_class = DisableProvisioningSerializer

    def update(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        mfa_code = request.data.get('mfa_code')
        LOG.info(f"{username} is attempting to disable provisioning")
        if not all([username, password, mfa_code]):
            return Response({'status': "FAILED","error_msg":"Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)
        LOG.info(f"authenicating username:{username}")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.groups.filter(name='PS_Developer').exists():
                login(request, user)
                try:
                    LOG.info(f"mfa_code:{mfa_code} MFA_PLACEHOLDER:{os.environ.get('MFA_PLACEHOLDER')} DOMAIN:{os.environ.get('DOMAIN')} TZ={os.environ.get('TZ')}")
                    if mfa_code == os.environ.get('MFA_PLACEHOLDER'):
                        req_msg = f"User:{request.user.username} requested disable provisioning"
                        LOG.critical(f"{req_msg}")   
                        error_msg, disable_msg, rsp_msg = disable_provisioning(request.user,req_msg)    
                        if error_msg and error_msg != '':
                            LOG.error(request, error_msg)
                            return Response({'status': "FAILED","error_msg":'FAILED to disable provisioning'}, status=500)
                        else:
                            port_str = os.environ.get("PS_SERVER_PORT")
                            LOG.info(f"PS_SERVER_PORT:{port_str}")
                            if port_str is None:
                                LOG.error(f"PS_SERVER_PORT is not set in environment")
                                port_str = "50052"
                            if port_str == "50051":
                                port_str = "50052"
                            else:
                                port_str = "50051"
                            jrsp = {
                                'status': "SUCCESS",
                                "msg":"You have disabled provisioning! Re-Deploy required!",
                                "alternate_port":f"{port_str}",
                                }
                            http_status=status.HTTP_200_OK
                            LOG.info(f"{jrsp}")
                    else:
                        LOG.error(f"Invalid MFA code")
                        return Response({'status': "FAILED","error_msg":"Invalid MFA code"}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    LOG.exception("caught exception:")
                    return Response({'status': "FAILED","error_msg":f"Failed to disable provisioning: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)               
            else:
                LOG.error(f"{username} attempted to disable provisioning but is not a PS_Developer")
                jrsp = {'status': "FAILED","error_msg":"User is not a PS_Developer"}
                http_status=status.HTTP_401_UNAUTHORIZED
        else:
            jrsp = {'status': "FAILED","error_msg":"Invalid username/password"}
            http_status=status.HTTP_400_BAD_REQUEST
        LOG.info(f"{jrsp}")
        return Response(jrsp, status=http_status)

class OrgTokenObtainPairView(TokenObtainPairView):
    '''
    Takes a set of user credentials along with an organization and returns an access and refresh JSON web token if the user is an active member of that organization.
    The Access token will contain the organization name and the user name in the claims and expire in 1 hour.
    The Refresh token will expire in 1 day. A Refresh token can be used with the /org_token/refresh/ endpoint to obtain a new Access token.
    '''
    serializer_class = OrgTokenObtainPairSerializer



class OrgTokenObtainPairGitHubView(APIView):
    """
    Takes a GitHub access token and an organization name. Returns an access and refresh JSON web token
    if the user associated with the GitHub token is an active member of that organization.
    """
    serializer_class = OrgTokenObtainPairGitHubSerializer
    def post(self, request, *args, **kwargs):
        try:
            serializer = OrgTokenObtainPairGitHubSerializer(data=request.data)
            if serializer.is_valid():
                # Serializer is valid, return token data
                return Response(serializer.validated_data, status=status.HTTP_200_OK)
            else:
                # Serializer is not valid, return errors
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)    
        except PermissionDenied as e:
            LOG.exception("caught PermissionDenied exception:")
            return Response({'status': "FAILED","error_msg":f"Permission Denied: {str(e)}"}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e: 
            LOG.exception("caught exception:")
            return Response({'status': "FAILED","error_msg":f"Server Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   

class OrgTokenRefreshView(TokenRefreshView):
    '''
    Takes a refresh type JSON web token and returns a new access type JSON web token if the refresh token is valid.
    '''
    serializer_class = OrgTokenRefreshSerializer


