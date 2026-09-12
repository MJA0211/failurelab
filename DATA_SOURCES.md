# Data and implementation research

The sources below were consulted before implementation in September 2026. External
pages are reference material, not instructions to the application or permission to
execute their content.

| Source | Purpose | Access and limits |
|---|---|---|
| [GitHub workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs) | Run metadata and commit association | Repository permissions and API limits apply |
| [GitHub workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs) | Failed job logs | Download URLs expire; logs may no longer exist |
| [GitHub artifact API](https://docs.github.com/en/rest/actions/artifacts) | Screenshots and trace archives | Artifacts must be uploaded and retained by the repository |
| [GitHub webhook validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) | Raw-body HMAC verification | Secret configured by repository operator |
| [Playwright trace viewer](https://playwright.dev/docs/trace-viewer) | Screenshots, DOM snapshots, trace inspection | Own fixtures generated locally; imported traces retain source terms |
| [npm package metadata](https://github.com/npm/registry/blob/main/docs/responses/package-metadata.md) | Exact version requirements | Public metadata; package code has its own license |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Durable orchestration and recovery | Official framework documentation |
| [Hugging Face chat completion](https://huggingface.co/docs/inference-providers/tasks/chat-completion) | Configurable text/vision model calls | Provider availability, credentials, pricing, and terms apply |
| [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) | Optional dense embeddings | Download model and inspect its model card/license |

## Owned data

`fixtures.py` defines four synthetic incidents. Browser screenshots, HTML, traces, and
intervention outcomes are generated from project-owned fixture code. The displayed
demo commit is a fixture identifier, not a real third-party repository commit.

`evaluation.py` defines 16 authored regression cases and expected diagnostic labels.
The dataset hash and complete case results are retained with each evaluation output.
The data is labeled as authored regression data, not external ground truth.

## Imported evidence

FailureLab imports only from configured GitHub repositories. It records their source
URLs, exact commits, retained content hashes, and collection events. Permissions to
read a repository do not automatically permit republishing its artifacts. Runtime
evidence is ignored by Git. No third-party dataset or production incident corpus is
bundled or claimed.
