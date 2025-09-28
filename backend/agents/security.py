import re
import subprocess
import tempfile
import os
from typing import Dict, List
import logging
from services.groq_service import GroqService

logger = logging.getLogger(__name__)

class SecurityAgent:
    """
    Agent responsible for detecting security vulnerabilities
    """
    
    def __init__(self, groq_service: GroqService):
        self.groq_service = groq_service
        self.name = "Security"
        
        # Common security patterns
        self.security_patterns = {
            'hardcoded_secrets': [
                r'password\s*=\s*["\'][^"\']{6,}["\']',
                r'api[_-]?key\s*=\s*["\'][^"\']{10,}["\']',
                r'secret\s*=\s*["\'][^"\']{8,}["\']',
                r'token\s*=\s*["\'][^"\']{16,}["\']',
            ],
            'sql_injection': [
                r'execute\s*\(\s*["\'].*%s.*["\']',
                r'query\s*\(\s*["\'].*\+.*["\']',
                r'SELECT.*\+.*FROM',
                r'INSERT.*\+.*INTO',
            ],
            'weak_crypto': [
                r'hashlib\.md5\(',
                r'hashlib\.sha1\(',
                r'DES\(',
                r'RC4\(',
            ],
            'xss_vulnerabilities': [
                r'innerHTML\s*=\s*.*\+',
                r'document\.write\s*\(',
                r'eval\s*\(',
                r'dangerouslySetInnerHTML',
            ],
            'path_traversal': [
                r'open\s*\(\s*.*\+.*["\']',
                r'file\s*=\s*.*\+.*["\']',
                r'path\s*=\s*.*\+.*["\']',
            ]
        }
    
    async def analyze(self, pr_data: Dict) -> List[Dict]:
        """
        Analyze security vulnerabilities in changed lines only
        """
        review_comments = []
        
        try:
            for file_data in pr_data.get("files", []):
                filename = file_data.get("filename")
                changes = file_data.get("changes", [])

                if not changes:
                    continue

                logger.info(f"Analyzing security for changes in: {filename}")

                pattern_issues = await self._detect_security_in_changes(filename, changes)
                for issue in pattern_issues:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(pattern_issues)

                llm_comments = await self.groq_service.analyze_security(changes, filename)
                for issue in llm_comments:
                    issue.setdefault("file", filename)
                    issue.setdefault("source_agent", self.name)
                review_comments.extend(llm_comments)
        
        except Exception as e:
            logger.error(f"Error in security analysis: {str(e)}")
            review_comments.append({
                "line": 0,
                "message": f"Error analyzing security: {str(e)}",
                "severity": "error",
                "type": "analysis-error"
            })
        
        return review_comments

    async def _detect_security_in_changes(self, filename: str, changes: List[Dict]) -> List[Dict]:
        """
        Detect security vulnerabilities in changed lines only
        """
        issues = []
        
        try:
            for change in changes:
                ctype = change.get("type")
                if ctype == "added":
                    issues.extend(self._check_line_security(filename, change.get("line"), change.get("new_code", "")))
                elif ctype == "modified":
                    issues.extend(self._check_line_security(filename, change.get("new_line"), change.get("new_code", "")))
                elif ctype == "removed":
                    # Sometimes removed code can indicate a resolved issue; optionally could analyze old_code
                    pass
        
        except Exception as e:
            logger.warning(f"Security pattern detection failed for {filename}: {str(e)}")
        
        return issues

    def _check_line_security(self, filename: str, line_number: int, content: str) -> List[Dict]:
        """
        Check individual line for security issues
        """
        issues = []
        
        try:
            import re
            
            # Check for hardcoded secrets
            secret_patterns = [
                (r'password\s*=\s*["\'][^"\']{6,}["\']', "hardcoded-password"),
                (r'api[_-]?key\s*=\s*["\'][^"\']{10,}["\']', "hardcoded-api-key"),
                (r'secret\s*=\s*["\'][^"\']{8,}["\']', "hardcoded-secret"),
                (r'token\s*=\s*["\'][^"\']{16,}["\']', "hardcoded-token"),
            ]
            
            for pattern, vuln_type in secret_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append({
                        "line": line_number,
                        "message": f"Hardcoded secret detected: {vuln_type}",
                        "severity": "critical",
                        "type": vuln_type,
                        "suggestion": "Move to environment variable or config file",
                        "file": filename,
                        "source_agent": self.name
                    })
            
            # Check for weak crypto
            if re.search(r'hashlib\.(md5|sha1)\(', content):
                issues.append({
                    "line": line_number,
                    "message": "Weak cryptographic hash function",
                    "severity": "medium",
                    "type": "weak-crypto",
                    "suggestion": "Use SHA-256 or better",
                    "file": filename,
                    "source_agent": self.name
                })
            
            # Check for SQL injection patterns
            if re.search(r'execute\s*\(\s*["\'].*%s.*["\']', content, re.IGNORECASE):
                issues.append({
                    "line": line_number,
                    "message": "Potential SQL injection vulnerability",
                    "severity": "high",
                    "type": "sql-injection",
                    "suggestion": "Use parameterized queries",
                    "file": filename,
                    "source_agent": self.name
                })
            
            # Check for eval usage
            if 'eval(' in content.lower():
                issues.append({
                    "line": line_number,
                    "message": "Dynamic code execution detected - potential code injection",
                    "severity": "high",
                    "type": "code-injection",
                    "suggestion": "Avoid eval(), use safer alternatives",
                    "file": filename,
                    "source_agent": self.name
                })
        
        except Exception as e:
            logger.warning(f"Line security check failed: {str(e)}")
        
        return issues
    
    async def _detect_security_patterns(self, filename: str, content: str) -> List[str]:
        """
        Detect security vulnerabilities using regex patterns
        """
        issues = []
        lines = content.split('\n')
        
        try:
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                
                # Check for hardcoded secrets
                for pattern in self.security_patterns['hardcoded_secrets']:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"HIGH: {filename}:Line {i}: Hardcoded secret detected")
                
                # Check for SQL injection vulnerabilities
                for pattern in self.security_patterns['sql_injection']:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"HIGH: {filename}:Line {i}: Potential SQL injection vulnerability")
                
                # Check for weak cryptographic functions
                for pattern in self.security_patterns['weak_crypto']:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"MEDIUM: {filename}:Line {i}: Weak cryptographic function detected")
                
                # Check for XSS vulnerabilities
                for pattern in self.security_patterns['xss_vulnerabilities']:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"HIGH: {filename}:Line {i}: Potential XSS vulnerability")
                
                # Check for path traversal vulnerabilities
                for pattern in self.security_patterns['path_traversal']:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"MEDIUM: {filename}:Line {i}: Potential path traversal vulnerability")
                
                # Additional specific checks
                if 'exec(' in line_lower or 'eval(' in line_lower:
                    issues.append(f"HIGH: {filename}:Line {i}: Dynamic code execution detected - potential code injection")
                
                if 'shell=true' in line_lower or 'shell=True' in line:
                    issues.append(f"MEDIUM: {filename}:Line {i}: Shell execution enabled - potential command injection")
                
                if 'verify=false' in line_lower or 'verify=False' in line:
                    issues.append(f"MEDIUM: {filename}:Line {i}: SSL verification disabled")
                
                # Check for insecure random number generation
                if re.search(r'random\.(random|randint)', line):
                    issues.append(f"LOW: {filename}:Line {i}: Use secrets module for cryptographically secure random numbers")
                
                # Check for debug mode in production
                if 'debug=true' in line_lower or 'debug = True' in line:
                    issues.append(f"MEDIUM: {filename}:Line {i}: Debug mode enabled - should be disabled in production")
        
        except Exception as e:
            logger.warning(f"Security pattern detection failed for {filename}: {str(e)}")
        
        return issues
    
    async def _run_bandit_scan(self, filename: str, content: str) -> List[str]:
        """
        Run Bandit security scanner for Python files
        """
        issues = []
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            # Run bandit with JSON output
            result = subprocess.run([
                'python', '-m', 'bandit', 
                '-f', 'txt',
                '-l',  # Show only the line number
                temp_path
            ], capture_output=True, text=True, timeout=15)
            
            if result.stdout:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'Issue:' in line or 'Severity:' in line or filename in line:
                        # Clean up the bandit output
                        if line.strip():
                            formatted_line = line.replace(temp_path, filename)
                            issues.append(f"[Bandit] {formatted_line.strip()}")
            
            os.unlink(temp_path)
            
        except subprocess.TimeoutExpired:
            logger.warning("Bandit scan timed out")
        except FileNotFoundError:
            # Bandit not installed, skip
            logger.info("Bandit not available, skipping detailed security scan")
        except Exception as e:
            logger.warning(f"Bandit scan failed: {str(e)}")
        
        return issues
    
    def _check_dependency_vulnerabilities(self, filename: str, content: str) -> List[str]:
        """
        Check for known vulnerable dependencies
        """
        issues = []
        
        try:
            # Check for known vulnerable packages
            vulnerable_packages = {
                'requests': ['2.19.1', '2.20.0'],  # Example vulnerable versions
                'flask': ['0.12.0', '0.12.1'],
                'django': ['1.11.0', '1.11.1'],
            }
            
            if filename in ['requirements.txt', 'package.json', 'Pipfile']:
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    for package, vulnerable_versions in vulnerable_packages.items():
                        if package in line.lower():
                            # Extract version if specified
                            version_match = re.search(r'[=<>]+([0-9.]+)', line)
                            if version_match:
                                version = version_match.group(1)
                                if version in vulnerable_versions:
                                    issues.append(f"HIGH: {filename}:Line {i}: Vulnerable dependency {package} {version}")
        
        except Exception as e:
            logger.warning(f"Dependency vulnerability check failed: {str(e)}")
        
        return issues