import ast
import subprocess
import tempfile
import os
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
    
    async def _run_linting(self, filename: str, content: str) -> List[str]:
        """
        Run static analysis with linters
        """
        issues = []
        
        try:
            if filename.endswith('.py'):
                issues.extend(await self._run_pylint(filename, content))
                issues.extend(await self._run_flake8(filename, content))
            elif filename.endswith(('.js', '.ts', '.jsx', '.tsx')):
                issues.extend(await self._run_eslint_style_check(filename, content))
        
        except Exception as e:
            logger.warning(f"Linting error for {filename}: {str(e)}")
        
        return issues
    
    async def _run_pylint(self, filename: str, content: str) -> List[str]:
        """
        Run pylint analysis
        """
        issues = []
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            # Run pylint with specific checks
            result = subprocess.run([
                'python', '-m', 'pylint', 
                '--disable=all',
                '--enable=C0103,C0111,C0112,C0113,W0613,W0612',  # Selected quality checks
                '--output-format=text',
                temp_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if ':' in line and filename in line:
                        issues.append(f"[Pylint] {line.strip()}")
            
            os.unlink(temp_path)
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Pylint not available or timeout
            pass
        except Exception as e:
            logger.warning(f"Pylint analysis failed: {str(e)}")
        
        return issues
    
    async def _run_flake8(self, filename: str, content: str) -> List[str]:
        """
        Run flake8 analysis
        """
        issues = []
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            result = subprocess.run([
                'python', '-m', 'flake8',
                '--select=E,W,F',  # Select error, warning, and flake categories
                '--max-line-length=88',
                temp_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        # Replace temp path with actual filename
                        formatted_line = line.replace(temp_path, filename)
                        issues.append(f"[Flake8] {formatted_line}")
            
            os.unlink(temp_path)
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Flake8 not available or timeout
            pass
        except Exception as e:
            logger.warning(f"Flake8 analysis failed: {str(e)}")
        
        return issues
    
    async def _run_eslint_style_check(self, filename: str, content: str) -> List[str]:
        """
        Basic JavaScript/TypeScript style checks
        """
        issues = []
        
        try:
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                # Check for common style issues
                if '==' in line and '===' not in line:
                    issues.append(f"[Style] {filename}:{i}: Use '===' instead of '=='")
                
                if 'var ' in line:
                    issues.append(f"[Style] {filename}:{i}: Use 'let' or 'const' instead of 'var'")
                
                if len(line) > 120:
                    issues.append(f"[Style] {filename}:{i}: Line too long ({len(line)} characters)")
        
        except Exception as e:
            logger.warning(f"JS/TS style check failed: {str(e)}")
        
        return issues
    
    async def _analyze_ast(self, filename: str, content: str) -> List[str]:
        """
        Analyze code using Abstract Syntax Tree (Python only)
        """
        issues = []
        
        if not filename.endswith('.py'):
            return issues
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # Check for complex functions
                if isinstance(node, ast.FunctionDef):
                    complexity = self._calculate_complexity(node)
                    if complexity > 10:
                        issues.append(f"[AST] {filename}:Line {node.lineno}: Function '{node.name}' is too complex (complexity: {complexity})")
                    
                    # Check for missing docstring
                    if not ast.get_docstring(node):
                        issues.append(f"[AST] {filename}:Line {node.lineno}: Function '{node.name}' missing docstring")
                
                # Check for long parameter lists
                if isinstance(node, ast.FunctionDef) and len(node.args.args) > 5:
                    issues.append(f"[AST] {filename}:Line {node.lineno}: Function '{node.name}' has too many parameters ({len(node.args.args)})")
                
                # Check for nested loops (performance concern)
                if isinstance(node, ast.For):
                    nested_loops = sum(1 for child in ast.walk(node) if isinstance(child, (ast.For, ast.While)))
                    if nested_loops > 2:
                        issues.append(f"[AST] {filename}:Line {node.lineno}: Deeply nested loops detected (depth: {nested_loops})")
        
        except SyntaxError as e:
            issues.append(f"[AST] {filename}:Line {e.lineno}: Syntax error - {e.msg}")
        except Exception as e:
            logger.warning(f"AST analysis failed for {filename}: {str(e)}")
        
        return issues
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """
        Calculate cyclomatic complexity of a function
        """
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.Try)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity