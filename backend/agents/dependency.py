import ast
import networkx as nx
from typing import Dict, List, Set, Tuple
import logging
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class DependencyAgent:
    """
    Agent responsible for analyzing dependencies and breaking changes
    """
    
    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "Dependency"
    
    async def analyze(self, pr_data: Dict) -> List[Dict]:
        """Analyze dependency-related risks using unified file change schema."""
        review_comments: List[Dict] = []
        try:
            for file_data in pr_data.get("files", []):
                filename = file_data.get("filename")
                changes = file_data.get("changes", [])
                if not changes:
                    continue
                logger.info(f"Analyzing dependency impacts for changes in: {filename}")

                # Derive removed, added, modified line lists
                removed = [c for c in changes if c.get("type") == "removed"]
                added = [c for c in changes if c.get("type") == "added"]
                modified = [c for c in changes if c.get("type") == "modified"]

                breaking_changes = self._detect_breaking_changes_unified(filename, removed, modified)
                for issue in breaking_changes:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(breaking_changes)

                import_issues = self._check_new_imports_unified(filename, added, modified)
                for issue in import_issues:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(import_issues)

        except Exception as e:
            logger.error(f"Error in dependency analysis: {str(e)}")
            review_comments.append({
                "line": 0,
                "message": f"Error analyzing dependencies: {str(e)}",
                "severity": "error",
                "type": "analysis-error",
                "file": "*",
                "source_agent": self.name
            })
        return review_comments

    def _detect_breaking_changes_unified(self, filename: str, removed: List[Dict], modified: List[Dict]) -> List[Dict]:
        issues: List[Dict] = []
        try:
            import re
            # Removed functions/classes
            for r in removed:
                content = r.get("old_code", "")
                line_number = r.get("line")
                m = re.search(r'(def|class)\s+(\w+)', content)
                if m:
                    issues.append({
                        "line": line_number,
                        "message": f"Removed {m.group(1)} '{m.group(2)}' - potential breaking change",
                        "severity": "high",
                        "type": "breaking-change",
                        "suggestion": "Consider deprecation before removal"
                    })
            # Modified signatures
            for mchg in modified:
                old_code = mchg.get("old_code", "")
                new_code = mchg.get("new_code", "")
                line_number = mchg.get("new_line")
                old_sig = re.search(r'def\s+(\w+)\s*\([^)]*\)', old_code)
                new_sig = re.search(r'def\s+(\w+)\s*\([^)]*\)', new_code)
                if old_sig and new_sig and old_sig.group(1) == new_sig.group(1) and old_sig.group(0) != new_sig.group(0):
                    issues.append({
                        "line": line_number,
                        "message": f"Function '{old_sig.group(1)}' signature changed - potential breaking change",
                        "severity": "medium",
                        "type": "signature-change",
                        "suggestion": "Preserve backward compatibility or document change"
                    })
        except Exception as e:
            logger.warning(f"Unified breaking change detection failed for {filename}: {e}")
        return issues

    def _check_new_imports_unified(self, filename: str, added: List[Dict], modified: List[Dict]) -> List[Dict]:
        issues: List[Dict] = []
        try:
            import re
            candidate_lines = []
            candidate_lines.extend([(a.get("line"), a.get("new_code", "")) for a in added])
            candidate_lines.extend([(m.get("new_line"), m.get("new_code", "")) for m in modified])
            for line_number, content in candidate_lines:
                if not content:
                    continue
                if re.match(r'^\s*(import|from)\s+', content):
                    if any(pkg in content.lower() for pkg in ['os.system', 'subprocess', 'eval', 'exec']):
                        issues.append({
                            "line": line_number,
                            "message": "New import references potentially dangerous functionality",
                            "severity": "warning",
                            "type": "dangerous-import",
                            "suggestion": "Review necessity and security implications"
                        })
                    if re.search(r'from\s+\.+\w+', content):
                        issues.append({
                            "line": line_number,
                            "message": "Relative import added - ensure package structure",
                            "severity": "info",
                            "type": "relative-import",
                            "suggestion": "Prefer absolute imports for clarity"
                        })
        except Exception as e:
            logger.warning(f"Unified new import check failed for {filename}: {e}")
        return issues

    async def _detect_breaking_changes_in_lines(self, filename: str, changed_lines: Dict) -> List[Dict]:
        """
        Detect breaking changes in modified lines
        """
        issues = []
        
        try:
            # Check removed lines for potential breaking changes
            for line_data in changed_lines.get("removed_lines", []):
                content = line_data["content"]
                line_number = line_data["line_number"]
                
                # Check if function/class definition was removed
                import re
                if re.search(r'def\s+(\w+)', content) or re.search(r'class\s+(\w+)', content):
                    func_or_class = re.search(r'(def|class)\s+(\w+)', content)
                    if func_or_class:
                        issues.append({
                            "line": line_number,
                            "message": f"Removed {func_or_class.group(1)} '{func_or_class.group(2)}' - potential breaking change",
                            "severity": "high",
                            "type": "breaking-change",
                            "suggestion": "Consider deprecation instead of removal"
                        })
            
            # Check modified lines for signature changes
            for line_data in changed_lines.get("modified_lines", []):
                old_content = line_data["old_content"]
                new_content = line_data["new_content"] 
                line_number = line_data["line_number"]
                
                # Check if function signature changed
                import re
                old_func = re.search(r'def\s+(\w+)\s*\([^)]*\)', old_content)
                new_func = re.search(r'def\s+(\w+)\s*\([^)]*\)', new_content)
                
                if old_func and new_func and old_func.group(1) == new_func.group(1):
                    if old_func.group(0) != new_func.group(0):
                        issues.append({
                            "line": line_number,
                            "message": f"Function '{old_func.group(1)}' signature changed - potential breaking change",
                            "severity": "medium",
                            "type": "signature-change",
                            "suggestion": "Consider backward compatibility"
                        })
        
        except Exception as e:
            logger.warning(f"Breaking change detection failed: {str(e)}")
        
        return issues

    async def _check_new_imports(self, filename: str, changed_lines: Dict) -> List[Dict]:
        """
        Check new imports for potential issues
        """
        issues = []
        
        try:
            for line_data in changed_lines.get("added_lines", []):
                content = line_data["content"]
                line_number = line_data["line_number"]
                
                # Check for new imports
                import re
                if re.match(r'^\s*(import|from)\s+', content):
                    # Check for potentially problematic imports
                    if any(pkg in content.lower() for pkg in ['os.system', 'subprocess', 'eval', 'exec']):
                        issues.append({
                            "line": line_number,
                            "message": "New import of potentially dangerous module",
                            "severity": "warning",
                            "type": "dangerous-import",
                            "suggestion": "Review security implications"
                        })
                    
                    # Check for relative imports
                    if re.search(r'from\s+\.+\w+', content):
                        issues.append({
                            "line": line_number,
                            "message": "Relative import added - ensure module structure is correct",
                            "severity": "info",
                            "type": "relative-import",
                            "suggestion": "Consider absolute imports for clarity"
                        })
        
        except Exception as e:
            logger.warning(f"Import check failed: {str(e)}")
        
        return issues
    
    async def _build_dependency_graph(self, changed_files: List[Dict]) -> nx.DiGraph:
        """
        Build a dependency graph from the changed files
        """
        graph = nx.DiGraph()
        
        try:
            for file_data in changed_files:
                filename = file_data["filename"]
                content = file_data["content"]
                
                # Add file as node
                graph.add_node(filename)
                
                if filename.endswith('.py'):
                    dependencies = self._extract_python_dependencies(content)
                elif filename.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    dependencies = self._extract_js_dependencies(content)
                else:
                    continue
                
                # Add dependency edges
                for dep in dependencies:
                    if dep != filename:  # Avoid self-dependencies
                        graph.add_edge(filename, dep)
        
        except Exception as e:
            logger.warning(f"Error building dependency graph: {str(e)}")
        
        return graph
    
    def _extract_python_dependencies(self, content: str) -> Set[str]:
        """
        Extract Python dependencies from import statements
        """
        dependencies = set()
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies.add(alias.name.split('.')[0])
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        dependencies.add(node.module.split('.')[0])
        
        except SyntaxError:
            # Parse imports manually for files with syntax errors
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('import '):
                    module = line.replace('import ', '').split(' as ')[0].split(',')[0].strip()
                    dependencies.add(module.split('.')[0])
                elif line.startswith('from '):
                    if ' import ' in line:
                        module = line.split(' import ')[0].replace('from ', '').strip()
                        if module and not module.startswith('.'):
                            dependencies.add(module.split('.')[0])
        
        except Exception as e:
            logger.warning(f"Error extracting Python dependencies: {str(e)}")
        
        return dependencies
    
    def _extract_js_dependencies(self, content: str) -> Set[str]:
        """
        Extract JavaScript/TypeScript dependencies
        """
        dependencies = set()
        
        try:
            import_patterns = [
                r'import.*from\s+["\']([^"\']+)["\']',
                r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
                r'import\s*\(\s*["\']([^"\']+)["\']\s*\)',
            ]
            
            import re
            for pattern in import_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # Remove relative path indicators and get base module
                    clean_dep = match.replace('./', '').replace('../', '').split('/')[0]
                    if clean_dep and not clean_dep.startswith('.'):
                        dependencies.add(clean_dep)
        
        except Exception as e:
            logger.warning(f"Error extracting JS dependencies: {str(e)}")
        
        return dependencies
    
    async def _detect_breaking_changes(self, changed_files: List[Dict], graph: nx.DiGraph) -> List[str]:
        """
        Detect breaking changes that might affect dependent modules
        """
        issues = []
        
        try:
            for file_data in changed_files:
                filename = file_data["filename"]
                content = file_data["content"]
                patch = file_data.get("patch", "")
                
                # Analyze removed functions/classes
                removed_functions = self._find_removed_functions(patch)
                for func_name in removed_functions:
                    # Check if other files depend on this file
                    dependents = [n for n in graph.nodes() if graph.has_edge(n, filename.replace('.py', ''))]
                    if dependents:
                        issues.append(f"BREAKING: Function '{func_name}' removed from {filename}, affects: {', '.join(dependents)}")
                
                # Check for signature changes
                signature_changes = self._detect_signature_changes(patch)
                for change in signature_changes:
                    issues.append(f"BREAKING: {filename}: {change}")
                
                # Check for renamed functions/classes
                renamed_items = self._detect_renamed_items(patch)
                for old_name, new_name in renamed_items:
                    issues.append(f"BREAKING: {filename}: '{old_name}' renamed to '{new_name}' - may break imports")
        
        except Exception as e:
            logger.warning(f"Error detecting breaking changes: {str(e)}")
        
        return issues
    
    async def _detect_circular_dependencies(self, graph: nx.DiGraph) -> List[str]:
        """
        Detect circular dependencies in the dependency graph
        """
        issues = []
        
        try:
            # Find strongly connected components (cycles)
            cycles = list(nx.simple_cycles(graph))
            
            for cycle in cycles:
                if len(cycle) > 1:
                    cycle_str = " -> ".join(cycle + [cycle[0]])
                    issues.append(f"CIRCULAR DEPENDENCY: {cycle_str}")
        
        except Exception as e:
            logger.warning(f"Error detecting circular dependencies: {str(e)}")
        
        return issues
    
    async def _detect_dependency_conflicts(self, changed_files: List[Dict]) -> List[str]:
        """
        Detect dependency version conflicts
        """
        issues = []
        
        try:
            requirement_files = [f for f in changed_files if f["filename"] in 
                               ['requirements.txt', 'package.json', 'Pipfile', 'pom.xml']]
            
            for file_data in requirement_files:
                filename = file_data["filename"]
                content = file_data["content"]
                patch = file_data.get("patch", "")
                
                # Check for version conflicts in requirements
                if filename == 'requirements.txt':
                    issues.extend(self._check_python_version_conflicts(content, patch))
                elif filename == 'package.json':
                    issues.extend(self._check_npm_version_conflicts(content, patch))
        
        except Exception as e:
            logger.warning(f"Error detecting dependency conflicts: {str(e)}")
        
        return issues
    
    async def _detect_unused_dependencies(self, changed_files: List[Dict]) -> List[str]:
        """
        Detect unused imports and dependencies
        """
        issues = []
        
        try:
            for file_data in changed_files:
                filename = file_data["filename"]
                content = file_data["content"]
                
                if filename.endswith('.py'):
                    unused = self._find_unused_python_imports(content)
                    for imp in unused:
                        issues.append(f"UNUSED: {filename}: Unused import '{imp}'")
        
        except Exception as e:
            logger.warning(f"Error detecting unused dependencies: {str(e)}")
        
        return issues
    
    def _find_removed_functions(self, patch: str) -> List[str]:
        """
        Find function names that were removed based on patch
        """
        removed_functions = []
        
        try:
            import re
            # Look for removed function definitions
            removed_lines = [line for line in patch.split('\n') if line.startswith('-')]
            
            for line in removed_lines:
                # Python function
                func_match = re.search(r'-\s*def\s+(\w+)\s*\(', line)
                if func_match:
                    removed_functions.append(func_match.group(1))
                
                # JavaScript function
                js_func_match = re.search(r'-\s*function\s+(\w+)\s*\(', line)
                if js_func_match:
                    removed_functions.append(js_func_match.group(1))
        
        except Exception as e:
            logger.warning(f"Error finding removed functions: {str(e)}")
        
        return removed_functions
    
    def _detect_signature_changes(self, patch: str) -> List[str]:
        """
        Detect function signature changes
        """
        changes = []
        
        try:
            import re
            lines = patch.split('\n')
            
            for i, line in enumerate(lines):
                if line.startswith('-') and 'def ' in line:
                    # Look for the corresponding added line
                    for j in range(i+1, min(i+5, len(lines))):
                        if lines[j].startswith('+') and 'def ' in lines[j]:
                            old_func = re.search(r'def\s+(\w+)\s*\([^)]*\)', line)
                            new_func = re.search(r'def\s+(\w+)\s*\([^)]*\)', lines[j])
                            
                            if old_func and new_func and old_func.group(1) == new_func.group(1):
                                old_sig = old_func.group(0)
                                new_sig = new_func.group(0)
                                if old_sig != new_sig:
                                    changes.append(f"Function '{old_func.group(1)}' signature changed")
                            break
        
        except Exception as e:
            logger.warning(f"Error detecting signature changes: {str(e)}")
        
        return changes
    
    def _detect_renamed_items(self, patch: str) -> List[Tuple[str, str]]:
        """
        Detect renamed functions/classes
        """
        renamed = []
        
        try:
            import re
            lines = patch.split('\n')
            removed_items = []
            added_items = []
            
            for line in lines:
                if line.startswith('-'):
                    # Find removed functions/classes
                    func_match = re.search(r'def\s+(\w+)', line)
                    class_match = re.search(r'class\s+(\w+)', line)
                    if func_match:
                        removed_items.append(func_match.group(1))
                    elif class_match:
                        removed_items.append(class_match.group(1))
                
                elif line.startswith('+'):
                    # Find added functions/classes
                    func_match = re.search(r'def\s+(\w+)', line)
                    class_match = re.search(r'class\s+(\w+)', line)
                    if func_match:
                        added_items.append(func_match.group(1))
                    elif class_match:
                        added_items.append(class_match.group(1))
            
            # Simple heuristic: if similar names exist in both lists
            for removed in removed_items:
                for added in added_items:
                    if self._are_likely_renamed(removed, added):
                        renamed.append((removed, added))
        
        except Exception as e:
            logger.warning(f"Error detecting renamed items: {str(e)}")
        
        return renamed
    
    def _are_likely_renamed(self, old_name: str, new_name: str) -> bool:
        """
        Heuristic to determine if two names represent a rename
        """
        # Simple similarity check
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, old_name.lower(), new_name.lower()).ratio()
        return similarity > 0.7 and old_name != new_name
    
    def _check_python_version_conflicts(self, content: str, patch: str) -> List[str]:
        """
        Check for Python package version conflicts
        """
        issues = []
        
        try:
            import re
            lines = content.split('\n')
            packages = {}
            
            for line in lines:
                line = line.strip()
                if '==' in line:
                    match = re.match(r'([^=<>!]+)[=<>!]+([0-9.]+)', line)
                    if match:
                        pkg_name, version = match.groups()
                        pkg_name = pkg_name.strip()
                        if pkg_name in packages and packages[pkg_name] != version:
                            issues.append(f"VERSION CONFLICT: {pkg_name} specified as both {packages[pkg_name]} and {version}")
                        packages[pkg_name] = version
        
        except Exception as e:
            logger.warning(f"Error checking Python version conflicts: {str(e)}")
        
        return issues
    
    def _check_npm_version_conflicts(self, content: str, patch: str) -> List[str]:
        """
        Check for NPM package version conflicts
        """
        issues = []
        
        try:
            import json
            data = json.loads(content)
            
            dependencies = data.get('dependencies', {})
            dev_dependencies = data.get('devDependencies', {})
            
            # Check for conflicting versions between deps and devDeps
            for pkg_name in set(dependencies.keys()) & set(dev_dependencies.keys()):
                if dependencies[pkg_name] != dev_dependencies[pkg_name]:
                    issues.append(f"VERSION CONFLICT: {pkg_name} has different versions in dependencies and devDependencies")
        
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Error checking NPM version conflicts: {str(e)}")
        
        return issues
    
    def _find_unused_python_imports(self, content: str) -> List[str]:
        """
        Find unused Python imports
        """
        unused = []
        
        try:
            tree = ast.parse(content)
            imported_names = set()
            used_names = set()
            
            # Collect imported names
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name.split('.')[0]
                        imported_names.add(name)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imported_names.add(name)
            
            # Collect used names
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    used_names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    # Get the root name of attribute access
                    current = node
                    while isinstance(current, ast.Attribute):
                        current = current.value
                    if isinstance(current, ast.Name):
                        used_names.add(current.id)
            
            # Find unused imports
            unused = list(imported_names - used_names)
        
        except (SyntaxError, Exception) as e:
            logger.warning(f"Error finding unused imports: {str(e)}")
        
        return unused