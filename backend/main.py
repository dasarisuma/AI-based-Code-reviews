from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import logging
from typing import Dict, List, Optional
import os
from datetime import datetime

from agents.code_quality import CodeQualityAgent
from agents.bug_detection import BugDetectionAgent
from agents.security import SecurityAgent
from agents.dependency import DependencyAgent
from agents.documentation import DocumentationAgent
from services.github_service import GitHubService
from services.groq_service import GroqService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AutoPR - AI Code Review System", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class PRReviewRequest(BaseModel):
    pr_url: str
    github_token: str

class PRReviewResponse(BaseModel):
    summary: str
    final_status: str
    timestamp: str
    pr_info: Dict
    execution_time: float
    comments: List[Dict]  # aggregated per-line comments now
    agents: Optional[Dict[str, List[str]]] = None  # deprecated

# Initialize services
try:
    groq_service = GroqService()
    logger.info("GroqService initialized successfully")
except ValueError as e:
    logger.error(f"Failed to initialize GroqService: {e}")
    raise

github_service = GitHubService()

# Initialize agents
# random comment to test commits
code_quality_agent = CodeQualityAgent(groq_service)
bug_detection_agent = BugDetectionAgent(groq_service)
security_agent = SecurityAgent(groq_service)
dependency_agent = DependencyAgent(groq_service)
documentation_agent = DocumentationAgent(groq_service)
coordinator_agent = None  # Coordinator removed in simplified version
crew_runner = None
print("random comment to test commits")
async def summarize_comments_per_line(raw_comments: List[Dict]) -> List[Dict]:
    if not raw_comments:
        return []
    grouped: Dict[tuple, List[Dict]] = {}
    for c in raw_comments:
        key = (c.get("file", "*"), c.get("line", 0))
        grouped.setdefault(key, []).append(c)
    results: List[Dict] = []
    # Parallelize LLM summaries with gather
    tasks = []
    meta = []
    for (file, line), issues in grouped.items():
        meta.append((file, line, issues))
        tasks.append(groq_service.summarize_line_issues(file, line, issues))
    summaries = await asyncio.gather(*tasks, return_exceptions=True)
    for (file, line, issues), summ in zip(meta, summaries):
        if isinstance(summ, Exception):
            # fallback heuristic
            base_msg = issues[0].get("message")
            suggestion = issues[0].get("suggestion")
            severity = issues[0].get("severity", "info")
            results.append({
                "file": file,
                "line": line,
                "message": base_msg,
                "severity": severity,
                "type": issues[0].get("type", "general"),
                "suggestion": suggestion,
                "source_agent": issues[0].get("source_agent")
            })
        else:
            # choose highest severity among issues
            severity = sorted(issues, key=lambda x: x.get("severity","info"))[0].get("severity","info")
            results.append({
                "file": file,
                "line": line,
                "message": summ.get("summary"),
                "severity": severity,
                "type": issues[0].get("type", "general"),
                "suggestion": summ.get("suggestion"),
                "source_agent": issues[0].get("source_agent")
            })
    # Order consistently
    results.sort(key=lambda x: (x["file"], x["line"]))
    return results

def convert_agent_results_to_strings(agent_results: Dict[str, List]) -> Dict[str, List[str]]:
    """
    Convert agent results from dict format to string format for Pydantic validation
    """
    converted_results = {}
    
    for agent_name, results in agent_results.items():
        string_results = []
        
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    # Convert dict to readable string
                    line = item.get("line", 0)
                    message = item.get("message", "")
                    severity = item.get("severity", "info")
                    suggestion = item.get("suggestion", "")
                    
                    # Format based on severity
                    severity_emoji = {
                        "critical": "🔴",
                        "error": "🔴", 
                        "high": "🔴",
                        "warning": "⚠️",
                        "medium": "⚠️",
                        "info": "ℹ️",
                        "low": "ℹ️"
                    }
                    
                    emoji = severity_emoji.get(severity.lower(), "ℹ️")
                    formatted_message = f"{emoji} Line {line}: {message}"
                    
                    if suggestion:
                        formatted_message += f" | Suggestion: {suggestion}"
                    
                    string_results.append(formatted_message)
                    
                elif isinstance(item, str):
                    string_results.append(item)
                else:
                    string_results.append(str(item))
        else:
            # Handle non-list results
            if results:
                string_results.append(str(results))
        
        converted_results[agent_name] = string_results
    
    return converted_results

@app.post("/review-pr", response_model=PRReviewResponse)
async def review_pull_request(request: PRReviewRequest):
    """
    Main endpoint to review a GitHub Pull Request
    """
    start_time = datetime.now()
    
    try:
        logger.info(f"Starting PR review for: {request.pr_url}")
        
        # Parse PR URL and fetch data
        pr_data = await github_service.fetch_pr_data(request.pr_url, request.github_token)
        print("PR DATA IS ", pr_data, "END OF PR DATA")
        # Decide execution mode (CrewAI vs legacy)
        logger.info("Running concurrent agent analysis")
        agent_tasks = [
            code_quality_agent.analyze(pr_data),
            bug_detection_agent.analyze(pr_data),
            security_agent.analyze(pr_data),
            dependency_agent.analyze(pr_data),
            documentation_agent.analyze(pr_data)
        ]
        agent_results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        compiled_results = {}
        agent_names = ["CodeQuality", "BugDetection", "Security", "Dependency", "Documentation"]
        for i, result in enumerate(agent_results):
            agent_name = agent_names[i]
            if isinstance(result, Exception):
                logger.error(f"Agent {agent_name} failed: {result}")
                compiled_results[agent_name] = [{"line": 0, "message": f"Agent failed: {str(result)}", "severity": "error"}]
            else:
                compiled_results[agent_name] = result if result else []
        
        # Flatten to unified comments list
        unified_comments: List[Dict] = []
        for agent_name, issues in compiled_results.items():
            for issue in issues:
                if isinstance(issue, dict):
                    issue.setdefault("source_agent", agent_name)
                    unified_comments.append(issue)
                else:
                    unified_comments.append({
                        "line": 0,
                        "message": str(issue),
                        "severity": "info",
                        "type": "text",
                        "source_agent": agent_name
                    })

        # Replace raw comments with aggregated per-line comments (single entry per line)
        aggregated_comments = await summarize_comments_per_line(unified_comments)

        # Coordinate final review
        total_issues = len(unified_comments)
        if total_issues == 0:
            summary = "✅ No issues found in this PR"
            final_status = "Approve"
        elif total_issues <= 3:
            summary = f"⚠️ {total_issues} minor issues found"
            final_status = "Needs Changes"
        else:
            summary = f"🔴 {total_issues} issues found requiring attention"
            final_status = "Needs Changes"

        execution_time = (datetime.now() - start_time).total_seconds()

        return PRReviewResponse(
            summary=summary,
            final_status=final_status,
            timestamp=datetime.now().isoformat(),
            pr_info={
                "title": pr_data.get("title", ""),
                "author": pr_data.get("author", ""),
                "branch": pr_data.get("branch", ""),
                "files_changed": len(pr_data.get("files", []))
            },
            execution_time=execution_time,
            comments=aggregated_comments,
            agents=None
        )
        
    except Exception as e:
        logger.error(f"Error processing PR review: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AutoPR - AI Code Review System",
        "version": "1.0.0",
        "endpoints": {
            "/review-pr": "POST - Review a GitHub Pull Request",
            "/health": "GET - Health check",
            "/docs": "GET - API documentation"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)