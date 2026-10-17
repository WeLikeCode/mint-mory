# Spec Delta

## Purpose
Regression scenarios for the ingestion capability, found by the verifier in add-recurrent-tree-indexing.

## ADDED Requirements

### Requirement: task 2.3 is ticked as already satisfied, but its text is not done — finding F-b34b9dc3
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: task 2.3 is ticked as already satisfied, but its text is not done
- **WHEN** mintmory index-tree --help is shown
- **THEN** the --text-content help says that online-only files are skipped by the inline text pass, and the index_tree docstring says the same.
