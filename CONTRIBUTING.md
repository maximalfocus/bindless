# Contributing to bindless

Thanks for your interest. `bindless` is a small, local, educational demonstration of SQL injection
and its fix, and contributions are welcome within that purpose.

## Ground rules

- **The vulnerability stays.** The `vulnerable` application is intentionally insecure and is the
  whole point. Please do not "fix" it or remove its demonstrated behaviour; improvements to the
  *demonstration* — clarity, tests, documentation — are what help here.
- **Everything stays fictional and local.** All organizations, people, suppliers, invoices, tokens,
  and "secrets" are invented. Do not add real data, real credentials, or anything that reaches a
  real system.
- **Non-destructive by design.** The demonstration uses read-only, single-statement queries.
  Destructive, DDL (data-definition), and stacked-statement payloads are out of scope, as are blind
  or time-based inference and payload fuzzing.
- **No deployment or hosting.** This project is run locally with Docker Compose only.

## Developing

Everything runs in containers; the host needs only Docker.

```sh
./scripts/check.sh   # Ruff, mypy, and pytest against a freshly seeded database and both apps
./scripts/demo.sh    # the one-shot vulnerable-vs-secure comparison
```

Please make sure `./scripts/check.sh` is green before opening a pull request, keep changes focused,
and add or update tests at the behaviour boundary you are changing. The same Compose command runs in
GitHub Actions.

## Reporting problems

For an *unintended* security issue, follow [`SECURITY.md`](SECURITY.md) and report it privately. For
everything else — a bug in the demonstration, a documentation gap, an idea — open a normal issue.
