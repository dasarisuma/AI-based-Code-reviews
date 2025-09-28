# AI Code Review Integration Guide

This document shows how to integrate the AutoPR AI code review agent across multiple CI/CD platforms using the enhanced `scripts/run_review.py`.

## Core Command

```bash
python scripts/run_review.py \
  --pr-url "https://github.com/owner/repo/pull/123" \
  --github-token "$GITHUB_TOKEN" \
  --agents "security,bug_detection,code_quality" \
  --max-lines 1200 \
  --fail-on critical,error \
  --output review.json
```

Or local diff mode (no PR API calls required):
```bash
git fetch origin main:refs/remotes/origin/main
python scripts/run_review.py \
  --base-ref origin/main \
  --head-ref HEAD \
  --local-diff \
  --agents security,bug_detection \
  --fail-on critical,error \
  --output review.json
```

Exit codes:
- 0: No blocking severities
- 1: A severity in `--fail-on` set was found (or critical/error in legacy mode)
- 2: High / warning present (only in tiered mode when not using `--single-exit-code`)

Add `--single-exit-code` to collapse non-blocking vs blocking into simple pass/fail.

## Configuration Precedence
1. CLI flags
2. Environment variables (UPPER_SNAKE_CASE of flag, e.g. `FAIL_ON`, `PR_URL`)
3. JSON config file via `--config path.json`

Example config file:
```json
{
  "agents": "security,bug_detection,code_quality",
  "max-lines": 1000,
  "fail-on": "critical,error",
  "no-llm": false
}
```
Run with:
```bash
python scripts/run_review.py --config ci-config.json --pr-url "..." --github-token "$GITHUB_TOKEN"
```

---
## GitHub Actions (Custom Inline)
If you want a minimal custom workflow instead of the provided one:
```yaml
name: AI Review (Minimal)

on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt
      - name: Run AI Review
        run: |
          python backend/scripts/run_review.py \
            --pr-url "${{ github.event.pull_request.html_url }}" \
            --github-token "${{ secrets.GITHUB_TOKEN }}" \
            --agents security,bug_detection,code_quality \
            --fail-on critical,error \
            --output review.json || true
      - name: Parse & Fail
        run: |
          python - <<'PY'
import json, sys
r=json.load(open('review.json'))
sev=[c.get('severity','').lower() for c in r.get('comments',[])]
if any(s in ('critical','error') for s in sev):
  print('Blocking issues present, failing build')
  sys.exit(1)
print('No blocking issues')
PY
```

---
## GitLab CI
```yaml
ai_review:
  stage: test
  image: python:3.11-slim
  variables:
    PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  cache:
    paths: [.cache/pip]
  script:
    - pip install -r backend/requirements.txt
    - python backend/scripts/run_review.py \
        --pr-url "$CI_PROJECT_URL/-/merge_requests/$CI_MERGE_REQUEST_IID" \
        --github-token "$GITHUB_TOKEN" \
        --fail-on critical,error \
        --output review.json || true
    - python - <<'PY'
import json,sys
r=json.load(open('review.json'))
sev=[c.get('severity','').lower() for c in r.get('comments',[])]
if any(s in ('critical','error') for s in sev):
  sys.exit(1)
PY
  artifacts:
    paths: [review.json]
  only: [merge_requests]
```

---
## Jenkins Pipeline Snippet (Declarative)
```groovy
stage('AI Review') {
  steps {
    sh '''
      python backend/scripts/run_review.py \
        --pr-url "${CHANGE_URL}" \
        --github-token "${GITHUB_TOKEN}" \
        --agents security,bug_detection,code_quality \
        --fail-on critical,error \
        --output backend/review.json || true
    '''
    script {
      if (fileExists('backend/review.json')) {
        def r = readJSON file: 'backend/review.json'
        def sev = r.comments.collect{ (it.severity?:'').toLowerCase() }
        if (sev.any{ it in ['critical','error'] }) {
          error("Blocking AI review issues")
        }
      }
    }
  }
}
```

---
## Bitbucket Pipelines
```yaml
image: python:3.11
pipelines:
  pull-requests:
    '**':
      - step:
          name: AI Review
          caches: [pip]
          script:
            - pip install -r backend/requirements.txt
            - python backend/scripts/run_review.py \
                --pr-url "$BITBUCKET_GIT_HTTP_ORIGIN/pull-requests/$BITBUCKET_PR_ID" \
                --github-token "$GITHUB_TOKEN" \
                --fail-on critical,error \
                --output review.json || true
            - python - <<'PY'
import json,sys
r=json.load(open('review.json'))
sev=[c.get('severity','').lower() for c in r.get('comments',[])]
if any(s in ('critical','error') for s in sev):
  sys.exit(1)
PY
          artifacts:
            - review.json
```

---
## Azure DevOps Pipeline
```yaml
jobs:
- job: ai_review
  pool: { vmImage: 'ubuntu-latest' }
  steps:
    - checkout: self
    - task: UsePythonVersion@0
      inputs: { versionSpec: '3.11' }
    - script: pip install -r backend/requirements.txt
      displayName: Install deps
    - script: |
        python backend/scripts/run_review.py \
          --pr-url "$(System.PullRequest.SourceRepositoryURI)/pull/$(System.PullRequest.PullRequestId)" \
          --github-token "$(GITHUB_TOKEN)" \
          --fail-on critical,error \
          --output review.json || true
      displayName: Run AI Review
    - script: |
        python - <<'PY'
import json,sys
r=json.load(open('review.json'))
sev=[c.get('severity','').lower() for c in r.get('comments',[])]
if any(s in ('critical','error') for s in sev):
  sys.exit(1)
PY
      displayName: Enforce policy
    - publish: review.json
      artifact: ai-review
```

---
## Local Pre-Push Hook Example
Add to `.git/hooks/pre-push`:
```bash
#!/bin/bash
python backend/scripts/run_review.py \
  --base-ref origin/main \
  --head-ref HEAD \
  --local-diff \
  --fail-on critical,error \
  --no-llm \
  --max-lines 400 \
  --output /tmp/local_review.json || true
jq '.summary' /tmp/local_review.json
```
Make executable:
```bash
chmod +x .git/hooks/pre-push
```

---
## Interpreting Results Programmatically
```python
import json
r = json.load(open('review.json'))
for c in r.get('comments', []):
    print(f"{c['file']}:{c['line']} [{c['severity']}] {c['message']}")
```

---
## Tips
- Use `--no-llm` for faster, cost-free heuristic-only checks in pre-push hooks.
- Use selective agents in early pipeline stages, full set later: `--agents security,bug_detection`.
- Pair with caching (pip cache, container layers) to reduce runtime.
- Combine with a summary comment bot on platforms without native PR comments.

---
## Roadmap Ideas
- Inline annotations (GitHub Checks annotations API)
- SARIF export for code scanning dashboards
- Slack / Teams notification bridge

---
Maintained alongside `scripts/run_review.py`. Keep flags in sync when extending functionality.
