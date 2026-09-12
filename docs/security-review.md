# Security finding review — September 12, 2026

This review covers the reported request and command boundaries. It is not an
independent penetration test or a security certification. The disposable-VM requirement
for executing repository code remains in force.

| Finding | Change or disposition | Regression evidence |
|---|---|---|
| Repository regex / `py/polynomial-redos` | Replaced the unbounded expression with bounded owner/repository validation | Oversized, dot-segment, and malformed allowlisted names are rejected |
| GitHub API path / `py/partial-ssrf` | Use the operator's canonical repository entry and a positive numeric run ID; constrain credentialed requests to the fixed GitHub API origin and canonical path segments | Absolute URLs, alternate hosts, traversal, encoded delimiters, fragments, and unsupported queries fail before HTTP requests |
| Deep-link path / `js/client-side-request-forgery` | Accept only generated investigation IDs from the browser URL and encode IDs in API paths | A real browser checks hostile deep links without issuing unexpected API requests |
| Git checkout / `py/command-line-injection` | Reviewed as a false positive for the validated argument flow described below; added defense-in-depth argument termination | Direct execution rejects invalid repository/SHA values even when model validation is bypassed; an actual Git process verifies `--` operand handling |

## Git checkout argument analysis

The remaining reported flow traced `request.repository` and `request.commit_sha` into
the argument list passed to `subprocess.Popen`. The execution boundary checks the
repository against two bounded ASCII components, rejects dot segments, and requires
exactly 40 hexadecimal characters for the commit SHA. The URL has a fixed
`https://github.com/` prefix. Git receives a fixed executable/subcommand, separate
arguments, and an explicit `--` before the URL and SHA. No shell interprets the data.
Those operands cannot supply a new executable, shell syntax, or Git options.

The endpoint separately requires bearer authentication and an operator-reviewed
manifest entry. Dependencies and checked-out repository code still execute later,
inside the required disposable Linux VM. Validation is not a sandbox for that code.

`tests/test_runner_service.py` exercises malformed direct calls, option-shaped test
names, and the actual Git option terminator. `tests/test_integrations.py` and
`tests/test_ui.py` cover the request boundaries. No CodeQL query, test, or severity
threshold was disabled. Re-review the command finding if the executable, argument
layout, validation, authentication, or repository policy changes.

References: [CodeQL command-line query](https://codeql.github.com/codeql-query-help/python/py-command-line-injection/)
and [project security boundaries](../SECURITY.md).
