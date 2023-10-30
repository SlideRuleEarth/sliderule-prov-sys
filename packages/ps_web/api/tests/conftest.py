import pytest
import os
import logging
from importlib import import_module
import pytest
from django.contrib.sites.models import Site
from users.tasks import process_state_change
from users.models import Membership,OrgAccount,OrgNumNode,Cluster,OwnerPSCmd,PsCmdResult
from unittest.mock import patch, MagicMock, Mock
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model
from users.tests.utilities_for_unit_tests import create_active_membership,get_test_org

@pytest.fixture(scope='session', autouse=True)
def setup_logging():
    # Create a custom logger
    logger = logging.getLogger('unit-testing')
    # Set level of logging
    #logger.setLevel(logging.ERROR)
    logger.setLevel(logging.INFO)
    #logger.setLevel(logging.DEBUG)

    # Create handlers
    console_handler = logging.StreamHandler()
    #console_handler.setLevel(logging.ERROR)
    console_handler.setLevel(logging.INFO)
    #console_handler.setLevel(logging.DEBUG)

    # Create formatter and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)

    yield logger  # provide the fixture value

    # After the test session, remove the handler to avoid logging duplicate messages
    logger.removeHandler(console_handler)

@pytest.fixture
def netrc_setup():
    # Path to the .netrc file
    netrc_file = os.path.expanduser("~/.netrc")

    # Ensure no existing .netrc file
    if os.path.exists(netrc_file):
        os.rename(netrc_file, netrc_file + '.backup')

    # Write content to .netrc
    with open(netrc_file, 'w') as f:
        f.write("machine localhost login ceugarteblair password nomore1bs")

    # Change permissions on .netrc to be read/write for the owner only
    os.chmod(netrc_file, 0o600)

    yield netrc_file

    # Cleanup: Remove the .netrc file after the test is finished
    os.remove(netrc_file)

    # Restore the original .netrc if it existed
    if os.path.exists(netrc_file + '.backup'):
        os.rename(netrc_file + '.backup', netrc_file)

@pytest.fixture
def setup_site():
    # Fetch or create the Site object with domain 'localhost'
    site, created = Site.objects.get_or_create(domain='localhost')
    if created:
        site.name = 'Localhost Test Site'
        site.save()

    # Override the SITE_ID setting to use the created site's ID for the duration of the test
    from django.conf import settings
    original_site_id = settings.SITE_ID
    settings.SITE_ID = site.id

    yield site

    # Cleanup (optional): Reset the SITE_ID setting
    settings.SITE_ID = original_site_id


@pytest.fixture
def social_user(db,initialize_test_environ):
    s_user = get_user_model().objects.create_user(username='testsocialuser', password='12345')
    return s_user

@pytest.fixture
def social_user_membership(social_user):
    return create_active_membership(the_org=get_test_org(),the_user=social_user)

@pytest.fixture
def github_social_app(db):
    app = SocialApp.objects.create(
        provider='github',
        name='GitHub',
        client_id=os.getenv('GITHUB_CLIENT_ID_LOCALHOST'),
        secret=os.getenv('GITHUB_CLIENT_SECRET_LOCALHOST'),
    )
    site = Site.objects.get_current()
    app.sites.add(site)
    return app

@pytest.fixture
def github_social_account(social_user, db):
    social_account = SocialAccount.objects.create(
        user=social_user,
        provider='github',
        uid=os.getenv('GITHUB_DEVTESTER_SLIDERULE_USER_ID'),  
        extra_data= {
                        'access_token': os.getenv('GITHUB_DEVTESTER_SLIDERULE_ACCESS_TOKEN'),
                        'login': os.getenv('GITHUB_DEVTESTER_SLIDERULE_USER_NAME'),
                    }  
    )
    return social_account

