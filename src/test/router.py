"""
Test Router - FastAPI router for test endpoints.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.
"""
from logging import getLogger

from fastapi import APIRouter


logger = getLogger(__name__)

# FastAPI router instance for test endpoints
router = APIRouter()

# Router is ready for endpoint registration
# Endpoints will be registered in dispatch.py and imported here
