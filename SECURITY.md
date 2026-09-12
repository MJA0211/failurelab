# Security boundaries

FailureLab has one workspace trust domain. A configured bearer token protects all
workspace API access, including downloads. It is not per-user authentication or
multi-tenancy. Binding outside loopback requires a token. A same-origin deployment
is expected; foreign browser origins are rejected. Configure TLS at the reverse proxy.

Origin checks compare the scheme, hostname, and effective port. Malformed or duplicate
Origin headers are rejected, and localhost ports have no cross-origin exemption.
The Vite development server uses its same-origin proxy. Loopback deployments accept
only localhost and the IPv4/IPv6 loopback literals as Host values. A reverse proxy
must preserve the public Host and forward the correct scheme through a trusted proxy
configuration; do not trust forwarded headers from arbitrary clients.

Webhook signatures are validated against the raw request body before parsing.
Repository imports require an explicit allowlist. HTTP redirects for GitHub storage
are allowlisted and fetched without GitHub Authorization headers. Request, archive,
expansion, model output, and experiment bounds prevent common accidental overloads.
Use ingress rate limits for an internet-facing deployment; app authentication alone
is not a distributed abuse-prevention service.

Credentialed GitHub API requests use a fixed HTTPS origin and canonical, bounded path
segments. Dot segments, encoded delimiters, alternative origins, and unsupported query
strings are rejected before the request is sent. Repository names have bounded owner
and repository components. Browser deep links accept only generated investigation IDs;
IDs are encoded separately when constructing API paths.

GitHub metadata and artifact responses are read incrementally and stopped when the
decoded response exceeds the configured ingestion limit. The response stream is
closed on rejection. Bearer tokens and webhook signatures use constant-time byte
comparisons so malformed non-ASCII headers are rejected without a comparison error.

Retrieved content is untrusted evidence. It cannot add tools or executable commands.
Structured outputs and citation references are validated. These controls reduce the
impact of prompt injection but do not prove semantic immunity; a model can still offer
a misleading hypothesis. Only experiments can produce experimental support, and human
review remains visible.

Text credentials matching supported patterns are redacted before storage. This is
best-effort secret filtering, not a guarantee. Screenshots can contain secrets and
must be treated as sensitive. Do not publish imported evidence without permission.
Model chat mode sends retained evidence to the configured provider; confirm the
provider's data-handling terms for the repository's sensitivity.

The local runner executes only owned static HTML and fixed interventions. Browser
network routes are blocked. This is not a secure sandbox for arbitrary untrusted code.
Imported code requires the separately isolated disposable-VM runner described in
docs/runner-protocol.md. Review manifests cannot constrain malicious repository code;
the VM boundary and credential/network restrictions remain mandatory.

The repository runner binds a test name to one `--grep=` argument and escapes its
regular-expression syntax. A name beginning with `--` cannot select a different CLI
option. This argument boundary does not make repository execution safe outside the
required disposable VM.

Do not report credentials or private logs in public issues. Security fixes should
include regression tests demonstrating the actual boundary that failed.

Report vulnerabilities through [GitHub's private reporting form](https://github.com/MJA0211/failurelab/security/advisories/new).
Include the affected version, reproduction steps using synthetic data, and the
expected and observed behavior. Remove credentials and private repository evidence
from the report.

CI audits installed Python dependencies and the npm lockfile for known vulnerabilities.
Third-party CI actions are pinned to commit hashes, and checkout does not persist
its credentials. These checks supplement the isolation and access controls above;
they do not establish that the application is free of vulnerabilities.
