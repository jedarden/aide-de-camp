"""
LLM utilities for aide-de-camp.

Provides centralized utilities for LLM interaction including:
- Response parsing (ZAI proxy unwrapping, markdown fence stripping)
- Common error handling
"""

from .response_parser import parse_llm_response, ParseLLMError

__all__ = ["parse_llm_response", "ParseLLMError"]
