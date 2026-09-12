"""Read-only public endpoint smoke check. No credentials or writes required."""

import json

from failurelab.config import Settings
from failurelab.integrations import GitHub, npm_metadata


def main():
    report = {}
    package = npm_metadata("@playwright/test", "1.51.0")
    report["npm"] = {"status": "passed", "name": package["name"], "version": package["version"]}
    settings = Settings(github_repositories="microsoft/playwright", github_token="", _env_file=None)
    github = GitHub(settings)
    try:
        runs = github.get("/repos/microsoft/playwright/actions/runs?status=failure&per_page=1")
        if not runs.get("workflow_runs"):
            raise RuntimeError("No public failed run was available for the metadata smoke check")
        run = runs["workflow_runs"][0]
        snapshot = github.describe_run("microsoft/playwright", run["id"])
        report["github"] = {
            "status": "passed",
            "repository": snapshot["repository"],
            "run_id": snapshot["run_id"],
            "commit_sha": snapshot["commit_sha"],
            "scope": "public workflow metadata only",
        }
    finally:
        github.close()
    settings.prepare()
    (settings.data_dir / "integration-smoke.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
