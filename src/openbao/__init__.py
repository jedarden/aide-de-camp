"""OpenBao client for runtime secret retrieval."""

from .client import OpenBaoClient, get_openbao_client

__all__ = ["OpenBaoClient", "get_openbao_client"]
