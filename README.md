# bindless

A small, local, container-only educational project about one idea: **user input crossing the
boundary from data into the structure of a query**.

Everything in it is fictional — the organizations, the people, the suppliers, the invoices, and
every "secret". It runs entirely on your machine, contacts nothing, and changes no data.

> **Status:** this repository currently contains the *secure* baseline only. The deliberately
> vulnerable counterpart, the side-by-side comparison, and the full walkthrough arrive next.

## Requirements

Docker with Compose. Nothing else — no Python, no PostgreSQL, no project install on the host.

## Run the demonstration

```sh
./scripts/demo.sh
```

This brings up a fresh PostgreSQL instance, waits for it to be ready, seeds deterministic
fixtures, runs the walkthrough against the application over real HTTP, prints a verdict, and
cleans up after itself.

## Run the checks

```sh
./scripts/check.sh
```

Ruff, mypy, and pytest, inside the container image, against a freshly seeded database and the
running application. GitHub Actions runs this same script.

## Explore the API by hand

```sh
docker compose up
```

The secure application is then on <http://127.0.0.1:8000>, with generated OpenAPI documentation at
<http://127.0.0.1:8000/docs>. PostgreSQL is not published to the host at all.

```sh
curl -s -H 'Authorization: Bearer demo-token-northwind' \
  'http://127.0.0.1:8000/invoices?supplier=Kestrel%20Logistics&sort=amount'
```

Stop it with `docker compose down`.

## The scenario

A fictional supplier-invoice portal serves several tenant organizations out of one database. Each
organization has its own users, suppliers, and invoices. A separate `integration_credentials` table
holds conspicuously fake third-party secrets that **no endpoint ever legitimately queries** — it is
there so "a table this screen should never be able to reach" is a real, observable thing.

One endpoint does the work:

```
GET /invoices?supplier=<term>&sort=<column>
```

By contract it returns only the calling user's own organization's invoices, ordered by the
requested column.

## Two kinds of input, two different fixes

The interesting part is that the endpoint takes two pieces of untrusted input that cannot be
defended the same way.

`supplier` is a **value**. It is bound as a parameter, so the database receives it as data and
never as query structure:

```sql
WHERE i.org_id = :org_id AND s.name = :supplier
```

Type `' OR '1'='1` into the search box and you get zero rows, because there is no supplier
literally named `' OR '1'='1`. The tenant filter is bound the same way, which is what keeps one
organization's invoices invisible to another — even when two organizations happen to use a supplier
with exactly the same name, as `Kestrel Logistics` does here. Guessability was never the defence.

`sort` names a **column**. A parameter placeholder cannot stand in for an identifier — you cannot
write `ORDER BY :column` — so binding is not available and something else has to do the job. Here
that is a fixed allowlist of permitted `(column, direction)` pairs with a safe default. Anything
outside it is refused with a generic `400` that does not name a single valid column, so the
rejection never becomes a way to map the schema.

## Layout

| Path | What it is |
|---|---|
| `src/bindless/listing.py` | the listing query: bound values, allowlisted identifier |
| `src/bindless/api.py` | shared HTTP wiring, so every variant has an identical contract |
| `src/bindless/secure_app.py` | the secure application |
| `src/bindless/fixtures.py` | the deterministic fictional data |
| `src/bindless/scenarios.py` | the scenario engine, driven directly by tests |
| `src/bindless/demo.py` | the command that renders the walkthrough |
| `tests/` | the regression suite |

## Safety boundary

This is local educational software. It is not deployed or hosted anywhere, and it must not be.

- The demonstration is **non-destructive by construction**: the listing is a read-only,
  single-statement query, and the regression suite proves the fixture data is byte-for-byte
  identical after every path.
- Destructive, data-definition (DDL), and stacked-statement payloads are **out of scope by
  design**. This project does not demonstrate or require any of them.
- Nothing here interacts with, tests, or describes any real system.
- Authentication is deliberately a toy: static demonstration bearer tokens, which is not a pattern
  to copy.
