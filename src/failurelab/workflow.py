import hashlib
import logging
import threading
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from failurelab.agents import PROMPT_VERSION, Agents
from failurelab.integrations import GitHub
from failurelab.retrieval import RETRIEVAL_VERSION, retrieve
from failurelab.runner import run_experiment, screenshot
from failurelab.schemas import Diagnosis, ExperimentPlan

logger = logging.getLogger("failurelab.worker")


class State(TypedDict, total=False):
    case_id: str
    runtime: dict
    started: float
    evidence: list[dict]
    retrieved: list[dict]
    diagnosis: dict
    plans: list[dict]
    experiments: list[dict]
    usage: list[dict]
    report: dict


class Investigator:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    def runtime(self):
        return {
            "mode": self.settings.model_mode,
            "model": self.settings.model_name,
            "provider": self.settings.model_base_url,
            "vision": self.settings.model_vision,
            "retrieval": self.settings.retrieval_mode,
            "embedding": self.settings.embedding_model,
            "reranker": self.settings.reranker_model,
            "prompt": PROMPT_VERSION,
            "retrieval_version": RETRIEVAL_VERSION,
        }

    def collect(self, state):
        case = self.store.get(state["case_id"])
        evidence = list(case["payload"]["evidence"])
        if case["source"] == "github":
            client = GitHub(self.settings)
            try:
                evidence = client.collect(case, self.store)
            finally:
                client.close()
        elif case["source"] == "demo":
            visual = screenshot(self.store, case["id"], case["scenario"])
            if visual:
                evidence.append(visual)
        self.store.event(
            case["id"],
            "collect",
            f"Preserved {len(evidence)} evidence items at commit {case['commit_sha'][:7]}.",
            {"count": len(evidence)},
            key="collected",
        )
        return {"evidence": evidence, "started": state.get("started", time.time())}

    def retrieval(self, state):
        case = self.store.get(state["case_id"])
        query = (
            case["test_name"]
            + " "
            + " ".join(e["content"][-2000:] for e in state["evidence"] if e["kind"] == "log")
        )
        result = retrieve(query, state["evidence"], self.settings)
        # A retained screenshot is always available to the vision agent within the bounded context.
        for e in state["evidence"]:
            if e["kind"] == "image" and not any(x["id"] == e["id"] for x in result):
                result = result[:7] + [{**e, "rank": 8, "retrieval_score": 0}]
                break
        self.store.event(
            case["id"],
            "retrieve",
            f"Ranked {len(result)} evidence items using {self.settings.retrieval_mode} retrieval.",
            {"ids": [e["id"] for e in result], "version": RETRIEVAL_VERSION},
            key="retrieved",
        )
        return {"retrieved": result}

    def diagnose(self, state):
        agents = Agents(self.settings, self.store, state["case_id"])
        result = agents.diagnose(state["retrieved"], state["case_id"])
        self.store.event(
            state["case_id"],
            "diagnose",
            f"Diagnosis agent proposed {len(result.hypotheses)} hypotheses.",
            {"mode": self.settings.model_mode, "prompt_version": PROMPT_VERSION},
            key="diagnosed",
        )
        return {"diagnosis": result.model_dump(), "usage": agents.usage}

    def plan(self, state):
        agents = Agents(self.settings, self.store, state["case_id"])
        agents.usage = list(state.get("usage", []))
        plans = agents.plan(Diagnosis.model_validate(state["diagnosis"]), state["retrieved"])
        self.store.event(
            state["case_id"],
            "plan",
            f"Experiment agent selected {len(plans.experiments)} bounded interventions.",
            {"plans": [p.model_dump() for p in plans.experiments]},
            key="planned",
        )
        return {"plans": [p.model_dump() for p in plans.experiments], "usage": agents.usage}

    def execute(self, state):
        case = self.store.get(state["case_id"])
        results = []
        for raw in state["plans"]:
            self.store.heartbeat(case["id"])
            result = run_experiment(
                self.settings, self.store, case, ExperimentPlan.model_validate(raw)
            )
            results.append(result.model_dump())
            self.store.event(
                case["id"],
                "experiment",
                f"{result.intervention}: {result.verdict} ({result.baseline_passes}/{result.repetitions} baseline, {result.intervention_passes}/{result.repetitions} intervention passes).",
                result.model_dump(),
                key=f"experiment:{result.hypothesis_id}:{result.intervention}",
            )
        return {"experiments": results}

    def report(self, state):
        hypotheses = [dict(h) for h in state["diagnosis"]["hypotheses"]]
        for h in hypotheses:
            experiment = next(
                (e for e in state["experiments"] if e["hypothesis_id"] == h["id"]), None
            )
            h["status"] = (
                experiment["verdict"]
                if experiment and experiment["verdict"] != "unavailable"
                else "inconclusive"
            )
        supported = [h for h in hypotheses if h["status"] == "supported"]
        outcome = "supported" if supported else "inconclusive"
        summary = (
            (
                supported[0]["title"]
                + ". Controlled runs support this mechanism in the recorded environment."
            )
            if supported
            else "The investigation did not establish an experiment-supported cause. Review the hypotheses and missing evidence before acting."
        )
        recorded = self.store.timeline(state["case_id"])
        usage = [e["data"] for e in recorded if e["stage"] == "model_usage"] or state.get(
            "usage", []
        )
        attempted_calls = sum(e["stage"] == "model_call" for e in recorded)
        input_tokens = sum(u.get("input_tokens") or 0 for u in usage)
        output_tokens = sum(u.get("output_tokens") or 0 for u in usage)
        cost = None
        if self.settings.model_mode == "baseline":
            cost = 0.0
        elif (
            self.settings.input_usd_per_million is not None
            and self.settings.output_usd_per_million is not None
            and attempted_calls == len(usage)
            and all(
                u.get("input_tokens") is not None and u.get("output_tokens") is not None
                for u in usage
            )
        ):
            cost = (
                input_tokens * self.settings.input_usd_per_million
                + output_tokens * self.settings.output_usd_per_million
            ) / 1_000_000
        missing = list(state["diagnosis"].get("missing_evidence", []))
        if any(e["verdict"] == "unavailable" for e in state["experiments"]):
            missing.append(
                "An isolated runner with the repository's reviewed reproduction manifest"
            )
        report = {
            "outcome": outcome,
            "summary": summary,
            "hypotheses": hypotheses,
            "experiments": state["experiments"],
            "evidence": state["evidence"],
            "retrieval": [
                {"id": e["id"], "rank": e["rank"], "score": e["retrieval_score"]}
                for e in state["retrieved"]
            ],
            "missing_evidence": missing,
            "limitations": [
                "Experiments support a mechanism in the recorded environment; they do not prove it is the only cause.",
                "Demo incidents are owned synthetic fixtures, not production customer incidents.",
            ],
            "metrics": {
                "duration_ms": int((time.time() - state["started"]) * 1000),
                "model_calls": attempted_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_model_cost_usd": cost,
            },
            "versions": {
                "model": self.settings.model_name
                if self.settings.model_mode == "chat"
                else "deterministic-signatures-v1",
                "mode": self.settings.model_mode,
                "prompt": PROMPT_VERSION,
                "retrieval": RETRIEVAL_VERSION,
                "retrieval_mode": self.settings.retrieval_mode,
            },
            "model_usage": usage,
            "evidence_digest": hashlib.sha256(
                "".join(e.get("sha", "") for e in state["evidence"]).encode()
            ).hexdigest(),
        }
        self.store.event(
            state["case_id"],
            "report",
            "Investigation report assembled with explicit evidence and uncertainty.",
            {"outcome": outcome},
            key="reported",
        )
        return {"report": report}

    def graph(self, saver):
        graph = StateGraph(State)
        for name, action in [
            ("collect", self.collect),
            ("retrieve", self.retrieval),
            ("diagnose", self.diagnose),
            ("plan", self.plan),
            ("execute", self.execute),
            ("report", self.report),
        ]:
            graph.add_node(name, action)
        path = [START, "collect", "retrieve", "diagnose", "plan", "execute", "report", END]
        for before, after in zip(path, path[1:], strict=False):
            graph.add_edge(before, after)
        return graph.compile(checkpointer=saver)

    def run(self, case_id):
        with self.store.checkpointer() as saver:
            graph = self.graph(saver)
            config = {"configurable": {"thread_id": case_id}, "recursion_limit": 20}
            state = graph.get_state(config)
            if (
                state.values
                and state.next
                and state.values.get("runtime", self.runtime()) != self.runtime()
            ):
                raise RuntimeError(
                    "Inference or retrieval configuration changed since this checkpoint. Start a new run to preserve version provenance."
                )
            if state.values and not state.next and state.values.get("report"):
                result = state.values
            else:
                result = graph.invoke(
                    None
                    if state.values
                    else {"case_id": case_id, "started": time.time(), "runtime": self.runtime()},
                    config,
                )
            self.store.finish(case_id, result["report"])


class Worker:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="failurelab-worker", daemon=True)
        self.thread.start()

    def tick(self):
        case_id = self.store.claim()
        if not case_id:
            return False
        lease_stop = threading.Event()

        def renew():
            while not lease_stop.wait(20):
                self.store.heartbeat(case_id)

        lease_thread = threading.Thread(target=renew, name="failurelab-lease", daemon=True)
        lease_thread.start()
        try:
            Investigator(self.settings, self.store).run(case_id)
        except Exception as exc:
            # Do not log raw provider errors, request objects, credentials, or repository content.
            logger.error("investigation_failed id=%s type=%s", case_id, type(exc).__name__)
            safe = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else f"{type(exc).__name__}: investigation failed. Check dependencies and integration configuration."
            )
            self.store.fail(case_id, safe)
        finally:
            lease_stop.set()
            lease_thread.join(timeout=2)
        return True

    def loop(self):
        while not self.stop_event.is_set():
            if not self.tick():
                self.stop_event.wait(1)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
