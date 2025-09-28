from dotenv import load_dotenv
import os
import json
import httpx
import asyncio
from typing import Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)
load_dotenv()


class GroqService:
    """
    Service to interact with Groq Cloud API for multiple LLaMA models.
    Enhanced to handle old vs new code comparisons for PR analysis.
    """

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")

        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        self.models = {
            "code_analysis": "llama-3.3-70b-versatile",
            "bug_detection": "llama-3.3-70b-versatile",
            "security": "llama-3.1-8b-instant",
            "documentation": "llama-3.1-8b-instant",
            "coordination": "llama-3.3-70b-versatile",
            "summarization": "llama-3.1-8b-instant"
        }

    async def generate_completion(
        self,
        prompt: str,
        model_type: str = "code_analysis",
        max_tokens: int = 1024,
        temperature: float = 0.1
    ) -> str:
        """
        Generate completion using specified Groq model
        """
        model = self.models.get(model_type, "llama3-8b-8192")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert code reviewer. Always return valid JSON responses."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.base_url, headers=self.headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Groq API error: {response.status_code} - {response.text}")
                    return f"Error: Status {response.status_code}"
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return f"Error: {str(e)}"

    def _extract_json_from_llama_response(self, response: str) -> Optional[List[Dict]]:
        """
        Extract JSON from LLaMA responses, fallback to text extraction if parsing fails
        """
        if not response or response.startswith("Error:"):
            return []

        # Attempt to parse JSON using multiple methods
        try:
            patterns = [r'\[[\s\S]*?\]', r'\{[\s\S]*?\}']
            for pat in patterns:
                matches = re.findall(pat, response, re.DOTALL)
                for match in matches:
                    try:
                        parsed = json.loads(match.strip())
                        return parsed if isinstance(parsed, list) else [parsed]
                    except json.JSONDecodeError:
                        continue

            delimiters = [('```json', '```'), ('```', '```'), ('[', ']'), ('JSON:', '\n')]
            for start, end in delimiters:
                idx_start = response.find(start)
                if idx_start != -1:
                    idx_start += len(start)
                    idx_end = response.find(end, idx_start) if end != '\n' else response.find(end, idx_start)
                    idx_end = len(response) if idx_end == -1 else idx_end
                    candidate = response[idx_start:idx_end].strip()
                    try:
                        parsed = json.loads(candidate)
                        return parsed if isinstance(parsed, list) else [parsed]
                    except json.JSONDecodeError:
                        continue

            # Fallback: treat entire response as JSON
            response_strip = response.strip()
            if response_strip.startswith('[') and response_strip.endswith(']'):
                try:
                    return json.loads(response_strip)
                except json.JSONDecodeError:
                    pass

            return self._extract_issues_from_text(response)
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            return self._extract_issues_from_text(response)

    def _extract_issues_from_text(self, text: str) -> List[Dict]:
        """
        Extract issues from plain text when JSON parsing fails
        """
        issues = []
        current_issue = {}
        line_pattern = re.compile(r'line\s*(\d+)', re.IGNORECASE)

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            line_match = line_pattern.search(line)
            if line_match:
                if current_issue:
                    issues.append(current_issue)
                current_issue = {"line": int(line_match.group(1)), "message": line, "severity": "info"}
            elif any(k in line.lower() for k in ['error', 'warning', 'issue', 'problem', 'bug', 'security']):
                if current_issue:
                    current_issue["message"] = line
                else:
                    issues.append({"line": 0, "message": line, "severity": "info"})

        if current_issue:
            issues.append(current_issue)

        return issues[:5]

    async def analyze_code_quality(self, changes: List[Dict], filename: str) -> List[Dict]:
        """Analyze code quality for unified change list."""
        if not changes:
            return []

        added_segments = []
        modified_segments = []
        for ch in changes:
            ctype = ch.get("type")
            if ctype == "added":
                added_segments.append(f"Line {ch.get('line')}: {ch.get('new_code','')}")
            elif ctype == "modified":
                modified_segments.append(
                    f"Line {ch.get('new_line')} - OLD: {ch.get('old_code','')} | NEW: {ch.get('new_code','')}"
                )

        added_code = "\n".join(added_segments)
        modified_code = "\n".join(modified_segments)

        prompt = f"""
Review code quality with focus on changed lines.

File: {filename}

Added Lines:
{added_code}

Modified Lines (OLD vs NEW):
{modified_code}

IMPORTANT: Respond only in JSON array:
[{{"line": line_number, "message": "...", "severity": "info|warning|error", "suggestion": "..."}}]

Check:
- Code style, readability
- Best practices
- Performance
- Naming conventions

Return [] if no issues.
"""
        response = await self.generate_completion(prompt, "code_analysis", max_tokens=512)
        return self._parse_review_comments(response)

    async def detect_bugs(self, changes: List[Dict], filename: str) -> List[Dict]:
        """Detect bugs in unified change list."""
        if not changes:
            return []

        all_code = []
        for ch in changes:
            t = ch.get("type")
            if t == "added":
                all_code.append(f"Line {ch.get('line')} (ADDED): {ch.get('new_code','')}")
            elif t == "removed":
                all_code.append(f"Line {ch.get('line')} (REMOVED): {ch.get('old_code','')}")
            elif t == "modified":
                all_code.append(
                    f"Line {ch.get('new_line')} OLD: {ch.get('old_code','')} NEW: {ch.get('new_code','')}"
                )
        all_code_str = "\n".join(all_code)[:2000]

        prompt = f"""
Analyze potential bugs in code changes.

File: {filename}
Code Context:
{all_code_str}

Respond only with JSON array:
[{{"line": line_number, "message": "...", "severity": "low|medium|high|critical", "type": "...", "suggestion": "..."}}]

Check:
- Null pointers
- Logic errors
- Index out of bounds
- Exception handling
- Resource leaks
"""
        response = await self.generate_completion(prompt, "bug_detection", max_tokens=512)
        return self._parse_review_comments(response)

    async def analyze_security(self, changes: List[Dict], filename: str) -> List[Dict]:
        """Analyze security vulnerabilities in unified changes."""
        if not changes:
            return []

        code_lines = []
        for ch in changes:
            t = ch.get("type")
            if t == "added":
                code_lines.append(f"Line {ch.get('line')} ADDED: {ch.get('new_code','')}")
            elif t == "modified":
                code_lines.append(f"Line {ch.get('new_line')} NEW: {ch.get('new_code','')}")
        code = "\n".join(code_lines)

        prompt = f"""
Analyze security issues in code changes.

File: {filename}
Changed Code:
{code}

Respond only in JSON array:
[{{"line": line_number, "message": "...", "severity": "low|medium|high|critical", "type": "...", "suggestion": "..."}}]

Check:
- Hardcoded secrets
- SQL injection
- XSS
- Command injection
- Cryptography
- Auth bypass
"""
        response = await self.generate_completion(prompt, "security", max_tokens=512)
        return self._parse_review_comments(response)

    async def analyze_documentation(self, changes: List[Dict], filename: str) -> List[Dict]:
        """Analyze documentation needs from unified changes (focus on additions & modifications)."""
        if not changes:
            return []

        added_lines = [f"Line {c.get('line')}: {c.get('new_code','')}" for c in changes if c.get("type") == "added"]
        code = "\n".join(added_lines)
        prompt = f"""
Review documentation for newly added code.

File: {filename}
New Code:
{code}

Respond only in JSON array:
[{{"line": line_number, "message": "...", "severity": "info|warning", "type": "...", "suggestion": "..."}}]

Check:
- Missing docstrings
- Missing comments
- Parameter/return documentation
"""
        response = await self.generate_completion(prompt, "documentation", max_tokens=512)
        return self._parse_review_comments(response)

    async def coordinate_review(self, agent_results: Dict, pr_info: Dict) -> Dict:
        """
        Aggregate multiple agent results and produce final PR status
        """
        all_issues = []
        for agent, issues in agent_results.items():
            for issue in issues:
                if isinstance(issue, dict) and issue.get("message"):
                    all_issues.append(f"[{agent}] {issue['message']}")

        prompt = f"""
Summarize pull request review.

Title: {pr_info.get('title', 'N/A')}
Total issues identified: {len(all_issues)}
Sample issues:
{chr(10).join(all_issues[:10])}

Respond ONLY in JSON:
{{"summary": "<concise actionable summary>", "status": "Approve|Needs Changes|Reject"}}
"""
        response = await self.generate_completion(prompt, "coordination", max_tokens=256)
        parsed = self._extract_json_from_llama_response(response)
        if parsed and isinstance(parsed[0], dict):
            return parsed[0]
        return {"summary": f"{len(all_issues)} issues found", "status": "Needs Changes" if all_issues else "Approve"}

    def _parse_review_comments(self, response: str) -> List[Dict]:
        parsed_comments = self._extract_json_from_llama_response(response)
        if not parsed_comments:
            return []

        validated = []
        for c in parsed_comments:
            if isinstance(c, dict) and "line" in c and "message" in c:
                entry = {
                    "line": c.get("line"),
                    "message": c.get("message"),
                    "severity": c.get("severity", "info"),
                    "type": c.get("type", "general"),
                    "suggestion": c.get("suggestion", "")
                }
                # file/source_agent tagging left to caller; don't overwrite if already present
                if "file" in c:
                    entry["file"] = c.get("file")
                if "source_agent" in c:
                    entry["source_agent"] = c.get("source_agent")
                validated.append(entry)
        return validated

    def _parse_json_response(self, response: str, default: List[str]) -> List[str]:
        parsed = self._extract_json_from_llama_response(response)
        return [str(item) for item in parsed] if parsed else default

    async def summarize_line_issues(self, file: str, line: int, issues: List[Dict]) -> Dict:
        """Generate a concise natural-language summary + single actionable suggestion for all issues on a line.
        Issues: list of dicts with keys (severity,type,message,suggestion,source_agent)
        Returns dict with keys: summary, suggestion.
        """
        if not issues:
            return {"summary": "No issues", "suggestion": None}
        # Build compact issue list
        lines = []
        for i, iss in enumerate(issues, 1):
            lines.append(f"{i}. [{iss.get('severity','info')}] {iss.get('source_agent','Agent')}: {iss.get('message')}")
        issues_block = "\n".join(lines)[:3000]
        prompt = f"""
Provide a concise professional code review summary for the following issues found in a pull request on one line.
File: {file}
Line: {line}
Issues:\n{issues_block}

Rules:
- Do NOT mention counts explicitly like '(+2 more)'.
- Combine related issues into one coherent sentence (max ~40 words) focusing on highest severity first.
- If multiple high/critical, list their core nouns separated by commas.
- Provide exactly one actionable suggestion (imperative tone) summarizing best remediation.
Return valid JSON object: {{"summary": "...", "suggestion": "..."}}
"""
        raw = await self.generate_completion(prompt, model_type="summarization", max_tokens=200, temperature=0.2)
        parsed = self._extract_json_from_llama_response(raw)
        if parsed and isinstance(parsed[0], dict):
            data = parsed[0]
            return {
                "summary": data.get("summary") or issues[0].get("message"),
                "suggestion": data.get("suggestion") or (issues[0].get("suggestion") if issues[0].get("suggestion") else None)
            }
        # Fallback heuristic
        highest = sorted(issues, key=lambda x: x.get('severity','info'))[0]
        suggestion = highest.get('suggestion') or next((i.get('suggestion') for i in issues if i.get('suggestion')), None)
        return {"summary": highest.get("message"), "suggestion": suggestion}
