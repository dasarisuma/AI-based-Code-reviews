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
import subprocess
from typing import Dict, List, Optional

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.github_service import GitHubService
from services.groq_service import GroqService
from severity import weight, status_from_comments
from agents.code_quality import CodeQualityAgent
from agents.bug_detection import BugDetectionAgent
from agents.security import SecurityAgent
from agents.dependency import DependencyAgent
from agents.documentation import DocumentationAgent

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
    # Backwards compatibility wrapper
    return weight(severity)

def determine_final_status(comments):
    return status_from_comments(c.get("severity", "info") for c in comments)

async def main():
    parser = argparse.ArgumentParser(description="AI Code Review Analysis")
    # Source selection
    parser.add_argument("--pr-url", help="GitHub PR URL (optional if using --base-ref/--head-ref)")
    parser.add_argument("--github-token", help="GitHub personal access token (or set GITHUB_TOKEN env)")
    parser.add_argument("--base-ref", help="Git base ref (for local diff mode)")
    parser.add_argument("--head-ref", help="Git head ref (for local diff mode)")
    parser.add_argument("--local-diff", action="store_true", help="Force local diff mode even if PR URL provided")

    # Behavior & filtering
    parser.add_argument("--output", default="review.json", help="Output JSON file")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis (heuristics only)")
    parser.add_argument("--max-lines", type=int, default=1000, help="Skip analysis if PR changes exceed this limit")
    parser.add_argument("--agents", help="Comma-separated list of agents to run (code_quality,bug_detection,security,dependency,documentation)")
    parser.add_argument("--fail-on", help="Comma-separated severities that should cause exit code 1 (default: critical,error)")
    parser.add_argument("--single-exit-code", action="store_true", help="If set, any fail-on severity returns exit 1; otherwise multi-tier exit codes 0/1/2")
    parser.add_argument("--config", help="Path to JSON config file providing arguments (CLI overrides config)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()

    # Load config file if provided
    file_cfg = {}
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as cf:
                file_cfg = json.load(cf)
        except Exception as e:
            print(f"WARNING: Failed loading config file {args.config}: {e}", file=sys.stderr)

    def cfg(key, default=None):
        # Priority: CLI arg (if set & not None) > env var > config file > default
        cli_val = getattr(args, key.replace('-', '_'), None)
        if cli_val not in [None, '']:
            return cli_val
        env_key = key.upper().replace('-', '_')
        if env_key in os.environ and os.environ[env_key]:
            return os.environ[env_key]
        return file_cfg.get(key, default)

    pr_url = cfg('pr-url')
    github_token = cfg('github-token') or os.getenv('GITHUB_TOKEN')
    base_ref = cfg('base-ref')
    head_ref = cfg('head-ref')
    force_local = bool(args.local_diff)
    fail_on_raw = cfg('fail-on', 'critical,error')
    fail_on_set = {s.strip().lower() for s in (fail_on_raw or '').split(',') if s.strip()}
    single_exit = bool(args.single_exit_code)
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug(f"Config resolved: pr_url={pr_url} base_ref={base_ref} head_ref={head_ref} local={force_local}")
    
    # Validate source selection
    if not pr_url and not (base_ref and head_ref):
        parser.error("Either --pr-url OR both --base-ref and --head-ref must be provided")
    if pr_url and (base_ref and head_ref) and not force_local:
        logger.info("Both PR URL and local refs provided; using PR URL (pass --local-diff to force local mode)")
    
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
        # Build PR / diff data
        if pr_url and not force_local:
            if not github_token:
                raise ValueError("GitHub token required for PR mode (provide --github-token or set GITHUB_TOKEN)")
            logger.info(f"Fetching PR data from: {pr_url}")
            pr_data = await github_service.fetch_pr_data(pr_url, github_token)
        else:
            logger.info(f"Running in local diff mode: {base_ref}..{head_ref}")
            pr_data = build_local_diff_pr_data(base_ref, head_ref, github_service)
        
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
        # Fail-on logic
        if any(s in fail_on_set for s in severities):
            logger.info(f"Fail-on severities hit ({fail_on_set}); returning exit 1")
            return 1
        if single_exit:
            logger.info("single-exit-code enabled and no fail-on severities present -> exit 0")
            return 0
        # Legacy tiered exit mode
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

# ----------------- Helper Functions (Local Diff Mode) -----------------

def run_git_command(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{e.output}")

def split_patches(diff_text: str) -> List[Dict[str, str]]:
    patches = []
    current: Dict[str, Optional[str]] = {"file": None, "patch": None}
    lines = diff_text.splitlines()
    buf: List[str] = []
    current_file: Optional[str] = None
    for line in lines:
        if line.startswith('diff --git'):
            # flush
            if current_file and buf:
                patches.append({"file": current_file, "patch": '\n'.join(buf)})
            buf = []
            current_file = None
        if line.startswith('+++ b/'):
            current_file = line[6:].strip()
        if line.startswith('@@') or line.startswith('+') or line.startswith('-') or line.startswith(' '):
            buf.append(line)
    if current_file and buf:
        patches.append({"file": current_file, "patch": '\n'.join(buf)})
    return patches

def build_local_diff_pr_data(base_ref: str, head_ref: str, gh_service: GitHubService) -> Dict:
    if not base_ref or not head_ref:
        raise ValueError("Both base_ref and head_ref required for local diff mode")
    # Ensure refs exist
    run_git_command(['git', 'fetch', '--quiet', 'origin', base_ref]) if '/' in base_ref else None
    run_git_command(['git', 'fetch', '--quiet', 'origin', head_ref]) if '/' in head_ref else None
    diff = run_git_command(['git', 'diff', f'{base_ref}..{head_ref}', '--unified=0', '--no-color'])
    patch_entries = split_patches(diff)
    files: List[Dict] = []
    for entry in patch_entries:
        patch = entry['patch']
        if not patch:
            continue
        try:
            parsed = gh_service._extract_changes_v2(patch)  # reuse internal parser
        except Exception:
            continue
        unified_changes: List[Dict] = []
        for a in parsed['added_lines']:
            unified_changes.append({"type": "added", "line": a['line_number'], "new_code": a['content']})
        for r in parsed['removed_lines']:
            unified_changes.append({"type": "removed", "line": r['line_number'], "old_code": r['content']})
        for m in parsed['modified_lines']:
            unified_changes.append({
                "type": "modified",
                "old_line": m.get('old_line_number', m.get('line_number')),
                "new_line": m.get('new_line_number', m.get('line_number')),
                "old_code": m['old_content'],
                "new_code": m['new_content']
            })
        if unified_changes:
            files.append({"filename": entry['file'], "changes": unified_changes})
    return {
        "title": f"Local diff {base_ref}..{head_ref}",
        "pr_url": None,
        "files": files
    }