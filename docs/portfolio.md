# Portfolio walkthrough

## Five-minute demonstration

1. Open the dashboard. Show that owned synthetic data and baseline mode are labeled.
2. Open the overlay failure. Inspect the actual pre-intervention browser screenshot.
3. Click a citation and show the exact retained log, source location, and content hash.
4. Open Experiments. Show failing baselines and passing interventions, download a trace,
   and explain the limits of a small controlled comparison.
5. Open the missing-artifact incident. Show that no unsupported experiment is fabricated.
6. Record a human review and export the complete investigation record.
7. Open the evaluation bench. Explain why a signature regression score is not a
   production accuracy claim, and show the checkpoint/failure tests.

## Engineering discussion

Discuss historical context leakage, exact identifier retrieval, deterministic tool
contracts, unavailable evidence, idempotency across crashes, separate code execution,
provider failure behavior, human overrides, and model quality versus system correctness.

The project maps to current applied AI role requirements for retrieval, agent tools,
typed outputs, evals, observability, deployment, and reliability. Example research:
[Fluency AI Engineer](https://jobs.ashbyhq.com/fluency/9a83146e-e32d-4e0c-84b5-59996a58a821/),
[Build Harness & Evals](https://jobs.ashbyhq.com/build/cdf0c29b-157e-4b85-a767-e72211022c96/),
[Notion Agent Dev Velocity](https://jobs.ashbyhq.com/notion/c565d3b0-0dcf-4bcd-b29b-4168479ac78e/).
These links were used for project relevance research; openings may change.

## Resume claims

Use measured engineering facts: implemented checkpointed LangGraph workflows,
versioned retrieval, credential-scoped GitHub ingestion, actual browser interventions,
schema-validated inference, and executable evaluation gates. Include the test count
from the final verification report, not a number copied from an earlier run.

Only claim model accuracy on a frozen held-out dataset after running it. Only claim
developer time savings after conducting the user study. Do not describe the authored
baseline regression accuracy as real-world diagnostic accuracy.
