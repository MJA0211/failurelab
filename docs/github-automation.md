# GitHub automation

The workflows run on GitHub-hosted runners. Actions are pinned to commit hashes,
checkout credentials are not persisted, and jobs have read-only repository access
unless they need to upload CodeQL results. No workflow uses `pull_request_target`
to execute pull-request code.

| Automation | Triggers | Checks or output |
|---|---|---|
| Quality gates | Push, pull request, Monday schedule, manual | Python 3.11 and 3.12 tests, Ruff lint/format, frontend format/build, pip-audit, npm audit, authored baseline evaluation |
| CodeQL | Push to master, pull request to master, Tuesday schedule, manual | Python, JavaScript/TypeScript, and GitHub Actions analysis with security-extended queries |
| Dependency review | Pull request to master, manual comparison | Rejects newly introduced known vulnerabilities at low severity or higher |
| Dependency graph SBOM | Manifest or workflow changes on master, Monday schedule, manual | Validates Python/npm presence in GitHub's graph and archives an SPDX SBOM |
| Dependabot updates | Weekly on Monday at 09:00 America/New_York | Update pull requests for uv, npm, GitHub Actions, and Docker |

Dependabot groups minor and patch updates for Python, npm, and Actions. Major updates
remain separate. Update pull requests require review; these workflows do not merge
them automatically. Dependabot security updates remain enabled independently of the
weekly version-update schedule.

GitHub already resolves the Python lockfile through its managed Dependency Graph
workflow and reads the npm lockfile. The SBOM workflow exports that graph without
overwriting it with a separate dependency submission. Graph ingestion is asynchronous,
so the export shows the current graph and does not attest to an exact commit.

Quality artifacts and SBOMs are retained for 14 days. Browser screenshots and traces
used in quality checks come from owned fixtures; local runtime state and credentials
are not uploaded. The Python audit covers installed dependencies in each CI environment,
not optional model or PostgreSQL packages that were not installed.

Inspect CodeQL results in the repository's Security tab. A completed analysis means
the scanner ran and uploaded results; review any resulting alerts separately. Check
Dependabot jobs under Insights / Dependency graph / Dependabot and workflow runs under
Actions. Manual dependency review accepts a base and head ref for a real comparison.

These workflows report checks. They do not configure branch protection or bypass
repository rules. The application version tag `v0.1.1` remains unchanged.

References: [CodeQL workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options),
[Dependabot ecosystem support](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories),
and [GitHub dependency graph](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/explore-dependencies).
