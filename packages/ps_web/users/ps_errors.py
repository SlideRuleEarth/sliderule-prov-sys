import logging

class ProvSys_Exception(Exception):
    """Base class for other Provisioning System Exceptions"""
    pass

class LowBalanceError(ProvSys_Exception):
    """Raised when the account balance is insufficient"""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ShortExpireTimeError(ProvSys_Exception):
    """Raised when the Expire time is insufficient"""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class UnknownUserError(ProvSys_Exception):
    """Raised when the username is invalid"""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ClusterDeployAuthError(ProvSys_Exception):
    """Raised when the Cluster cannot be Deployed due to authorization failure"""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ProvisionCmdError(ProvSys_Exception):
    """Raised when an exception is caught processing a provision cmd"""

    def __init__(self, message, log_level=logging.ERROR):
        self.message = message
        self.log_level = log_level
        super().__init__(self.message)
