"""
API Request/Response Models for aide-de-camp.

This module defines Pydantic models for validating API requests and responses.
All models include field validators with clear error messages and examples
for OpenAPI documentation.

Models:
    DispatchRequest: Request model for POST /dispatch endpoint
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DispatchRequest(BaseModel):
    """
    Request model for POST /dispatch endpoint.

    This model validates incoming dispatch requests, ensuring that required
    fields are present and valid. Field validators provide clear error messages
    for invalid input.

    Attributes:
        utterance: The text utterance to dispatch (required, non-empty)
        session_id: Session ID for tracking and SSE targeting (required)
        surface_id: Surface ID for SSE broadcast targeting (required)
        utterance_id: Optional utterance ID (auto-generated if not provided)

    Example:
        >>> request = DispatchRequest(
        ...     utterance="Check CI status for aide-de-camp",
        ...     session_id="550e8400-e29b-41d4-a716-446655440000",
        ...     surface_id="surface-abc123"
        ... )
    """

    utterance: str = Field(
        ...,
        min_length=2,
        description="The utterance text to dispatch",
        example="Check CI status for aide-de-camp",
    )
    session_id: str = Field(
        ...,
        description="Session ID for tracking and SSE targeting",
        example="550e8400-e29b-41d4-a716-446655440000",
    )
    surface_id: str = Field(
        ...,
        description="Surface ID for SSE broadcast targeting",
        example="surface-abc123",
    )
    utterance_id: Optional[str] = Field(
        None,
        description="Optional utterance ID (auto-generated if not provided)",
        example="660e8400-e29b-41d4-a716-446655440000",
    )

    @field_validator('utterance')
    @classmethod
    def utterance_must_be_non_empty(cls, v: str) -> str:
        """
        Validate that utterance is a non-empty string.

        Args:
            v: The utterance value to validate

        Returns:
            str: The stripped utterance

        Raises:
            ValueError: If utterance is not a string or is empty after stripping
        """
        if not isinstance(v, str):
            raise ValueError('utterance must be a string')
        stripped = v.strip()
        if not stripped:
            raise ValueError('utterance must be a non-empty string')
        return stripped

    @field_validator('session_id')
    @classmethod
    def session_id_must_be_non_empty(cls, v: str) -> str:
        """
        Validate that session_id is a non-empty string.

        Args:
            v: The session_id value to validate

        Returns:
            str: The validated session_id

        Raises:
            ValueError: If session_id is not a string or is empty after stripping
        """
        if not isinstance(v, str):
            raise ValueError('session_id must be a string')
        stripped = v.strip()
        if not stripped:
            raise ValueError('session_id must be a non-empty string')
        return stripped

    @field_validator('surface_id')
    @classmethod
    def surface_id_must_be_non_empty(cls, v: str) -> str:
        """
        Validate that surface_id is a non-empty string.

        Args:
            v: The surface_id value to validate

        Returns:
            str: The validated surface_id

        Raises:
            ValueError: If surface_id is not a string or is empty after stripping
        """
        if not isinstance(v, str):
            raise ValueError('surface_id must be a string')
        stripped = v.strip()
        if not stripped:
            raise ValueError('surface_id must be a non-empty string')
        return stripped

    @field_validator('utterance_id', mode='before')
    @classmethod
    def validate_optional_utterance_id(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate optional utterance_id field.

        Args:
            v: The utterance_id value to validate (may be None)

        Returns:
            Optional[str]: The validated utterance_id or None

        Raises:
            ValueError: If utterance_id is provided but not a valid string
        """
        if v is not None:
            if not isinstance(v, str):
                raise ValueError('utterance_id must be a string')
            if v.strip() == "":
                raise ValueError('utterance_id must be a non-empty string if provided')
        return v

    class Config:
        """Pydantic model configuration for OpenAPI documentation."""
        json_schema_extra = {
            "examples": [
                {
                    "utterance": "Check CI status for aide-de-camp",
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "surface_id": "surface-abc123",
                    "utterance_id": "660e8400-e29b-41d4-a716-446655440000",
                }
            ]
        }
