# Design Document

## Overview

Fix unit 2 of `multi-tenancy-cli`. The verifier found the problems below in `multi-tenancy-cli`; each task of tasks.md names the findings it answers, and bugfix.md says what must change and what must not.

## Findings and Decisions

### F-fda7e586: repository CI failed: ci.yml / lint · types · tests

Severity: blocker. Chore: a single phase, no red test.

job `ci.yml / lint · types · tests` failed on the hand-off commit c994c20bc9 (<forge>/WeLikeCode/mint-mory/actions/runs/39482344837/job/118834065447). Log ends: ...0T19:21:18.7389830Z ##(warning)Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, astral-sh/setup-uv@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/. 33336 1929 94% 2026-10-20T19:21:17.5276081Z Required test coverage of 80% reached. Total coverage: 94.21% 2026-10-20T19:21:17.52768...
