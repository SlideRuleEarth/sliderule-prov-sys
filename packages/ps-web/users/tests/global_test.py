from django.test import TestCase

import logging
LOG = logging.getLogger('django')

class GlobalTestCase(TestCase):

    tst_org = None
    tst_user = None
    def setUp(self) -> None:
        #LOG.info(f"{__name__}({self}) vvv %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        return super().setUp()

    def tearDown(self) -> None:
        #LOG.info(f"{__name__}({self}) ^^^ %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        return super().tearDown()   
