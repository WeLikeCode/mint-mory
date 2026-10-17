# Proposal: fix 1 for add-telemetry-heavy-path-spans

## Why
The verifier found problems in `add-telemetry-heavy-path-spans` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-6eb0cc43 (major): an inline suppression was not declared: packages/core/src/mintmory/core/storage.py:871 # noqa: PLC0415. Remove each comment by fixing what it hides; declare one only if it cannot be removed

## Impact
The code and the tests of `add-telemetry-heavy-path-spans`.
