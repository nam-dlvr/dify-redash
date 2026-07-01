"""
Stub classes for Dify Plugin SDK - Tool layer.

These stubs allow the tool modules to be developed and tested without
the actual Dify Plugin SDK installed. At runtime in the Dify environment,
the real SDK classes will be used instead.
"""

import json
from typing import Any, Generator


class ToolInvokeMessage:
    """
    Stub for dify_plugin.entities.tool.ToolInvokeMessage.

    Represents a message yielded from a tool invocation.
    """

    class TextMessage:
        """A text message returned by a tool."""

        def __init__(self, text: str) -> None:
            self.text = text

        def __repr__(self) -> str:
            return f"TextMessage(text={self.text!r})"


class RuntimeCredentials:
    """Stub for runtime credentials access."""

    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}


class ToolRuntime:
    """Stub for dify_plugin tool runtime."""

    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}


class Tool:
    """
    Stub for dify_plugin.Tool base class.

    In the actual Dify SDK, this class provides:
    - Tool invocation lifecycle
    - Credential access via self.runtime.credentials
    - Message creation utilities (create_text_message, etc.)
    """

    def __init__(self) -> None:
        self.runtime = ToolRuntime()

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the tool with the given parameters.

        Subclasses must override this method to implement tool logic.

        Args:
            tool_parameters: Dictionary of tool parameter values from the user/agent.

        Yields:
            ToolInvokeMessage.TextMessage instances containing the tool output.
        """
        raise NotImplementedError("Subclasses must implement _invoke")

    def create_text_message(self, text: str) -> ToolInvokeMessage.TextMessage:
        """
        Create a text message to return from the tool.

        Args:
            text: The text content of the message.

        Returns:
            A ToolInvokeMessage.TextMessage instance.
        """
        return ToolInvokeMessage.TextMessage(text=text)
