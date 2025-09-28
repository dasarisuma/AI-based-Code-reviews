import ast
import re
from typing import Dict, List
import logging
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class DocumentationAgent:
    """
    Agent responsible for analyzing documentation quality
    """
    
    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "Documentation"
    
    async def analyze(self, pr_data: Dict) -> List[Dict]:
        """
        Analyze documentation quality for changed lines only
        """
        review_comments = []
        
        try:
            for file_data in pr_data.get("files", []):
                filename = file_data.get("filename")
                changes = file_data.get("changes", [])

                if not changes:
                    continue

                logger.info(f"Analyzing documentation for changes in: {filename}")

                static_issues = await self._analyze_changed_lines_documentation(filename, changes)
                for issue in static_issues:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(static_issues)

                # LLM analysis (only feed additions & modifications new code)
                llm_comments = await self.groq_service.analyze_documentation(changes, filename)
                for issue in llm_comments:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(llm_comments)
        
        except Exception as e:
            logger.error(f"Error in documentation analysis: {str(e)}")
            review_comments.append({
                "line": 0,
                "message": f"Error analyzing documentation: {str(e)}",
                "severity": "error",
                "type": "analysis-error"
            })
        
        return review_comments

    async def _analyze_changed_lines_documentation(self, filename: str, changes: List[Dict]) -> List[Dict]:
        """
        Analyze documentation in changed lines only
        """
        issues = []
        
        try:
            for change in changes:
                ctype = change.get("type")
                if ctype == "added":
                    line_number = change.get("line")
                    content = change.get("new_code", "")
                    issues.extend(self._check_line_documentation(filename, line_number, content))
                elif ctype == "modified":
                    # Focus on new code for documentation presence
                    line_number = change.get("new_line")
                    content = change.get("new_code", "")
                    issues.extend(self._check_line_documentation(filename, line_number, content))
        
        except Exception as e:
            logger.warning(f"Documentation analysis failed for {filename}: {str(e)}")
        
        return issues

    def _check_line_documentation(self, filename: str, line_number: int, content: str) -> List[Dict]:
        """
        Check individual line for documentation needs
        """
        issues = []
        
        try:
            import re
            
            # Python-specific checks
            if filename.endswith('.py'):
                # New function without docstring
                if re.match(r'\s*def\s+\w+\s*\(', content) and not content.strip().startswith('def __'):
                    issues.append({
                        "line": line_number,
                        "message": "New function should have a docstring",
                        "severity": "warning",
                        "type": "missing-docstring",
                        "suggestion": "Add docstring describing function purpose, parameters, and return value",
                        "file": filename,
                        "source_agent": self.name
                    })
                
                # New class without docstring
                if re.match(r'\s*class\s+\w+', content):
                    issues.append({
                        "line": line_number,
                        "message": "New class should have a docstring",
                        "severity": "warning", 
                        "type": "missing-class-docstring",
                        "suggestion": "Add class docstring describing purpose and usage",
                        "file": filename,
                        "source_agent": self.name
                    })
                
                # Complex logic without comments
                if any(keyword in content for keyword in ['if', 'for', 'while', 'try']) and len(content.strip()) > 50:
                    if '#' not in content:
                        issues.append({
                            "line": line_number,
                            "message": "Complex logic should have inline comments",
                            "severity": "info",
                            "type": "missing-comment",
                            "suggestion": "Add comment explaining the logic",
                            "file": filename,
                            "source_agent": self.name
                        })
                
                # TODO without description
                if re.search(r'\b(TODO|FIXME)\b', content) and len(content.strip()) < 20:
                    issues.append({
                        "line": line_number,
                        "message": "TODO/FIXME should include detailed description",
                        "severity": "info",
                        "type": "incomplete-todo",
                        "suggestion": "Add description of what needs to be done and why",
                        "file": filename,
                        "source_agent": self.name
                    })
            
            # JavaScript/TypeScript checks
            elif filename.endswith(('.js', '.ts', '.jsx', '.tsx')):
                # New function without JSDoc
                if re.match(r'\s*(function|const\s+\w+\s*=|\w+\s*:.*=>)', content):
                    issues.append({
                        "line": line_number,
                        "message": "Consider adding JSDoc for new function",
                        "severity": "info",
                        "type": "missing-jsdoc",
                        "suggestion": "Add /** JSDoc comment */ describing function",
                        "file": filename,
                        "source_agent": self.name
                    })
        
        except Exception as e:
            logger.warning(f"Line documentation check failed: {str(e)}")
        
        return issues
    
    async def _analyze_static_documentation(self, filename: str, content: str) -> List[str]:
        """
        Analyze documentation using static analysis
        """
        issues = []
        lines = content.split('\n')
        
        try:
            # Check for README files
            if filename.lower() == 'readme.md':
                issues.extend(self._analyze_readme_content(content))
            
            # Check for TODO/FIXME comments without explanation
            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()
                
                # TODO/FIXME without proper description
                if re.search(r'\b(TODO|FIXME)\b', line, re.IGNORECASE):
                    if len(line_stripped) < 20:  # Too short to be descriptive
                        issues.append(f"{filename}:Line {i}: TODO/FIXME comment needs more detailed description")
                
                # Check for magic numbers without comments
                magic_numbers = re.findall(r'\b(\d{2,})\b', line)
                for number in magic_numbers:
                    if int(number) > 10 and '#' not in line and '//' not in line:
                        issues.append(f"{filename}:Line {i}: Magic number '{number}' should be explained or made into a constant")
                
                # Check for complex regex without comments
                if re.search(r'["\'][^"\']*[\[\]\\^$.*+?{}|()][^"\']*["\']', line):
                    if '#' not in line and '//' not in line and i > 1:
                        prev_line = lines[i-2].strip() if i > 1 else ""
                        if not prev_line.startswith('#') and not prev_line.startswith('//'):
                            issues.append(f"{filename}:Line {i}: Complex regex should be documented")
        
        except Exception as e:
            logger.warning(f"Static documentation analysis failed for {filename}: {str(e)}")
        
        return issues
    
    async def _analyze_python_documentation(self, filename: str, content: str) -> List[str]:
        """
        Analyze Python documentation using AST
        """
        issues = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # Check function documentation
                if isinstance(node, ast.FunctionDef):
                    issues.extend(self._check_function_documentation(node, filename))
                
                # Check class documentation
                elif isinstance(node, ast.ClassDef):
                    issues.extend(self._check_class_documentation(node, filename))
        
        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception as e:
            logger.warning(f"Python documentation AST analysis failed for {filename}: {str(e)}")
        
        return issues
    
    def _check_function_documentation(self, node: ast.FunctionDef, filename: str) -> List[str]:
        """
        Check if a function has adequate documentation
        """
        issues = []
        
        try:
            docstring = ast.get_docstring(node)
            
            # Check if function needs docstring
            if self._function_needs_docstring(node):
                if not docstring:
                    issues.append(f"{filename}:Line {node.lineno}: Function '{node.name}' missing docstring")
                else:
                    # Check docstring quality
                    if len(docstring.split()) < 3:
                        issues.append(f"{filename}:Line {node.lineno}: Function '{node.name}' has inadequate docstring")
                    
                    # Check if docstring describes parameters
                    if len(node.args.args) > 1:  # More than just 'self'
                        if not any(word in docstring.lower() for word in ['param', 'arg', 'parameter']):
                            issues.append(f"{filename}:Line {node.lineno}: Function '{node.name}' docstring should describe parameters")
                    
                    # Check if docstring describes return value
                    has_return = any(isinstance(n, ast.Return) and n.value for n in ast.walk(node))
                    if has_return and 'return' not in docstring.lower():
                        issues.append(f"{filename}:Line {node.lineno}: Function '{node.name}' docstring should describe return value")
        
        except Exception as e:
            logger.warning(f"Error checking function documentation: {str(e)}")
        
        return issues
    
    def _check_class_documentation(self, node: ast.ClassDef, filename: str) -> List[str]:
        """
        Check if a class has adequate documentation
        """
        issues = []
        
        try:
            docstring = ast.get_docstring(node)
            
            # Public classes should have docstrings
            if not node.name.startswith('_'):
                if not docstring:
                    issues.append(f"{filename}:Line {node.lineno}: Class '{node.name}' missing docstring")
                elif len(docstring.split()) < 5:
                    issues.append(f"{filename}:Line {node.lineno}: Class '{node.name}' has inadequate docstring")
            
            # Check if class has public methods without docstrings
            public_methods = [n for n in node.body if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')]
            undocumented_methods = [m for m in public_methods if not ast.get_docstring(m)]
            
            if len(undocumented_methods) > 2:
                issues.append(f"{filename}:Line {node.lineno}: Class '{node.name}' has many undocumented public methods")
        
        except Exception as e:
            logger.warning(f"Error checking class documentation: {str(e)}")
        
        return issues
    
    def _function_needs_docstring(self, node: ast.FunctionDef) -> bool:
        """
        Determine if a function needs a docstring
        """
        # Skip very simple functions
        if len(node.body) <= 2 and not node.args.args:
            return False
        
        # Skip private functions (but not special methods)
        if node.name.startswith('_') and not node.name.startswith('__'):
            return False
        
        # Skip test functions with descriptive names
        if node.name.startswith('test_') and len(node.name.split('_')) > 3:
            return False
        
        return True
    
    def _analyze_readme_content(self, content: str) -> List[str]:
        """
        Analyze README.md content for completeness
        """
        issues = []
        content_lower = content.lower()
        
        try:
            # Check for essential sections
            essential_sections = {
                'installation': ['install', 'setup', 'getting started'],
                'usage': ['usage', 'example', 'how to use'],
                'description': ['description', 'about', 'what is'],
            }
            
            for section, keywords in essential_sections.items():
                if not any(keyword in content_lower for keyword in keywords):
                    issues.append(f"README.md: Missing {section} section")
            
            # Check if README is too short
            if len(content.split()) < 50:
                issues.append("README.md: README seems too brief, consider adding more details")
            
            # Check for code examples
            if 'usage' in content_lower and '```' not in content:
                issues.append("README.md: Usage section should include code examples")
        
        except Exception as e:
            logger.warning(f"Error analyzing README: {str(e)}")
        
        return issues