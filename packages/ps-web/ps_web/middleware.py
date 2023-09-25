from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseForbidden
from django.contrib.auth.models import Group
from oauth2_provider.views import ApplicationRegistration, ApplicationUpdate, ApplicationDelete, ApplicationList, AuthorizedTokensListView, AuthorizedTokenDeleteView
from pprint import pformat

import logging

LOG = logging.getLogger('django')


class HealthCheckMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.META['PATH_INFO'] == '/ping/':
            return HttpResponse('pong!')

class OAuthToolkitGroupProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        view_class = getattr(view_func, "view_class", None)
        if view_class in [ApplicationRegistration, ApplicationUpdate, ApplicationDelete, ApplicationList, AuthorizedTokensListView, AuthorizedTokenDeleteView ]:
            allowed_group_name = "PS_Developer"
            if not (request.user.is_authenticated and (request.user.is_superuser or request.user.groups.filter(name=allowed_group_name).exists())):
                LOG.critical(f"Forbade access to user:{request.user} for view_class:{view_class}")
                return HttpResponseForbidden()

class EarlyLoggingMiddleware:
    '''
    used in conjuction with the SETTINGS MIDDLEWARE section entry : 
    ps_web.middleware.EarlyLoggingMiddleware to log a request before 
    it is processed by the rest of the middleware
    '''
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for attribute in dir(request):
            value = getattr(request, attribute, None)
            LOG.info(f"{attribute}: {value}")
        
        response = self.get_response(request)
        return response


        response = self.get_response(request)
        return response

