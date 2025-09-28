# services/__init__.py
"""
AutoPR Services Module

This module contains service classes for external integrations:
- GroqService: Interface with Groq Cloud LLM API
- GitHubService: Interface with GitHub REST API
"""

from .groq_service import GroqService
from .github_service import GitHubService

__all__ = [
    'GroqService',
    'GitHubService'
]