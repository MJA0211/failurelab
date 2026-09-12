# Security boundaries

FailureLab has one workspace trust domain. A configured bearer token protects all
workspace API access, including downloads. It is not per-user authentication or
multi-tenancy. Binding outside loopback requires a token. A same-origin deployment
is expected; foreign browser origins are rejected. Configure TLS at the reverse proxy.

Webhook signatures are validated against the raw request body before parsing.
Repository imports require an explicit allowlist. HTTP redirects for GitHub storage
are allowlisted and fetched without GitHub Authorization headers. Request, archive,
expansion, model output, and experiment bounds prevent common accidental overloads.
Use ingress rate limits for an internet-facing deployment; app authentication alone
is not a distributed abuse-prevention service.

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

Do not report credentials or private logs in public issues. Security fixes should
include regression tests demonstrating the actual boundary that failed.
