"""
Stub classes for Dify Plugin SDK.

These stubs allow the provider module to be developed and tested without
the actual Dify Plugin SDK installed. At runtime in the Dify environment,
the real SDK classes will be used instead.
"""


class ToolProvider:
    """
    Stub for dify_plugin.ToolProvider base class.

    In the actual Dify SDK, this class provides:
    - Credential management
    - Tool registration and lifecycle
    - Provider configuration validation
    """

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials.

        Subclasses must override this method to implement credential validation.
        Should raise ToolProviderCredentialValidationError on failure.

        Args:
            credentials: Dictionary of provider credential values
        """
        raise NotImplementedError("Subclasses must implement _validate_credentials")


class ToolProviderCredentialValidationError(Exception):
    """
    Stub for dify_plugin.errors.tool.ToolProviderCredentialValidationError.

    Raised when provider credential validation fails. The message is
    displayed to the user in the Dify UI.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
