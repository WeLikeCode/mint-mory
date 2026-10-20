# Design Document

## Overview

Fix unit 1 of `multi-tenancy-cli`. The verifier found the problems below in `multi-tenancy-cli`; each task of tasks.md names the findings it answers, and bugfix.md says what must change and what must not.

## Findings and Decisions

### F-2192b892: Global image-caption-put exits 2, not 1

Severity: major.

Decided by human in Q-013: R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active image file-record found ...' to stderr and exits 1.. R6.10 requires exit 1 for a global image-caption-put on a tenant image. The code keeps the BadParameter path (exit 2) and the test was loosened to != 0.
