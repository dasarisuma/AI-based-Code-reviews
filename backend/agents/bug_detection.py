import ast
import re
from typing import Dict, List
import logging
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class BugDetectionAgent:
    """
    Agent responsible for detecting potential bugs and logical errors
    """
    
    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "BugDetection"
    
    async def analyze(self, pr_data: Dict) -> List[Dict]:
        review_comments = []
        try:
            for file_data in pr_data.get("files", []):
                filename = file_data.get("filename")
                changes = file_data.get("changes", [])

                if not changes:
                    continue

                logger.info(f"Analyzing for bugs in changes: {filename}")

                pattern_issues = await self._detect_bug_patterns_in_changes(filename, changes)
                for issue in pattern_issues:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(pattern_issues)

                llm_comments = await self.groq_service.detect_bugs(changes, filename)
                for issue in llm_comments:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(llm_comments)

        except Exception as e:
            logger.error(f"Error in bug detection: {str(e)}")
            review_comments.append({
                "line": 0,
                "message": f"Error analyzing for bugs: {str(e)}",
                "severity": "error",
                "type": "analysis-error"
            })
        
        return review_comments

    async def _detect_bug_patterns_in_changes(self, filename: str, changes: List[Dict]) -> List[Dict]:
        issues = []
        try:
            for change in changes:
                ctype = change.get("type")
                if ctype == "added":
                    issues.extend(self._check_line_for_bugs(filename, change.get("line"), change.get("new_code", "")))
                elif ctype == "modified":
                    issues.extend(self._check_line_for_bugs(filename, change.get("new_line"), change.get("new_code", "")))
        except Exception as e:
            logger.warning(f"Bug pattern detection failed for {filename}: {str(e)}")
        return issues

    def _check_line_for_bugs(self, filename: str, line_number: int, content: str) -> List[Dict]:
        issues = []
        try:
            if filename.endswith(".py"):
                if re.search(r"/\s*[\w\.\[\]]+\s*[^=]", content) and "if" not in content:
                    issues.append({
                        "line": line_number,
                        "message": "Potential division by zero",
                        "severity": "medium",
                        "type": "division-by-zero",
                        "suggestion": "Add zero check before division",
                        "file": filename,
                        "source_agent": self.name
                    })
                if re.match(r"\s*except\s*:\s*$", content):
                    issues.append({
                        "line": line_number,
                        "message": "Bare except clause catches all exceptions",
                        "severity": "warning",
                        "type": "bare-except",
                        "suggestion": "Specify exception type: except SpecificException:",
                        "file": filename,
                        "source_agent": self.name
                    })
            elif filename.endswith((".js", ".ts", ".jsx", ".tsx")):
                if ".length" in content and "if" not in content and "?" not in content:
                    issues.append({
                        "line": line_number,
                        "message": "Check for undefined before accessing .length",
                        "severity": "medium",
                        "type": "undefined-access",
                        "suggestion": "Use optional chaining: array?.length",
                        "file": filename,
                        "source_agent": self.name
                    })
        except Exception as e:
            logger.warning(f"Line bug check failed: {str(e)}")
        return issues
