from oauth2_provider.oauth2_validators import OAuth2Validator
from users.utils import get_memberships

class CustomOAuth2Validator(OAuth2Validator):
    # Extend the standard scopes to add a new "memberships" scope
    # which returns a "memberships" claim:
    oidc_claim_scope = OAuth2Validator.oidc_claim_scope
    oidc_claim_scope.update({"memberships": "memberships"})

    def get_additional_claims(self):
        return {
            "memberships": lambda request: list(get_memberships(request))
        }
