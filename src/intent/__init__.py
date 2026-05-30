"""
Intent module - handles utterance classification and routing.

Provides the IntentRouter which:
- Classifies utterances into intent types
- Routes to appropriate strands (escalate, fetch, synthesize)
- Returns structured intent objects for processing
"""

from .router import (
    IntentRouter,
    IntentType,
    IntentClassification,
    RoutedIntent,
    get_router,
)

__all__ = [
    "IntentRouter",
    "IntentType",
    "IntentClassification",
    "RoutedIntent",
    "get_router",
]
