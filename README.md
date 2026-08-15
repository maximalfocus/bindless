# bindless

A small, local, container-only educational project about one idea: **user input crossing the
boundary from data into the structure of a query**. That is SQL injection — OWASP
[A03:2021 Injection](https://owasp.org/Top10/A03_2021-Injection/),
[CWE-89](https://cwe.mitre.org/data/definitions/89.html).

Everything in it is fictional — the organizations, the people, the suppliers, the invoices, and
every "secret". It runs entirely on your machine, contacts nothing, and changes no data. It ships
the flaw and its fix **side by side** so you can watch exactly where they diverge.

## Requirements

Docker with Compose. Nothing else — no Python, no PostgreSQL, no project install on the host.

## See it in one command

```sh
./scripts/demo.sh
```

This brings up a fresh PostgreSQL instance, seeds deterministic fixtures, starts **both** the
vulnerable and the secure portal, sends the same payloads to each over real localhost HTTP, prints
the comparison and a verdict, and cleans up. It finishes well under five minutes once images are
built.

You will see, per payload, the query the vulnerable app assembled, how many rows each app returned,
whether tenant isolation broke or credentials leaked, and how the sort behaved:

```
SCENARIO                          VULNERABLE APP                      SECURE APP                      VERDICT
--------------------------------  ----------------------------------  ------------------------------  -------------------------------
Benign search, legitimate sort    3 rows, own tenant only             3 rows, own tenant only         parity
Tautology tenant-isolation break  9 rows, 5 from other tenants        0 rows — filter held            vulnerable leaked · secure held
UNION credential exfiltration     3 credential value(s) exfiltrated   0 rows — filter held            vulnerable leaked · secure held
Injected ORDER BY identifier      injected ORDER BY accepted          HTTP 400 — refused, no columns  vulnerable leaked · secure held
```

Add `--verbose` for the underlying HTTP exchanges, or explore your own inputs:

```sh
docker compose run --rm demo python -m bindless.cli interactive
```

## The scenario

A fictional supplier-invoice portal serves several tenant organizations out of one database. Each
organization has its own users, suppliers, and invoices. A separate `integration_credentials` table
holds conspicuously fake third-party secrets that **no endpoint ever legitimately queries** — it is
there so "a table this screen should never be able to reach" is a real, observable thing.

One endpoint does the work, and both portals expose it identically:

```
GET /invoices?supplier=<term>&sort=<column>
```

By contract it returns only the calling user's own organization's invoices, ordered by the
requested column. The caller is a *legitimately authenticated* user of one tenant — this is not an
authentication flaw. The only difference between the two portals is how that one query is built.

## Data versus query structure

A SQL statement has two kinds of content: **structure** (the keywords, table and column names, and
operators that say what the query *does*) and **data** (the values it compares against). A query is
safe when user input can only ever land in the data half.

The vulnerable portal builds its statement by pasting your input into the text:

```python
f"... WHERE i.org_id = {org_id} AND s.name = '{supplier}' ORDER BY {sort}"
```

Now your input *is* part of the structure. The database can no longer tell "a supplier named X"
from "and here is some more query". That is the entire vulnerability, and everything below is a
consequence of it.

### 1 · The tautology dissolves the tenant boundary

Enter `supplier=' OR '1'='1` and the assembled `WHERE` becomes:

```sql
WHERE i.org_id = 1 AND s.name = '' OR '1'='1'
```

`AND` binds tighter than `OR`, so this reads as *(my org AND empty name) OR (always true)* — true
for **every** row in the table. The vulnerable app returns invoices from every organization; the
`org_id = 1` filter has evaporated.

### 2 · UNION reads a table the endpoint never touches

Enter a `supplier` payload of the form
`' UNION SELECT provider, api_key, 0, 'leaked' FROM integration_credentials --`, its columns lined
up with the invoice projection, and the vulnerable app renders **credential rows inside the invoice
list**. The endpoint was never written to query that table; the injected `UNION` reaches it anyway.

### 3 · The sort column can't be a value at all

`sort` names a *column*, and a column position is structure, not data. A crafted `sort=` value
reaches the `ORDER BY` clause directly — it can even order by a subquery that reads
`integration_credentials`.

## Two flaws, two different fixes

The most important lesson in this project is that the two injection points **cannot be fixed the
same way**.

### Bind the values

`org_id` and `supplier` are values, so the secure portal binds them as parameters:

```sql
WHERE i.org_id = :org_id AND s.name = :supplier
```

The database receives your input as data, always. `' OR '1'='1` becomes a search for a supplier
literally named `' OR '1'='1` — of which there are none, so you get zero rows. The `UNION` payload
is likewise just an oddly-named supplier, and `integration_credentials` stays unreachable. Note that
this is *not* about escaping quotes by hand, and *not* about the tenant boundary being hard to
guess: two organizations here even share a supplier named `Kestrel Logistics`, and the boundary
still holds, because it is bound.

### Allowlist the identifier

`sort` names a column, and **you cannot bind an identifier** — there is no `ORDER BY :column`. So
binding is not available and something else must do the job. The secure portal resolves `sort`
through a fixed allowlist of permitted `(column, direction)` pairs with a safe default, and refuses
anything else with a generic `400` that names no valid column. The refusal is not an oracle: a
rejected sort, an unknown supplier, and a real miss are indistinguishable from the outside.

When the secure app refuses a sort, it emits exactly one structured audit line to standard output —
carrying a request id and the actor and organization, and deliberately **not** the token, the
authorization header, or the rejected value:

```json
{"action":"list_invoices","actor_org_id":1,"actor_user_id":1,"event":"listing.sort_rejected","outcome":"rejected","reason":"sort_not_allowlisted","request_id":"…","timestamp":"…"}
```

## Explore the API by hand

```sh
docker compose up
```

The **secure** application is then on <http://127.0.0.1:8000>, with generated OpenAPI docs at
<http://127.0.0.1:8000/docs>. The default `docker compose up` starts the secure app only.
PostgreSQL is not published to the host at all.

```sh
curl -s -H 'Authorization: Bearer demo-token-northwind' \
  'http://127.0.0.1:8000/invoices?supplier=Kestrel%20Logistics&sort=amount'
# → three INV-100x invoices for Northwind Freight, ordered by amount

curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer demo-token-northwind' \
  "http://127.0.0.1:8000/invoices?supplier=Kestrel%20Logistics&sort=api_key"
# → 400 (sort not on the allowlist)
```

### Running the vulnerable app for manual exploration

Starting the vulnerable portal takes **two deliberate actions** — enabling its Compose profile and
setting the acknowledgement — so it can never come up by accident:

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable up
```

It then listens on <http://127.0.0.1:8001> (loopback only). With only one of the two actions it
refuses to start.

```sh
curl -s -D - -o /dev/null -H 'Authorization: Bearer demo-token-northwind' \
  "http://127.0.0.1:8001/invoices?supplier=%27%20OR%20%271%27%3D%271"
# → 200, and an X-Bindless-Effective-Query header showing the injected SQL
```

## Run the checks

```sh
./scripts/check.sh
```

Ruff, mypy, and pytest, inside the container image, against a freshly seeded database and both
running applications. GitHub Actions runs this same script, followed by the one-shot demo.

## Layout

| Path | What it is |
|---|---|
| `src/bindless/listing.py` | the **secure** query: bound values, allowlisted identifier |
| `src/bindless/vulnerable_listing.py` | the **vulnerable** query: string interpolation (do not copy) |
| `src/bindless/api.py` | shared HTTP wiring, so every variant has an identical contract |
| `src/bindless/secure_app.py`, `vulnerable_app.py` | the two application entry points |
| `src/bindless/audit.py` | the rejection audit event |
| `src/bindless/compare.py` | the comparison engine, driven directly by tests |
| `src/bindless/cli.py` | the demonstration CLI (`compare` and `interactive`) |
| `src/bindless/fixtures.py` | the deterministic fictional data |
| `tests/` | the security regression matrix |

## Project status and support

`bindless` is a local educational demonstration, offered as-is under the [MIT License](LICENSE).
There is **no hosted service** — nothing here runs anywhere but your own machine — and it makes **no
production-safety, support-duration, or compatibility commitment**. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) to get involved and [`SECURITY.md`](SECURITY.md) for how to
report an *unintended* problem (the deliberately vulnerable app is not one).

## Safety boundary

This is local educational software. It is not deployed or hosted anywhere, and it must not be. The
vulnerable application is intentionally insecure and exists only to be observed on your machine.

- The demonstration is **non-destructive by construction**: every listing is a read-only,
  single-statement query, and the regression suite proves the fixture data is byte-for-byte
  identical after every path — including every attack.
- Destructive, data-definition (DDL), and stacked-statement payloads are **out of scope by
  design**. This project does not demonstrate or require any of them, and neither does it cover
  blind/boolean or time-based inference, payload fuzzing, or secret enumeration beyond the two
  scripted injection points.
- Nothing here interacts with, tests, or describes any real system.
- Authentication is deliberately a toy: static demonstration bearer tokens, which is not a pattern
  to copy.
