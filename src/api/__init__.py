"""
API models and request/response validation for aide-de-camp.

This package contains Pydantic models for API validation:
- DispatchRequest/DispatchResponse: POST /dispatch endpoint models
"""

from .models import DispatchRequest, DispatchResponse

__all__ = [
    "DispatchRequest",
    "DispatchResponse",
]
