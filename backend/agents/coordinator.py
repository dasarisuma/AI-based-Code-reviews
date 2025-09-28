import json
import logging
from typing import Dict, List
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class CoordinatorAgent:
    """
    Coordinator agent that synthesizes results from all other agents
    """

    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "Coordinator"

    async def coordinate(self, agent_results: Dict[str, List[Dict]], pr_data: Dict) -> Dict:
        """
        Coordinate and synthesize results from all agents into final review
        """
        try:
            logger.info("Coordinating final review from agent results")

            # Categorize issues by severity
            critical_comments, high_comments, medium_comments, low_comments = [], [], [], []

            for agent, comments in agent_results.items():
                for comment in comments:
                    severity = comment.get("severity", "info").lower()
                    formatted = f"[{agent}] Line {comment.get('line', '?')}: {comment.get('message', '')}"

                    if severity in ["critical", "error"]:
                        critical_comments.append(formatted)
                    elif severity in ["high", "warning"]:
                        high_comments.append(formatted)
                    elif severity == "medium":
                        medium_comments.append(formatted)
                    else:
                        low_comments.append(formatted)

            # Build summary stats
            # Compute total changes from unified schema
            total_changes = 0
            for f in pr_data.get("files", []):
                total_changes += len(f.get("changes", []))

            summary_data = {
                "critical": len(critical_comments),
                "high": len(high_comments),
                "medium": len(medium_comments),
                "low": len(low_comments),
                "files": len(pr_data.get("files", [])),
                "total_changes": total_changes,
            }

            # Generate final review with LLM
            final_review = await self._generate_final_summary(summary_data, agent_results)

            return {
                "summary": final_review.get(
                    "summary", self._generate_default_summary(summary_data)
                ),
                "status": final_review.get(
                    "status", self._determine_status(summary_data)
                ),
                "issue_breakdown": {
                    "critical": critical_comments,
                    "high": high_comments,
                    "medium": medium_comments,
                    "low": low_comments,
                },
                "total_comments": sum(len(c) for c in agent_results.values()),
                "files_analyzed": len(pr_data.get("files", [])),
                "confidence_score": self._calculate_confidence_score(agent_results),
            }

        except Exception as e:
            logger.error(f"Error in coordination: {str(e)}")
            return {
                "summary": "⚠️ Review completed with coordination issues",
                "status": "Needs Changes",
                "error": str(e),
            }

    async def _generate_final_summary(self, summary_data: Dict, agent_results: Dict) -> Dict:
        """
        Generate final summary using LLM
        """
        try:
            prompt = f"""
            Based on the code review results, provide a final summary and recommendation.

            Review Statistics:
            - Critical issues: {summary_data['critical']}
            - High severity: {summary_data['high']}
            - Medium severity: {summary_data['medium']}
            - Low severity: {summary_data['low']}
            - Files changed: {summary_data['files']}
            - Total code changes: {summary_data['total_changes']} lines

            Agent Results Summary:
            {self._format_agent_summary(agent_results)}

            very Strictly Provide response as JSON:
            {{
                "summary": "Brief, actionable summary with emoji (e.g., '🚫 3 critical security issues block merge')",
                "status": "Approve|Needs Changes|Reject"
            }}
            """

            response = await self.groq_service.generate_completion(
                prompt, "coordination", max_tokens=256
            )
            return json.loads(response.strip().replace("```json", "").replace("```", ""))

        except Exception as e:
            logger.warning(f"Failed to generate LLM summary: {str(e)}")
            return {
                "summary": self._generate_default_summary(summary_data),
                "status": self._determine_status(summary_data),
            }

    def _format_agent_summary(self, agent_results: Dict) -> str:
        """
        Format agent results for LLM prompt
        """
        summary = ""
        for agent, comments in agent_results.items():
            if comments:
                summary += f"{agent}: {len(comments)} comments\n"
                for comment in comments[:2]:  # include first 2 comments only
                    summary += f"  - Line {comment.get('line')}: {comment.get('message')[:60]}...\n"
        return summary

    def _generate_default_summary(self, summary_data: Dict) -> str:
        """
        Generate default summary without LLM
        """
        if summary_data["critical"] > 0:
            return f"🚫 {summary_data['critical']} critical issue(s) found - blocking merge"
        elif summary_data["high"] > 0:
            return f"⚠️ {summary_data['high']} high severity issue(s) found - changes recommended"
        elif summary_data["medium"] > 0:
            return f"⚡ {summary_data['medium']} medium issue(s) found - consider addressing"
        elif summary_data["low"] > 0:
            return f"💡 {summary_data['low']} minor suggestion(s) - optional improvements"
        else:
            return "✅ No issues found - ready to merge"

    def _determine_status(self, summary_data: Dict) -> str:
        """
        Determine status based on issue severity
        """
        if summary_data["critical"] > 0:
            return "Reject"
        elif summary_data["high"] > 0 or summary_data["medium"] > 2:
            return "Needs Changes"
        else:
            return "Approve"

    def _calculate_confidence_score(self, agent_results: Dict[str, List[Dict]]) -> float:
        """
        Calculate confidence score based on agent responses
        """
        try:
            total_agents = len(agent_results)
            successful_agents = 0

            for _, results in agent_results.items():
                if results:
                    has_errors = any(c.get("type") == "analysis-error" for c in results)
                    if not has_errors:
                        successful_agents += 1
                else:
                    successful_agents += 1  # no issues also counts as success

            return round((successful_agents / total_agents) * 100, 1) if total_agents else 0.0
        except Exception:
            return 50.0  # fallback