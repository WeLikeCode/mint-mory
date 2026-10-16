# Design: local observability stack

## Decisions

- **The doctor row never fails `doctor`.** `doctor` is the command a user runs when something is wrong, so a bad
  `OTEL_EXPORTER_OTLP_ENDPOINT` (no host, port out of range) is reported as `reachable=invalid`, and any other error
  as `status unavailable (<class>)`; the exit code depends only on the existing checks.
- **One status cell of `key=value` pairs**, because the doctor table has two columns (`check`, `status`); tests match
  the exact text with `COLUMNS=200`.
- **`SDK missing` is the display form of runtime's `sdk missing`** (and `exporting` of `export`), so the row reads as
  a status, not an internal state name.
- **Helm defaults are empty strings, not null**, so `values.schema.json` can keep `type: string` and
  `additionalProperties: false` for `otel`; the template renders a variable only for a non-empty value.
- **File tests live in `tests/integration/`**, the repository-level test folder already in `testpaths`; there are no
  deploy tests elsewhere on `staging`.
- **Image tags are pinned but not verified by the gates** (no Docker there); the `docker compose config` test runs
  where Docker exists. Splitting the stack into a separate unit would not change that.
