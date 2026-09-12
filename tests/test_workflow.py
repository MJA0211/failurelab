import pytest

from failurelab.fixtures import fixture
from failurelab.runner import run_experiment, run_fixture, verdict
from failurelab.schemas import ExperimentPlan
from failurelab.workflow import Investigator, Worker


def test_unknown_finishes_without_fabricated_experiment(settings, store):
    case_id, _ = store.create(fixture("unknown"), source="demo", scenario="unknown")
    assert Worker(settings, store).tick()
    result = store.get(case_id)["result"]
    assert result["outcome"] == "inconclusive"
    assert result["experiments"] == []
    assert result["metrics"]["model_calls"] == 0
    assert result["missing_evidence"]


def test_completed_checkpoint_replay_is_idempotent(settings, store):
    case_id, _ = store.create(fixture("unknown"), source="demo", scenario="unknown")
    Investigator(settings, store).run(case_id)
    first = store.get(case_id)["result"]
    events = store.timeline(case_id)
    Investigator(settings, store).run(case_id)
    assert store.get(case_id)["result"] == first
    assert store.timeline(case_id) == events


def test_resume_after_failure_does_not_repeat_completed_node(settings, store, monkeypatch):
    case_id, _ = store.create(fixture("unknown"), source="demo", scenario="unknown")
    investigator = Investigator(settings, store)
    original = investigator.plan
    monkeypatch.setattr(
        investigator, "plan", lambda state: (_ for _ in ()).throw(RuntimeError("Injected failure"))
    )
    with pytest.raises(RuntimeError, match="Injected"):
        investigator.run(case_id)
    before = store.timeline(case_id)
    assert any(e["stage"] == "diagnose" for e in before)
    monkeypatch.setattr(investigator, "plan", original)
    monkeypatch.setattr(
        investigator,
        "diagnose",
        lambda state: (_ for _ in ()).throw(AssertionError("Completed diagnosis was repeated")),
    )
    investigator.run(case_id)
    assert store.get(case_id)["status"] == "completed"


def test_imported_repository_never_executes_in_local_runner(settings, store):
    case_id, _ = store.create(fixture("overlay"), source="manual")
    result = run_experiment(
        settings,
        store,
        store.get(case_id),
        ExperimentPlan(
            hypothesis_id="h1", intervention="remove_overlay", rationale="Check overlay"
        ),
    )
    assert result.verdict == "unavailable"


def test_rerun_and_mixed_outcomes_are_not_confirmation():
    assert verdict(0, 3, 3, "remove_overlay") == "supported"
    assert verdict(0, 0, 3, "remove_overlay") == "contradicted"
    assert verdict(1, 3, 3, "remove_overlay") == "inconclusive"
    assert verdict(0, 3, 3, "repeat_baseline") == "inconclusive"


@pytest.mark.browser
@pytest.mark.parametrize(
    "scenario,intervention",
    [
        ("overlay", "remove_overlay"),
        ("selector", "restore_selector"),
        ("api_contract", "restore_response"),
    ],
)
def test_real_browser_interventions(store, scenario, intervention):
    case_id, _ = store.create(fixture(scenario), source="demo", scenario=scenario)
    plan = ExperimentPlan(
        hypothesis_id="h1",
        intervention=intervention,
        rationale="Exercise the real browser",
        repetitions=2,
    )
    result = run_fixture(store, case_id, scenario, plan)
    assert result.baseline_passes == 0
    assert result.intervention_passes == 2
    assert result.verdict == "supported"
    assert len(result.artifacts) == 4
    for name in result.artifacts:
        assert store.artifact_path(case_id, name).stat().st_size > 0
    assert run_fixture(store, case_id, scenario, plan) == result


@pytest.mark.browser
def test_wrong_browser_intervention_is_contradicted(store):
    case_id, _ = store.create(fixture("overlay"), source="demo", scenario="overlay")
    result = run_fixture(
        store,
        case_id,
        "overlay",
        ExperimentPlan(
            hypothesis_id="h1",
            intervention="restore_selector",
            rationale="Try a competing explanation",
            repetitions=2,
        ),
    )
    assert result.baseline_passes == 0 and result.intervention_passes == 0
    assert result.verdict == "contradicted"
