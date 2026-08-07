"""
API models and request/response validation for aide-de-camp.

This package contains Pydantic models for API validation:
- DispatchRequest: POST /dispatch endpoint request model
"""

from .models import DispatchRequest

__all__ = [
    "DispatchRequest",
]
