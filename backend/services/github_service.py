import re
import httpx
from typing import Dict, List, Optional
import base64
import logging

logger = logging.getLogger(__name__)

class GitHubService:
    """
    Service to interact with GitHub API and fetch PR data
    """
    
    def __init__(self):
        self.base_url = "https://api.github.com"
        
    async def fetch_pr_data(self, pr_url: str, token: str) -> Dict:
        """
                Fetch PR data returning ONLY what reviewers need:
                {
                    title: str,
                    pr_url: str,
                    files: [
                        {
                            filename: str,
                            changes: [
                                { type: 'added', line: int, new_code: str } |
                                { type: 'removed', line: int, old_code: str } |
                                { type: 'modified', old_line: int, new_line: int, old_code: str, new_code: str }
                            ]
                        }
                    ]
                }
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get PR details
            pr_response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers
            )
            
            if pr_response.status_code != 200:
                raise Exception(f"Failed to fetch PR: {pr_response.status_code}")
            
            pr_info = pr_response.json()
            
            # Get changed files (GitHub returns patch + metadata)
            files_response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=headers
            )
            if files_response.status_code != 200:
                raise Exception(f"Failed to fetch PR files: {files_response.status_code}")
            gh_files = files_response.json()

            processed_files: List[Dict] = []
            for file_info in gh_files:
                filename = file_info.get("filename")
                status = file_info.get("status")  # added, modified, removed, renamed
                patch = file_info.get("patch")  # may be None for binary / large files

                # Skip binary or unsupported (no patch)
                if not patch:
                    logger.info(f"Skipping file without textual patch: {filename}")
                    continue

                parsed = self._extract_changes_v2(patch)

                # Build unified change list
                unified_changes: List[Dict] = []

                # Pure additions
                for a in parsed["added_lines"]:
                    unified_changes.append({
                        "type": "added",
                        "line": a["line_number"],
                        "new_code": a["content"]
                    })
                # Pure deletions
                for d in parsed["removed_lines"]:
                    unified_changes.append({
                        "type": "removed",
                        "line": d["line_number"],
                        "old_code": d["content"]
                    })
                # Modifications
                for m in parsed["modified_lines"]:
                    unified_changes.append({
                        "type": "modified",
                        "old_line": m.get("old_line_number", m.get("line_number")),
                        "new_line": m.get("new_line_number", m.get("line_number")),
                        "old_code": m["old_content"],
                        "new_code": m["new_content"]
                    })

                if not unified_changes:
                    continue

                processed_files.append({
                    "filename": filename,
                    "changes": unified_changes
                })

            return {
                "title": pr_info.get("title", ""),
                "pr_url": pr_url,
                "files": processed_files
            }
    
    async def _fetch_file_content(
        self, 
        owner: str, 
        repo: str, 
        filepath: str, 
        sha: str, 
        headers: Dict, 
        client: httpx.AsyncClient
    ) -> Optional[str]:
        """
        Fetch file content from GitHub
        """
        try:
            response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}/contents/{filepath}?ref={sha}",
                headers=headers
            )
            
            if response.status_code == 200:
                file_data = response.json()
                if file_data.get("encoding") == "base64":
                    content = base64.b64decode(file_data["content"]).decode("utf-8")
                    return content
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to fetch file {filepath}: {str(e)}")
            return None
    
    def _parse_pr_url(self, pr_url: str) -> tuple:
        """
        Parse GitHub PR URL to extract owner, repo, and PR number
        Examples:
        - https://github.com/owner/repo/pull/123
        - https://github.com/owner/repo/pulls/123
        """
        pattern = r"github\.com/([^/]+)/([^/]+)/pulls?/(\d+)"
        match = re.search(pattern, pr_url)
        
        if not match:
            raise ValueError(f"Invalid GitHub PR URL format: {pr_url}")
        
        return match.groups()
    
    def _extract_changed_lines(self, patch: str) -> Dict:
        """
        Extract only the changed lines from a GitHub patch
        Returns dict with added_lines, removed_lines, and context
        """
        if not patch:
            return {"added_lines": [], "removed_lines": [], "modified_lines": [], "context": []}
        
        added_lines = []
        removed_lines = []
        modified_lines = []
        context_lines = []
        current_line_number = 0
        
        try:
            lines = patch.split('\n')
            
            for line in lines:
                # Parse hunk header to get line numbers
                if line.startswith('@@'):
                    # Extract starting line number from hunk header
                    # Format: @@ -old_start,old_count +new_start,new_count @@
                    import re
                    match = re.search(r'\+(\d+)', line)
                    if match:
                        current_line_number = int(match.group(1)) - 1
                    continue
                
                current_line_number += 1
                
                if line.startswith('+') and not line.startswith('+++'):
                    # Added line
                    added_lines.append({
                        "line_number": current_line_number,
                        "content": line[1:],  # Remove + prefix
                        "type": "addition"
                    })
                elif line.startswith('-') and not line.startswith('---'):
                    # Removed line  
                    removed_lines.append({
                        "line_number": current_line_number - 1,  # Removed lines don't increment new line count
                        "content": line[1:],  # Remove - prefix
                        "type": "deletion"
                    })
                    current_line_number -= 1  # Don't count removed lines in new file
                elif line.startswith(' '):
                    # Context line (unchanged)
                    context_lines.append({
                        "line_number": current_line_number,
                        "content": line[1:],  # Remove space prefix
                        "type": "context"
                    })
            
            # Identify modified lines (removed + added in same area)
            for removed in removed_lines:
                for added in added_lines:
                    if abs(removed["line_number"] - added["line_number"]) <= 2:
                        modified_lines.append({
                            "line_number": added["line_number"],
                            "old_content": removed["content"],
                            "new_content": added["content"],
                            "type": "modification"
                        })
        
        except Exception as e:
            logger.warning(f"Error parsing patch: {str(e)}")
        
        return {
            "added_lines": added_lines,
            "removed_lines": removed_lines, 
            "modified_lines": modified_lines,
            "context": context_lines
        }
    
    def _extract_changes_v2(self, patch: str) -> Dict:
        """Robust patch parser producing precise added/removed/modified line info.

        Algorithm:
        - Parse each hunk header to establish old/new starting line numbers
        - Track contiguous change blocks (sequences of '+'/'-' lines without context)
        - For each block: if both additions & deletions exist => pair as modifications (line-wise)
          remaining unmatched additions / deletions kept as pure adds/removals
        - Provide old & new line numbers for modifications.
        """
        if not patch:
            return {"added_lines": [], "removed_lines": [], "modified_lines": [], "context": []}

        added: List[Dict] = []
        removed: List[Dict] = []
        modified: List[Dict] = []
        context: List[Dict] = []

        current_old = 0
        current_new = 0
        block: List[Dict] = []  # each entry: {kind: 'add'|'del', line_no: int, content: str}

        def flush_block():
            nonlocal block
            if not block:
                return
            dels = [b for b in block if b['kind'] == 'del']
            adds = [b for b in block if b['kind'] == 'add']
            # Pair for modifications
            pair_count = min(len(dels), len(adds))
            for i in range(pair_count):
                d = dels[i]
                a = adds[i]
                modified.append({
                    "old_line_number": d['line_no'],
                    "new_line_number": a['line_no'],
                    "old_content": d['content'],
                    "new_content": a['content'],
                    "type": "modification"
                })
            # Remaining additions
            for a in adds[pair_count:]:
                added.append({
                    "line_number": a['line_no'],
                    "content": a['content'],
                    "type": "addition"
                })
            # Remaining deletions
            for d in dels[pair_count:]:
                removed.append({
                    "line_number": d['line_no'],
                    "content": d['content'],
                    "type": "deletion"
                })
            block = []

        hunk_header_re = re.compile(r'^@@ -(?P<o_start>\d+)(?:,(?P<o_count>\d+))? \+(?P<n_start>\d+)(?:,(?P<n_count>\d+))? @@')

        for raw_line in patch.split('\n'):
            if raw_line.startswith('@@'):
                # Flush any pending block on new hunk
                flush_block()
                m = hunk_header_re.match(raw_line)
                if m:
                    current_old = int(m.group('o_start'))
                    current_new = int(m.group('n_start'))
                continue
            if raw_line.startswith('+') and not raw_line.startswith('+++'):
                block.append({
                    'kind': 'add',
                    'line_no': current_new,
                    'content': raw_line[1:]
                })
                current_new += 1
                continue
            if raw_line.startswith('-') and not raw_line.startswith('---'):
                block.append({
                    'kind': 'del',
                    'line_no': current_old,
                    'content': raw_line[1:]
                })
                current_old += 1
                continue
            if raw_line.startswith(' '):
                # Encounter context => flush previous change block
                flush_block()
                context.append({
                    'line_number': current_new if current_new else current_old,
                    'content': raw_line[1:],
                    'type': 'context'
                })
                current_old += 1
                current_new += 1
                continue
            # Any other line (e.g., \ No newline at end of file)
            flush_block()
        # Flush final block
        flush_block()

        return {
            "added_lines": added,
            "removed_lines": removed,
            "modified_lines": modified,
            "context": context
        }
        """
        Filter files that are relevant for code review
        """
        relevant_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.kt', '.swift', '.scala',
            '.html', '.css', '.scss', '.sass', '.vue', '.svelte'
        }
        
        filtered_files = []
        for file in files:
            filename = file["filename"].lower()
            
            # Skip certain files
            if any(skip in filename for skip in [
                'node_modules/', '.git/', 'dist/', 'build/', 'coverage/',
                '.min.', 'bundle.', 'vendor/', 'third_party/'
            ]):
                continue
            
            # Include files with relevant extensions
            if any(filename.endswith(ext) for ext in relevant_extensions):
                filtered_files.append(file)
            
            # Include certain config files
            elif any(name in filename for name in [
                'dockerfile', 'requirements.txt', 'package.json', 
                'pom.xml', 'build.gradle', '.env'
            ]):
                filtered_files.append(file)
        
        return filtered_files