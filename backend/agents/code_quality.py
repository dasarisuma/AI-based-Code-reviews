from typing import Dict, List
import logging
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class CodeQualityAgent:
    """
    Agent responsible for analyzing code quality and style
    """
    
    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "CodeQuality"
    
    async def analyze(self, pr_data: Dict) -> List[Dict]:
        """
        Analyze code quality for only changed lines in PR
        """
        review_comments = []
        
        try:
            for file_data in pr_data.get("files", []):
                filename = file_data.get("filename")
                changes = file_data.get("changes", [])

                if not changes:
                    continue

                logger.info(f"Analyzing code quality for changes in: {filename}")

                static_issues = await self._analyze_changed_lines_static(filename, changes)
                # tag issues with filename and source agent
                for issue in static_issues:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(static_issues)

                llm_comments = await self.groq_service.analyze_code_quality(changes, filename)
                for issue in llm_comments:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(llm_comments)
        
        except Exception as e:
            logger.error(f"Error in code quality analysis: {str(e)}")
            review_comments.append({
                "line": 0,
                "message": f"Error analyzing code quality: {str(e)}",
                "severity": "error",
                "type": "analysis-error"
            })
        
        return review_comments

    async def _analyze_changed_lines_static(self, filename: str, changes: List[Dict]) -> List[Dict]:
        """
        Run static analysis only on changed lines
        """
        issues = []
        
        try:
            for change in changes:
                ctype = change.get("type")
                if ctype == "added":
                    line_number = change.get("line")
                    content = change.get("new_code", "")
                    issues.extend(self._check_line_quality(filename, line_number, content))
                elif ctype == "modified":
                    new_line = change.get("new_line")
                    new_code = change.get("new_code", "")
                    issues.extend(self._check_line_quality(filename, new_line, new_code))
                # For removed lines we generally don't raise style issues
        
        except Exception as e:
            logger.warning(f"Static analysis failed for {filename}: {str(e)}")
        
        return issues

    def _check_line_quality(self, filename: str, line_number: int, content: str) -> List[Dict]:
        """
        Check individual line for code quality issues
        """
        issues = []
        
        try:
            # Python-specific checks
            if filename.endswith('.py'):
                # Long lines
                if len(content) > 88:
                    issues.append({
                        "line": line_number,
                        "message": f"Line too long ({len(content)} characters, max 88)",
                        "severity": "warning", 
                        "type": "line-length",
                        "suggestion": "Break line into multiple lines or simplify expression",
                        "file": filename,
                        "source_agent": self.name
                    })
                
                # Variable naming
                import re
                if re.search(r'\b[a-z]+[A-Z]', content) and 'class ' not in content:
                    issues.append({
                        "line": line_number,
                        "message": "Use snake_case for variable names (PEP 8)",
                        "severity": "info",
                        "type": "naming-convention", 
                        "suggestion": "Convert camelCase to snake_case",
                        "file": filename,
                        "source_agent": self.name
                    })
                
                # TODO/FIXME without description
                if re.search(r'\b(TODO|FIXME)\b', content) and len(content.strip()) < 20:
                    issues.append({
                        "line": line_number,
                        "message": "TODO/FIXME comment should include detailed description",
                        "severity": "info",
                        "type": "incomplete-comment",
                        "suggestion": "Add description of what needs to be done",
                        "file": filename,
                        "source_agent": self.name
                    })
            
            # JavaScript/TypeScript checks
            elif filename.endswith(('.js', '.ts', '.jsx', '.tsx')):
                # var usage
                if 'var ' in content:
                    issues.append({
                        "line": line_number,
                        "message": "Use 'let' or 'const' instead of 'var'",
                        "severity": "warning",
                        "type": "deprecated-syntax",
                        "suggestion": "Replace 'var' with 'let' or 'const'",
                        "file": filename,
                        "source_agent": self.name
                    })
                
                # == instead of ===
                if ' == ' in content and ' === ' not in content:
                    issues.append({
                        "line": line_number,
                        "message": "Use '===' for strict equality comparison",
                        "severity": "warning", 
                        "type": "loose-equality",
                        "suggestion": "Replace '==' with '==='",
                        "file": filename,
                        "source_agent": self.name
                    })
        
        except Exception as e:
            logger.warning(f"Line quality check failed: {str(e)}")
        
        return issues
    
