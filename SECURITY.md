# Security policy

`bindless` is an **intentionally vulnerable** educational project. Please read this before reporting
anything.

## The vulnerability that is supposed to be here

The `vulnerable` application builds its SQL by string interpolation, and it demonstrates — on
purpose — a tenant-isolation break, cross-table credential exfiltration, and `ORDER BY` identifier
injection. **This is the subject of the project, not a bug.** Please do not report it, and please do
not open "fixes" that remove the vulnerable application or its demonstrated behaviour; the paired
`secure` application already shows the correct implementation.

The demonstration is non-destructive by construction (read-only, single-statement queries) and runs
only on your own machine against entirely fictional data. Destructive, DDL, and stacked-statement
payloads are out of scope by design.

## Reporting an *unintended* problem

If you find a genuine, unintended security problem — something outside the deliberately vulnerable
demonstration, for example an issue in the **secure** application, the container setup, or the
tooling — please report it **privately**:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** to open a private security advisory.

Please do not open a public issue for an unintended vulnerability until it has been addressed.

## Scope and expectations

This is a local, educational project with no hosted service. It makes no service-level, support, or
production-readiness commitment, and provides no guaranteed response time. Reports are reviewed on a
best-effort basis.
