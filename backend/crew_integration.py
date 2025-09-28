import os
import asyncio
from typing import Dict, List, Any
import logging

try:
    from crewai import Agent, Task, Crew
except ImportError:  # Graceful fallback if crewai not installed yet
    Agent = Task = Crew = None  # type: ignore

logger = logging.getLogger(__name__)

class CrewReviewRunner:
    """Bridge existing agent logic into CrewAI orchestration without changing core analysis logic."""
    def __init__(self, 
                 code_quality_agent, 
                 bug_detection_agent, 
                 security_agent, 
                 dependency_agent, 
                 documentation_agent, 
                 coordinator_agent):
        self.code_quality_agent = code_quality_agent
        self.bug_detection_agent = bug_detection_agent
        self.security_agent = security_agent
        self.dependency_agent = dependency_agent
        self.documentation_agent = documentation_agent
        self.coordinator_agent = coordinator_agent
        if Agent is None:
            logger.warning("CrewAI not installed. Falling back to legacy execution.")

    async def run(self, pr_data: Dict) -> Dict[str, List[Dict]]:
        """Execute all analyses via Crew if available, else fallback to direct async gather.
        Returns dict keyed by agent name with list of issue dicts.
        """
        if Agent is None:
            return await self._legacy_run(pr_data)

        # Wrap existing async analyze methods into sync-friendly callables for Crew
        async def aq():
            return await self.code_quality_agent.analyze(pr_data)
        async def ab():
            return await self.bug_detection_agent.analyze(pr_data)
        async def as_():
            return await self.security_agent.analyze(pr_data)
        async def ad():
            return await self.dependency_agent.analyze(pr_data)
        async def ado():
            return await self.documentation_agent.analyze(pr_data)

        # Define Agent objects (lightweight) — goal/backstory minimal to not inflate prompts
        cq_agent = Agent(
            role="Code Quality Reviewer",
            goal="Identify style and maintainability issues in changed code lines.",
            backstory="Senior engineer focused on PEP8, readability and consistency.",
            verbose=False,
            allow_delegation=False
        )
        bug_agent = Agent(
            role="Bug Risk Analyst",
            goal="Detect logical and runtime error risks in modified code.",
            backstory="Experienced in static reasoning about defect patterns.",
            verbose=False,
            allow_delegation=False
        )
        sec_agent = Agent(
            role="Security Auditor",
            goal="Spot security vulnerabilities in changed code.",
            backstory="Security-focused reviewer checking for secrets, injection, unsafe patterns.",
            verbose=False,
            allow_delegation=False
        )
        dep_agent = Agent(
            role="Dependency Reviewer",
            goal="Identify breaking or risky dependency/interface changes.",
            backstory="Understands API surface and dependency graphs.",
            verbose=False,
            allow_delegation=False
        )
        doc_agent = Agent(
            role="Documentation Reviewer",
            goal="Suggest documentation or comment improvements for new code.",
            backstory="Focused on clarity and onboarding ease.",
            verbose=False,
            allow_delegation=False
        )

        # Each task just triggers the underlying async analyzer
        tasks = [
            Task(description="Analyze code quality of changed lines.", agent=cq_agent, async_execution=True, expected_output="List of code quality issue dicts"),
            Task(description="Detect potential bugs in changed lines.", agent=bug_agent, async_execution=True, expected_output="List of bug issue dicts"),
            Task(description="Analyze security concerns in changed lines.", agent=sec_agent, async_execution=True, expected_output="List of security issue dicts"),
            Task(description="Check dependency/interface implications.", agent=dep_agent, async_execution=True, expected_output="List of dependency issue dicts"),
            Task(description="Review documentation needs in changed code.", agent=doc_agent, async_execution=True, expected_output="List of documentation issue dicts"),
        ]

        # Because CrewAI currently expects internal LLM usage for tasks, we bypass by running
        # our analyzers directly and mapping to the same structure.
        # This keeps logic identical and avoids unnecessary token usage.
        results = await asyncio.gather(aq(), ab(), as_(), ad(), ado(), return_exceptions=True)
        names = ["CodeQuality", "BugDetection", "Security", "Dependency", "Documentation"]
        compiled: Dict[str, List[Dict]] = {}
        for n, res in zip(names, results):
            if isinstance(res, Exception):
                compiled[n] = [{"line": 0, "message": f"Agent failed: {res}", "severity": "error", "type": "analysis-error"}]
            else:
                compiled[n] = res or []
        return compiled

    async def _legacy_run(self, pr_data: Dict) -> Dict[str, List[Dict]]:
        results = await asyncio.gather(
            self.code_quality_agent.analyze(pr_data),
            self.bug_detection_agent.analyze(pr_data),
            self.security_agent.analyze(pr_data),
            self.dependency_agent.analyze(pr_data),
            self.documentation_agent.analyze(pr_data),
            return_exceptions=True
        )
        names = ["CodeQuality", "BugDetection", "Security", "Dependency", "Documentation"]
        compiled: Dict[str, List[Dict]] = {}
        for n, res in zip(names, results):
            if isinstance(res, Exception):
                compiled[n] = [{"line": 0, "message": f"Agent failed: {res}", "severity": "error", "type": "analysis-error"}]
            else:
                compiled[n] = res or []
        return compiled


def build_crew_runner(code_quality_agent, bug_detection_agent, security_agent, dependency_agent, documentation_agent, coordinator_agent) -> CrewReviewRunner:
    return CrewReviewRunner(code_quality_agent, bug_detection_agent, security_agent, dependency_agent, documentation_agent, coordinator_agent)
