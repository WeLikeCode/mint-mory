# Implementation Plan

- [x] 1. Fix the findings of the verifier
  - [x] 1.1 R3.2 cap on filter/all_active rows is not enforced before duplicate skipping (F-37e92031; C-3affbf7d, C-18a7043f)
    - _Requirements: 2.1, 2.2_

## Task Dependency Graph

```json
{"waves": [{"id": 0, "tasks": ["1.1"]}]}
```
