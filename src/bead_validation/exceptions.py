"""
Custom exceptions for bead validation.
"""


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


class ValidationRetryExhaustedError(ValidationError):
    """Raised when re-formulation retry is exhausted."""

    def __init__(self, original_violations: list, message: str = "Validation failed after re-formulation"):
        self.original_violations = original_violations
        super().__init__(message)
