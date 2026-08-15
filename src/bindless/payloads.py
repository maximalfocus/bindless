"""The payloads the walkthrough sends.

All three are read-only. This project never demonstrates or requires a stacked-statement,
data-definition, or otherwise destructive payload — every one of these only ever *reads*, and
against the secure application they do not even do that.

Each targets a different part of the statement, which is the whole point:

* `TAUTOLOGY` and `UNION_CREDENTIALS` are supplied as a **value**, where binding is the fix;
* `SORT_IDENTIFIER` is supplied as an **identifier**, where binding is impossible and an allowlist
  is the fix.
"""

from __future__ import annotations

#: Closes the quoted supplier literal and appends a condition that is always true. Against a
#: string-built `WHERE`, `AND` binds tighter than `OR`, so the whole tenant filter dissolves.
TAUTOLOGY = "' OR '1'='1"

#: Closes the literal, appends a second result set drawn from the never-queried credentials table
#: with its columns aligned to the invoice projection, and comments out the rest of the statement.
UNION_CREDENTIALS = "' UNION SELECT provider, api_key, 0, 'leaked' FROM integration_credentials --"

#: A column position cannot be a bound parameter, so this one reaches the `ORDER BY` clause as
#: structure or not at all. It reads an unrelated table without modifying anything.
SORT_IDENTIFIER = "amount DESC, (SELECT api_key FROM integration_credentials LIMIT 1)"

#: Substring shared by every fictional demonstration secret, used to spot a credential leak.
CREDENTIAL_MARKER = "DEMO-FAKE-SECRET"
