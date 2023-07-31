from rest_framework_simplejwt.tokens import RefreshToken, AccessToken, BlacklistMixin
from rest_framework_simplejwt.settings import api_settings

import logging

LOG = logging.getLogger('django')

# add blacklist functionality, needs settings.py  SIMPLE_JWT.AUTH_TOKEN_CLASSES set correctly
class JWTAccessToken( AccessToken,BlacklistMixin):
    pass


class OrgRefreshToken(RefreshToken,BlacklistMixin):

    def __init__(self, user_name, org_name, token=None, verify=True):
        super().__init__(token=token,verify=verify)
        # Set up new token
        if token is None:
            #LOG.info("initializing token %s %s",user_name,org_name)
            self.org_name = org_name
            self.set_org_name(org_name)
            self.set_user_name(user_name)
        else:
            LOG.info("OrgRefreshToken")

    def set_org_name(self,org_name):
        """
        Populates the org_name claim of a token 

        """
        self.payload['org_name'] = org_name

    def set_user_name(self,user_name):
        """
        Populates the user_name claim of a token 

        """
        self.payload['user_name'] = user_name

    @classmethod
    def for_user(cls, user, org_name):
        """
        Returns an authorization token for the given user with an org_name claim that will be provided
        after authenticating the user's credentials.
        """
        LOG.info("%s %s",user,org_name)
        user_id = getattr(user, api_settings.USER_ID_FIELD)
        if not isinstance(user_id, int):
            user_id = str(user_id)
        token = cls(user.username,org_name)
        token[api_settings.USER_ID_CLAIM] = user_id
        token['org_name'] = org_name

        return token
