from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["log", "code", "dom", "document", "metadata", "image"]
    content: str = Field(default="", max_length=100_000)
    source: str = Field(default="", max_length=1000)
    sha: str = ""
    artifact: str | None = None


Cause = Literal["overlay", "selector", "api_contract", "dependency", "timing", "unknown"]
Intervention = Literal["remove_overlay", "restore_selector", "restore_response", "repeat_baseline"]


class Hypothesis(StrictModel):
    id: str = Field(pattern=r"^h[1-3]$")
    cause: Cause
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    status: Literal["proposed", "supported", "contradicted", "inconclusive"] = "proposed"


class Diagnosis(StrictModel):
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=3)
    missing_evidence: list[str] = Field(default_factory=list, max_length=8)


class ExperimentPlan(StrictModel):
    hypothesis_id: str = Field(pattern=r"^h[1-3]$")
    intervention: Intervention
    rationale: str = Field(min_length=1, max_length=1000)
    repetitions: int = Field(default=3, ge=2, le=5)


class Plans(StrictModel):
    experiments: list[ExperimentPlan] = Field(max_length=3)


class ExperimentResult(StrictModel):
    hypothesis_id: str
    intervention: Intervention
    baseline_passes: int = Field(ge=0)
    intervention_passes: int = Field(ge=0)
    repetitions: int = Field(ge=2, le=5)
    verdict: Literal["supported", "contradicted", "inconclusive", "unavailable"]
    duration_ms: int = Field(ge=0)
    observations: list[str]
    artifacts: list[str] = Field(default_factory=list)
    environment: dict = Field(default_factory=dict)


class RunnerArtifact(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}\.(?:png|zip)$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_base64: str = Field(max_length=8_000_000)


class RunnerResponse(ExperimentResult):
    artifact_payloads: list[RunnerArtifact] = Field(default_factory=list, max_length=16)


class InvestigationInput(StrictModel):
    title: str = Field(min_length=3, max_length=200)
    repository: str = Field(pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
    commit_sha: str = Field(pattern=r"^[a-fA-F0-9]{7,40}$")
    test_name: str = Field(min_length=1, max_length=300)
    evidence: list[Evidence] = Field(min_length=1, max_length=40)


class GitHubImport(StrictModel):
    repository: str = Field(pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
    run_id: int = Field(gt=0)
    test_name: str | None = Field(default=None, min_length=1, max_length=300)


class Review(StrictModel):
    decision: Literal["accepted", "rejected", "needs_evidence"]
    note: str = Field(min_length=3, max_length=2000)


class DemoRequest(StrictModel):
    scenario: Literal["overlay", "selector", "api_contract", "unknown"] = "overlay"
