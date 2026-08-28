"""
OpenBao client for runtime secret retrieval.

Provides secure token retrieval from OpenBao without exposing credentials
in environment variables or logs.
"""

import logging
import os
from typing import Optional

import hvac

logger = logging.getLogger(__name__)


class OpenBaoClient:
    """
    OpenBao client for retrieving secrets at runtime.

    This client retrieves secrets from OpenBao without exposing credential
    values in environment variables, command lines, or logs. Secrets are
    fetched by reference (path) and materialized only in memory.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        """
        Initialize OpenBao client.

        Args:
            url: OpenBao server URL (default: from OPENBAO_URL env var or
                 http://traefik-ardenone-cluster:8200)
            token: OpenBao token (default: from OPENBAO_TOKEN env var)
                   Note: On k8s pods, this is typically mounted at
                   /path/to/mounted/token and should be passed via env var
        """
        self.url = url or os.getenv(
            "OPENBAO_URL", "http://traefik-ardenone-cluster:8200"
        )
        self.token = token or os.getenv("OPENBAO_TOKEN")

        if not self.token:
            logger.warning(
                "OpenBao client initialized without token - "
                "reads will fail. Set OPENBAO_TOKEN environment variable."
            )

        self._client: Optional[hvac.Client] = None

    def _get_client(self) -> hvac.Client:
        """Get or create the hvac Client instance."""
        if self._client is None:
            if not self.token:
                raise ValueError("Cannot create OpenBao client without token")

            # Use verify=False for self-signed Traefik certs (same as httpx clients)
            self._client = hvac.Client(
                url=self.url,
                token=self.token,
                verify=False,
            )
        return self._client

    def get_secret(self, path: str, field: str = "value") -> Optional[str]:
        """
        Retrieve a secret value from OpenBao by path.

        The value is never logged or exposed. Only the success/failure
        of the retrieval is logged.

        Args:
            path: OpenBao secret path (e.g., secret/ardenone-cluster/aide-de-camp/telegram_bot_token)
            field: Field name within the secret (default: "value")

        Returns:
            The secret value as a string, or None if retrieval fails.
        """
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(path=path)

            if response is None:
                logger.error(f"OpenBao returned None for path: {path}")
                return None

            data = response.get("data", {})
            if isinstance(data, dict):
                data = data.get("data", {})

            value = data.get(field)
            if value is None:
                logger.error(
                    f"Field '{field}' not found in secret at path: {path}"
                )
                return None

            # Value is retrieved but NEVER logged
            logger.debug(f"Successfully retrieved secret from path: {path}")
            return value

        except hvac.exceptions.InvalidPath:
            logger.error(f"Invalid OpenBao path: {path}")
            return None
        except hvac.exceptions.Forbidden:
            logger.error(f"Access forbidden to OpenBao path: {path}")
            return None
        except Exception as e:
            logger.error(
                f"Failed to retrieve secret from {path}: {type(e).__name__}"
            )
            return None

    def check_secret_exists(self, path: str) -> bool:
        """
        Check if a secret exists at the given path without reading its value.

        Args:
            path: OpenBao secret path

        Returns:
            True if the secret exists, False otherwise.
        """
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=path, raise_on_deleted_version=True
            )
            return response is not None
        except hvac.exceptions.InvalidPath:
            return False
        except hvac.exceptions.Forbidden:
            return False
        except Exception:
            return False


# Global OpenBao client instance
_openbao_client: Optional[OpenBaoClient] = None


def get_openbao_client() -> OpenBaoClient:
    """Get or create the global OpenBao client instance."""
    global _openbao_client
    if _openbao_client is None:
        _openbao_client = OpenBaoClient()
    return _openbao_client
