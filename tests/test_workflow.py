import pytest

from failurelab import runner
from failurelab.fixtures import fixture
from failurelab.runner import check, run_experiment, run_fixture, setup_page, verdict
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
    assert result.baseline_passes == 0, result.observations
    assert result.intervention_passes == 2, result.observations
    assert result.verdict == "supported", result.observations
    assert len(result.artifacts) == 4
    for name in result.artifacts:
        assert store.artifact_path(case_id, name).stat().st_size > 0
    assert run_fixture(store, case_id, scenario, plan) == result


@pytest.mark.browser
@pytest.mark.parametrize("scenario", ["overlay", "selector"])
def test_browser_check_waits_for_delayed_actionability(scenario):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())
            setup_page(page, "api_contract")
            target = "checkout" if scenario == "overlay" else "search-input"
            page.get_by_test_id(target).evaluate(
                """element => {
                    element.disabled = true;
                    setTimeout(() => { element.disabled = false; }, 600);
                }"""
            )
            passed, observation = check(page, scenario)
            assert passed, observation
            if scenario == "overlay":
                assert page.locator("#success").inner_text() == "Order placed"
            else:
                assert page.get_by_test_id(target).input_value() == "notebook"
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_cache_changes_with_action_budget(store, monkeypatch):
    case_id, _ = store.create(fixture("api_contract"), source="demo", scenario="api_contract")
    plan = ExperimentPlan(
        hypothesis_id="h1",
        intervention="restore_response",
        rationale="Check cache provenance",
        repetitions=2,
    )
    first = run_fixture(store, case_id, "api_contract", plan)
    monkeypatch.setattr(runner, "ACTION_TIMEOUT_MS", runner.ACTION_TIMEOUT_MS + 100)
    second = run_fixture(store, case_id, "api_contract", plan)
    assert first.environment["action_timeout_ms"] != second.environment["action_timeout_ms"]
    assert set(first.artifacts).isdisjoint(second.artifacts)
    assert first.verdict == second.verdict == "supported"
    assert run_fixture(store, case_id, "api_contract", plan) == second


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
