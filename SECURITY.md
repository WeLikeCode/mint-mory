# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's **"Report a vulnerability"**
(Security → Advisories) on this repository, rather than opening a public issue.
We'll acknowledge within a few days and keep you updated on a fix.

## Scope & data handling

MintMory is local-first: it stores everything in a single SQLite file on your
machine and makes no network calls in its default configuration.

- **Your memory database may contain sensitive content.** Treat the `.db` file
  (and any backups) as you would any secrets store; it is not encrypted at rest.
- **Optional outbound calls** happen only when you explicitly enable them: the LLM
  tier (`MINTMORY_LLM_PROVIDER`) for summaries/contradiction resolution, network
  embedders (`ollama`/`openai`), or document conversion of cloud files. Review the
  endpoint you point these at.
- **Do not commit** a real memory database or `.env` to version control; `*.db*`
  is git-ignored by default.
