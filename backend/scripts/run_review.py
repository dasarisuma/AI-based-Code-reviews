#!/usr/bin/env python3
"""
Standalone CLI script for running AI code review analysis.
Can be used in CI/CD pipelines without needing a running FastAPI server.
"""

import argparse
import json
import asyncio
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.github_service import GitHubService
from services.groq_service import GroqService
from agents.code_quality import CodeQualityAgent
from agents.bug_detection import BugDetectionAgent
from agents.security import SecurityAgent
from agents.dependency import DependencyAgent
from agents.documentation import DocumentationAgent
from agents.coordinator import CoordinatorAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def summarize_comments_per_line(raw_comments, groq_service, use_llm=True):
    """Simplified line summarization with LLM fallback"""
    if not raw_comments:
        return []

    # Group by (file, line)
    grouped = {}
    for c in raw_comments:
        key = (c.get("file", "*"), c.get("line", 0))
        grouped.setdefault(key, []).append(c)

    results = []
    
    if use_llm and groq_service:
        # Try LLM summarization with fallback
        for (file, line), issues in grouped.items():
            try:
                summary = await groq_service.summarize_line_issues(file, line, issues)
                severity = max(issues, key=lambda x: get_severity_weight(x.get("severity", "info"))).get("severity", "info")
                results.append({
                    "file": file,
                    "line": line,
                    "message": summary.get("summary", issues[0].get("message", "")),
                    "severity": severity,
                    "type": issues[0].get("type", "general"),
                    "suggestion": summary.get("suggestion", issues[0].get("suggestion", "")),
                    "source_agent": issues[0].get("source_agent", "unknown")
                })
            except Exception as e:
                logger.warning(f"LLM summarization failed for {file}:{line}, using fallback: {e}")
                # Fallback to first issue
                issue = issues[0]
                results.append({
                    "file": file,
                    "line": line,
                    "message": issue.get("message", ""),
                    "severity": issue.get("severity", "info"),
                    "type": issue.get("type", "general"),
                    "suggestion": issue.get("suggestion", ""),
                    "source_agent": issue.get("source_agent", "unknown")
                })
    else:
        # Heuristic-only mode
        for (file, line), issues in grouped.items():
            primary = max(issues, key=lambda x: get_severity_weight(x.get("severity", "info")))
            results.append({
                "file": file,
                "line": line,
                "message": primary.get("message", ""),
                "severity": primary.get("severity", "info"),
                "type": primary.get("type", "general"),
                "suggestion": primary.get("suggestion", ""),
                "source_agent": primary.get("source_agent", "unknown")
            })

    # Sort by file, then line
    results.sort(key=lambda x: (x["file"], x["line"]))
    return results

def get_severity_weight(severity):
    """Convert severity to numeric weight for comparison"""
    weights = {
        "critical": 0,
        "high": 1,
        "error": 1,
        "warning": 2,
        "medium": 3,
        "low": 4,
        "info": 5
    }
    return weights.get(severity.lower(), 10)

def determine_final_status(comments):
    """Determine final status based on severity distribution"""
    if not comments:
        return "Approve"
    
    severities = [c.get("severity", "info").lower() for c in comments]
    
    if any(s in ["critical", "error"] for s in severities):
        return "Reject"
    elif any(s in ["high", "warning"] for s in severities) or severities.count("medium") > 2:
        return "Needs Changes"
    else:
        return "Approve"

async def main():
    parser = argparse.ArgumentParser(description="AI Code Review Analysis")
    parser.add_argument("--pr-url", required=True, help="GitHub PR URL")
    parser.add_argument("--github-token", required=True, help="GitHub personal access token")
    parser.add_argument("--output", default="review.json", help="Output JSON file")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis (heuristics only)")
    parser.add_argument("--max-lines", type=int, default=1000, help="Skip analysis if PR changes exceed this limit")
    parser.add_argument("--agents", help="Comma-separated list of agents to run (code_quality,bug_detection,security,dependency,documentation)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize services
    github_service = GitHubService()
    
    groq_service = None
    use_llm = not args.no_llm
    if use_llm:
        try:
            groq_service = GroqService()
            logger.info("Groq service initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Groq service: {e}. Running in heuristics-only mode.")
            use_llm = False
    
    try:
        # Fetch PR data
        logger.info(f"Fetching PR data from: {args.pr_url}")
        pr_data = await github_service.fetch_pr_data(args.pr_url, args.github_token)
        
        # Check PR size limit
        total_changes = sum(len(f.get("changes", [])) for f in pr_data.get("files", []))
        if total_changes > args.max_lines:
            logger.warning(f"PR too large ({total_changes} changes > {args.max_lines} limit). Skipping analysis.")
            result = {
                "summary": f"⚠️ PR too large ({total_changes} changes) - skipped analysis",
                "final_status": "Approve",
                "timestamp": datetime.now().isoformat(),
                "pr_info": {
                    "title": pr_data.get("title", ""),
                    "author": pr_data.get("author", ""),
                    "branch": pr_data.get("branch", ""),
                    "files_changed": len(pr_data.get("files", []))
                },
                "execution_time": 0.0,
                "comments": [],
                "total_changes": total_changes,
                "skipped_reason": "size_limit_exceeded"
            }
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            return 0
        
        # Initialize agents
        agents = {}
        if groq_service or not use_llm:  # Allow heuristic-only mode
            agents = {
                "code_quality": CodeQualityAgent(groq_service) if groq_service else None,
                "bug_detection": BugDetectionAgent(groq_service) if groq_service else None,
                "security": SecurityAgent(groq_service) if groq_service else None,
                "dependency": DependencyAgent(groq_service) if groq_service else None,
                "documentation": DocumentationAgent(groq_service) if groq_service else None,
            }
        
        # Filter agents based on command line argument
        if args.agents:
            requested_agents = [a.strip() for a in args.agents.split(",")]
            agents = {k: v for k, v in agents.items() if k in requested_agents}
        
        # Remove None agents (when no Groq service available)
        agents = {k: v for k, v in agents.items() if v is not None}
        
        if not agents:
            logger.error("No agents available. Either provide GROQ_API_KEY or implement heuristic-only agents.")
            return 1
        
        # Run analysis
        start_time = datetime.now()
        raw_comments = []
        
        for agent_name, agent in agents.items():
            try:
                logger.info(f"Running {agent_name} agent...")
                comments = await agent.analyze(pr_data)
                for comment in comments:
                    comment.setdefault("source_agent", agent.name)
                raw_comments.extend(comments)
                logger.info(f"{agent_name} found {len(comments)} issues")
            except Exception as e:
                logger.error(f"Agent {agent_name} failed: {e}")
                raw_comments.append({
                    "line": 0,
                    "message": f"Agent {agent_name} failed: {str(e)}",
                    "severity": "error",
                    "type": "agent-failure",
                    "source_agent": agent_name,
                    "file": "*"
                })
        
        # Summarize comments per line
        logger.info("Summarizing comments per line...")
        aggregated_comments = await summarize_comments_per_line(raw_comments, groq_service, use_llm)
        
        # Determine final status
        final_status = determine_final_status(aggregated_comments)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Build result
        result = {
            "summary": f"🤖 AI Review Complete: {len(aggregated_comments)} issues found - {final_status}",
            "final_status": final_status,
            "timestamp": datetime.now().isoformat(),
            "pr_info": {
                "title": pr_data.get("title", ""),
                "author": pr_data.get("author", ""),
                "branch": pr_data.get("branch", ""),
                "files_changed": len(pr_data.get("files", []))
            },
            "execution_time": execution_time,
            "comments": aggregated_comments,
            "total_changes": total_changes,
            "agents_used": list(agents.keys()),
            "llm_enabled": use_llm
        }
        
        # Write output
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Analysis complete. Result written to {args.output}")
        logger.info(f"Final status: {final_status}")
        logger.info(f"Total issues: {len(aggregated_comments)}")
        
        # Return appropriate exit code for CI/CD
        severities = [c.get("severity", "info").lower() for c in aggregated_comments]
        if any(s in ["critical", "error"] for s in severities):
            logger.info("Exiting with code 1 (critical/error found)")
            return 1
        elif any(s in ["high", "warning"] for s in severities):
            logger.info("Exiting with code 2 (high/warning found)")
            return 2
        else:
            logger.info("Exiting with code 0 (no blocking issues)")
            return 0
            
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        error_result = {
            "summary": f"❌ Analysis failed: {str(e)}",
            "final_status": "Error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "comments": []
        }
        with open(args.output, 'w') as f:
            json.dump(error_result, f, indent=2)
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))