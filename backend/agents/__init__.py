# agents/__init__.py
"""
AutoPR Agents Module

This module contains all the AI agents responsible for different aspects of code review:
- CodeQualityAgent: Analyzes code style, readability, and best practices
- BugDetectionAgent: Detects potential bugs and logical errors
- SecurityAgent: Identifies security vulnerabilities
- DependencyAgent: Analyzes dependencies and breaking changes
- DocumentationAgent: Reviews documentation quality
- CoordinatorAgent: Coordinates and synthesizes results from all agents
"""

from .code_quality import CodeQualityAgent
from .bug_detection import BugDetectionAgent
from .security import SecurityAgent
from .dependency import DependencyAgent
from .documentation import DocumentationAgent
from .coordinator import CoordinatorAgent

__all__ = [
    'CodeQualityAgent',
    'BugDetectionAgent', 
    'SecurityAgent',
    'DependencyAgent',
    'DocumentationAgent',
    'CoordinatorAgent'
]


