# 🤖 AutoPR: AI-Powered Code Review System

Complete deployment and CI/CD integration guide for the AutoPR AI code review system.

## 🎯 Quick Start (Free Deployment)

### Option 1: GitHub Actions (Recommended - 100% Free)

1. **Setup Repository Secrets**:
   - Go to your repo → Settings → Secrets and variables → Actions
   - Add secrets:
     - `GROQ_API_KEY`: Your Groq API key
     - `GITHUB_TOKEN`: Auto-provided by GitHub Actions (no setup needed)

2. **Enable Workflow**:
   ```bash
   # Copy the workflow file (already created)
   cp .github/workflows/ai-pr-review.yml .github/workflows/
   git add .github/workflows/ai-pr-review.yml
   git commit -m "Add AI PR review workflow"
   git push
   ```

3. **Test**:
   - Create a test PR with some code changes
   - Watch the "AI PR Review" check run automatically
   - Review the detailed comment posted on your PR

### Option 2: Fly.io Deployment (Free Tier)

1. **Install Fly CLI**:
   ```bash
   # macOS/Linux
   curl -L https://fly.io/install.sh | sh
   
   # Windows (PowerShell)
   powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```

2. **Login and Deploy**:
   ```bash
   flyctl auth login
   export GROQ_API_KEY="your_groq_key_here"
   export GITHUB_TOKEN="your_github_token_here"  # optional
   chmod +x deploy-fly.sh
   ./deploy-fly.sh
   ```

3. **Use in CI/CD**: Call your deployed API at `https://autopr-backend.fly.dev/review-pr`

## 📋 Prerequisites

### Required
- Python 3.11+
- GitHub Personal Access Token (classic, `repo` scope)
- Groq API Key (free trial available)

### Optional
- Docker (for containerized deployment)
- Jenkins (for self-hosted CI/CD)
- GitLab account (for GitLab CI)

## 🔧 Installation & Setup

### 1. Clone and Setup Backend
```bash
git clone <your-repo>
cd autopr-system/backend

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY="your_groq_key"
export GITHUB_TOKEN="your_github_token"

# Test locally
python scripts/run_review.py --pr-url "https://github.com/owner/repo/pull/123" --github-token "$GITHUB_TOKEN" --output test-review.json
```

### 2. Verify Installation
```bash
# Start FastAPI server (optional)
uvicorn main:app --reload

# Health check
curl http://localhost:8000/health

# Test endpoint
curl -X POST http://localhost:8000/review-pr \
  -H "Content-Type: application/json" \
  -d '{"pr_url":"https://github.com/owner/repo/pull/123","github_token":"your_token"}'
```

## 🚀 Deployment Options

### 1. GitHub Actions (Free - Recommended)

**Features**:
- ✅ Completely free for public repos
- ✅ 2000 minutes/month for private repos
- ✅ Automatic PR comments
- ✅ Status checks
- ✅ Artifact storage

**Setup**: Already configured in `.github/workflows/ai-pr-review.yml`

**Customization**:
```yaml
# Adjust agents in the workflow
- name: Run AI Code Review
  run: |
    python scripts/run_review.py \
      --agents "security,bug_detection" \  # Only run specific agents
      --max-lines 500 \                   # Skip large PRs
      --no-llm                            # Heuristics only
```

### 2. Fly.io (Free Tier)

**Features**:
- ✅ 3 shared-cpu-1x 256MB VMs free
- ✅ Auto-sleep when idle
- ✅ HTTPS included
- ✅ Global edge network

**Deploy**:
```bash
./deploy-fly.sh
```

**Environment Variables**:
```bash
flyctl secrets set GROQ_API_KEY="your_key" --app autopr-backend
flyctl secrets set GITHUB_TOKEN="your_token" --app autopr-backend
```

### 3. Docker (Self-Hosted)

```bash
# Build image
docker build -t autopr-backend .

# Run with environment variables
docker run -d \
  --name autopr \
  -p 8000:8000 \
  -e GROQ_API_KEY="your_key" \
  -e GITHUB_TOKEN="your_token" \
  autopr-backend

# Or use docker-compose
echo "GROQ_API_KEY=your_key" > .env
echo "GITHUB_TOKEN=your_token" >> .env
docker-compose up -d
```

## 🔄 CI/CD Integration

### GitHub Actions (Detailed)

The provided workflow (`.github/workflows/ai-pr-review.yml`) includes:

- **Trigger**: Runs on PR open/update
- **Analysis**: Full AI review with all agents
- **Comments**: Posts detailed results to PR
- **Status Checks**: Sets GitHub check status
- **Artifacts**: Stores JSON results
- **Failure Policy**: Fails on critical issues

**Customization Examples**:
```yaml
# Security-focused review only
--agents "security"

# Skip LLM for faster runs
--no-llm

# Size limits
--max-lines 1000
```

### GitLab CI

Use the provided `.gitlab-ci.yml`:

**Setup Variables** (Settings → CI/CD → Variables):
- `GROQ_API_KEY`: Your Groq key
- `GITHUB_TOKEN`: GitHub token (if analyzing GitHub PRs)

**Features**:
- Runs on merge requests
- Caches Python dependencies
- Fails pipeline on critical issues
- Stores review artifacts

### Jenkins

Use the provided `Jenkinsfile`:

**Setup Credentials**:
- `github-pat`: GitHub Personal Access Token
- `groq-api-key`: Groq API Key

**Features**:
- Multibranch pipeline support
- Python virtual environment caching
- Build status based on severity
- Artifact archival

### Bitbucket Pipelines

```yaml
# bitbucket-pipelines.yml
image: python:3.11

pipelines:
  pull-requests:
    '**':
      - step:
          name: AI Code Review
          caches:
            - pip
          script:
            - cd backend
            - pip install -r requirements.txt
            - python scripts/run_review.py --pr-url "$BITBUCKET_GIT_HTTP_ORIGIN/pull-requests/$BITBUCKET_PR_ID" --github-token "$GITHUB_TOKEN" --output review.json
            - python -c "import json,sys; r=json.load(open('review.json')); sys.exit(1 if any(c.get('severity','').lower() in ('critical','error') for c in r.get('comments',[])) else 0)"
          artifacts:
            - review.json
```

## ⚙️ Configuration Options

### Environment Variables

```bash
# Required
GROQ_API_KEY=your_groq_api_key
GITHUB_TOKEN=your_github_token

# Optional
CREW_AI_ENABLED=false                    # Enable CrewAI orchestration
AUTO_PR_ENABLED_AGENTS=security,bugs    # Comma-separated agent list
USE_LLM=true                            # Enable/disable LLM features
MAX_PR_SIZE=1000                        # Skip large PRs
```

### Command Line Options

```bash
python scripts/run_review.py \
  --pr-url "https://github.com/owner/repo/pull/123" \
  --github-token "ghp_xxxx" \
  --output review.json \
  --agents "security,bug_detection,code_quality" \
  --max-lines 500 \
  --no-llm \
  --verbose
```

### Agent Selection

**Available Agents**:
- `code_quality`: Style, formatting, maintainability
- `bug_detection`: Logic errors, runtime issues
- `security`: Vulnerabilities, secrets, injection
- `dependency`: Breaking changes, imports
- `documentation`: Missing docs, comments

**Examples**:
```bash
# Security audit only
--agents "security"

# Core review (no docs)
--agents "code_quality,bug_detection,security"

# Full review
--agents "code_quality,bug_detection,security,dependency,documentation"
```

## 📊 Understanding Results

### Output Format

```json
{
  "summary": "🤖 AI Review Complete: 3 issues found - Needs Changes",
  "final_status": "Needs Changes",  // Approve | Needs Changes | Reject
  "timestamp": "2025-01-01T12:00:00Z",
  "pr_info": {
    "title": "Add new feature",
    "author": "developer",
    "files_changed": 5
  },
  "execution_time": 15.2,
  "comments": [
    {
      "file": "src/app.py",
      "line": 42,
      "message": "Hardcoded secret detected",
      "severity": "critical",
      "type": "hardcoded-secret",
      "suggestion": "Move to environment variable",
      "source_agent": "Security"
    }
  ],
  "total_changes": 150,
  "agents_used": ["security", "bug_detection"],
  "llm_enabled": true
}
```

### Severity Levels

- **Critical/Error**: Blocks merge, fails CI
- **High/Warning**: Should fix, may fail CI
- **Medium**: Consider fixing
- **Low/Info**: Optional improvements

### Exit Codes (CI/CD)

- `0`: Success (no blocking issues)
- `1`: Critical/error issues found
- `2`: High/warning issues found

## 🛠️ Troubleshooting

### Common Issues

1. **"No review.json found"**
   ```bash
   # Check GROQ_API_KEY is set
   echo $GROQ_API_KEY
   
   # Run with --verbose flag
   python scripts/run_review.py --verbose ...
   
   # Check logs for errors
   ```

2. **"GitHub API rate limit"**
   ```bash
   # Use authenticated token
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
   
   # Wait or use different token
   ```

3. **"Groq API failures"**
   ```bash
   # Run without LLM
   python scripts/run_review.py --no-llm ...
   
   # Check API key validity
   curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models
   ```

4. **"Large PR timeout"**
   ```bash
   # Set size limit
   --max-lines 500
   
   # Use specific agents only
   --agents "security,bug_detection"
   ```

### Debug Mode

```bash
# Enable verbose logging
python scripts/run_review.py --verbose ...

# Check FastAPI logs
uvicorn main:app --log-level debug

# Docker logs
docker logs autopr
```

## 🔒 Security Considerations

1. **Token Security**:
   - Use fine-grained GitHub tokens when possible
   - Store tokens in CI secrets, never in code
   - Rotate tokens regularly

2. **API Keys**:
   - Monitor Groq API usage
   - Set usage alerts
   - Use different keys for different environments

3. **Network Security**:
   - Use HTTPS endpoints only
   - Validate webhook signatures (future enhancement)
   - Rate limit API calls

## 📈 Monitoring & Observability

### Metrics to Track

- Review completion rate
- Average analysis time
- Issue detection accuracy
- False positive rate
- API usage costs

### Logging

```python
# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Custom log format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
```

### Health Checks

```bash
# Application health
curl https://your-app.fly.dev/health

# Detailed status
curl https://your-app.fly.dev/

# Fly.io monitoring
flyctl status --app autopr-backend
flyctl logs --app autopr-backend
```

## 🚧 Future Enhancements

1. **GitHub Integration**:
   - Inline PR comments
   - Review submissions
   - Status check integration

2. **Performance**:
   - Batch LLM calls
   - Response caching
   - Parallel file processing

3. **Features**:
   - Custom rule configuration
   - Historical trend analysis
   - Team-specific agent profiles

4. **Integrations**:
   - Slack notifications
   - JIRA ticket creation
   - Metrics dashboard

## 📝 License

MIT License - Feel free to use and modify for your projects.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests (future)
5. Submit a pull request

---

**Questions?** Open an issue or check the troubleshooting section above.