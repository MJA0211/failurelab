import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Beaker,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  Database,
  ExternalLink,
  FileText,
  FlaskConical,
  GitBranch,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Menu,
  Network,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  X,
  XCircle,
} from "lucide-react";
import { Github } from "./Github";
import { api, download, request } from "./api";
import type { Case, Config, Evaluation, Evidence } from "./types";

const cx = (...values: (string | false | undefined)[]) =>
  values.filter(Boolean).join(" ");
const short = (value: string) => value.replaceAll("_", " ");
const percent = (value: number) => `${Math.round(value * 100)}%`;
const duration = (ms: number) =>
  ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
const date = (value: string) =>
  new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const active = (c: Case) => ["running", "queued"].includes(c.status);

function Status({ value }: { value: string }) {
  return (
    <span className={cx("status", value)}>
      <span className="status-dot" />
      {short(value)}
    </span>
  );
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <CircleHelp size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Stat({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: ReactNode;
  note: string;
  icon: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-label">
        {label}
        {icon}
      </div>
      <strong>{value}</strong>
      <span>{note}</span>
    </div>
  );
}

function ArtifactImage({ caseId, name }: { caseId: string; name: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    let live = true;
    let object = "";
    request(`/artifacts/${encodeURIComponent(caseId)}/${name}`)
      .then((r) => r.blob())
      .then((blob) => {
        object = URL.createObjectURL(blob);
        if (live) setUrl(object);
        else URL.revokeObjectURL(object);
      })
      .catch(() => setError(true));
    return () => {
      live = false;
      if (object) URL.revokeObjectURL(object);
    };
  }, [caseId, name]);
  return error ? (
    <p className="muted">Screenshot unavailable.</p>
  ) : url ? (
    <img
      className="artifact-image"
      src={url}
      alt={`Recorded browser screenshot: ${name}`}
    />
  ) : (
    <div className="image-loading">
      <LoaderCircle className="spin" /> Loading screenshot
    </div>
  );
}

function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const element = ref.current;
    element?.querySelector<HTMLElement>("button, input, select")?.focus();
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab" && element) {
        const targets = [
          ...element.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input,select,textarea,a[href]",
          ),
        ];
        const first = targets[0],
          last = targets[targets.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.removeEventListener("keydown", listener);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function NewInvestigation({
  config,
  onCreated,
  close,
}: {
  config?: Config;
  onCreated: (id: string) => void;
  close: () => void;
}) {
  const [tab, setTab] = useState("demo");
  const [scenario, setScenario] = useState("overlay");
  const [repo, setRepo] = useState(config?.github_repositories[0] || "");
  const [runId, setRunId] = useState("");
  const [testName, setTestName] = useState("");
  const [manual, setManual] = useState(
    JSON.stringify(
      {
        title: "Investigate a failed browser test",
        repository: "my-team/my-app",
        commit_sha: "a13f8c2",
        test_name: "checkout completes",
        evidence: [
          {
            id: "e-log",
            title: "Test output",
            kind: "log",
            content: "Paste the actual failure output here.",
            source: "manual-upload",
          },
        ],
      },
      null,
      2,
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path =
        tab === "demo"
          ? "/demo"
          : tab === "github"
            ? "/integrations/github/import"
            : "/investigations";
      const body =
        tab === "demo"
          ? { scenario }
          : tab === "github"
            ? {
                repository: repo,
                run_id: Number(runId),
                ...(testName.trim() ? { test_name: testName.trim() } : {}),
              }
            : JSON.parse(manual);
      const result = await api<{ id: string }>(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onCreated(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="New investigation" close={close}>
      <div className="tabs">
        <button
          className={cx(tab === "demo" && "selected")}
          onClick={() => setTab("demo")}
        >
          Browser lab
        </button>
        <button
          className={cx(tab === "github" && "selected")}
          onClick={() => setTab("github")}
        >
          GitHub Actions
        </button>
        <button
          className={cx(tab === "manual" && "selected")}
          onClick={() => setTab("manual")}
        >
          Evidence JSON
        </button>
      </div>
      <form onSubmit={submit}>
        {tab === "demo" ? (
          <>
            <p className="muted">
              Run a real Chromium experiment against an owned test application.
              No API key needed.
            </p>
            <div className="scenario-options">
              {[
                [
                  "overlay",
                  "An overlay blocks checkout",
                  "Visual evidence + controlled click experiment",
                ],
                [
                  "selector",
                  "A selector was renamed",
                  "DOM evidence + locator restoration",
                ],
                [
                  "api_contract",
                  "An API response changed",
                  "Response evidence + contract restoration",
                ],
                [
                  "unknown",
                  "Critical artifacts are missing",
                  "Test abstention and uncertainty handling",
                ],
              ].map(([id, title, subtitle]) => (
                <label
                  key={id}
                  className={cx("scenario", scenario === id && "chosen")}
                >
                  <input
                    type="radio"
                    name="scenario"
                    value={id}
                    checked={scenario === id}
                    onChange={() => setScenario(id)}
                  />
                  <span>
                    <strong>{title}</strong>
                    <small>{subtitle}</small>
                  </span>
                </label>
              ))}
            </div>
            <div className="notice">
              <Beaker size={17} />
              <span>
                These incidents are synthetic. Screenshots and experiment
                results are generated by actual browser runs.
              </span>
            </div>
          </>
        ) : tab === "github" ? (
          <>
            <p className="muted">
              Import a failed workflow run and preserve evidence at its exact
              commit.
            </p>
            {!config?.github_configured && (
              <div className="notice warning">
                <TriangleAlert size={18} />
                <span>
                  Add the repository to FAILURELAB_GITHUB_REPOSITORIES and
                  restart the server first. Private repositories also require a
                  GitHub token.
                </span>
              </div>
            )}
            <label className="field">
              Repository
              <input
                required
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="owner/repository"
                pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
              />
            </label>
            <label className="field">
              Workflow run ID
              <input
                required
                type="number"
                min="1"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                placeholder="123456789"
              />
            </label>
            <small className="muted">
              Find the run ID in the GitHub Actions run URL.
            </small>
            <label className="field">
              Test name (optional)
              <input
                value={testName}
                onChange={(e) => setTestName(e.target.value)}
                placeholder="Exact Playwright test title for remote reproduction"
                maxLength={300}
              />
            </label>
          </>
        ) : (
          <>
            <p className="muted">
              Submit a versioned evidence snapshot. External code runs only
              through a configured isolated runner.
            </p>
            <label className="field">
              Investigation payload
              <textarea
                className="code-input"
                rows={14}
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                required
                spellCheck={false}
              />
            </label>
          </>
        )}
        {error && (
          <div className="notice danger" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Play size={16} />
            )}
            {busy ? "Creating…" : "Start investigation"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Dashboard({
  cases,
  search,
  onOpen,
  onNew,
}: {
  cases: Case[];
  search: string;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const [filter, setFilter] = useState("all");
  const completed = cases.filter((c) => c.status === "completed");
  const supported = completed.filter(
    (c) => c.result?.outcome === "supported",
  ).length;
  const experiments = completed.reduce(
    (n, c) => n + (c.result?.experiments.length || 0),
    0,
  );
  const shown = cases.filter(
    (c) =>
      (!search ||
        `${c.title} ${c.repository} ${c.commit_sha}`
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (filter === "all" ||
        (filter === "active"
          ? active(c)
          : filter === "supported"
            ? c.result?.outcome === "supported"
            : c.result?.outcome === "inconclusive")),
  );
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">YOUR INVESTIGATION WORKSPACE</div>
        <div className="heading-row">
          <div>
            <h1>Evidence over guesswork.</h1>
            <p>Understand what broke. Test why. Keep the proof.</p>
          </div>
          <button className="button primary" onClick={onNew}>
            <Plus size={17} />
            New investigation
          </button>
        </div>
      </div>
      <div className="stats">
        <Stat
          label="Investigations"
          value={cases.length}
          note={`${cases.filter(active).length} in progress`}
          icon={<Layers3 size={18} />}
        />
        <Stat
          label="Experiment-supported"
          value={supported}
          note={`${completed.length} completed investigations`}
          icon={<ShieldCheck size={18} />}
        />
        <Stat
          label="Experiments executed"
          value={experiments}
          note="Baseline and intervention comparisons"
          icon={<FlaskConical size={18} />}
        />
        <Stat
          label="Needs more evidence"
          value={completed.length - supported}
          note="Uncertainty stays visible"
          icon={<CircleHelp size={18} />}
        />
      </div>
      <div className="workspace-grid">
        <section className="panel investigations-panel">
          <div className="panel-heading">
            <h2>
              Investigations <span className="count">{cases.length}</span>
            </h2>
            <span className="live">
              <i />
              Live updates
            </span>
          </div>
          <div className="filter-row">
            {[
              ["all", "All"],
              ["active", "In progress"],
              ["supported", "Supported"],
              ["inconclusive", "Inconclusive"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={cx("filter", filter === key && "chosen")}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="list-label">
            <span>FAILURE / REPOSITORY</span>
            <span>OUTCOME</span>
          </div>
          {shown.length ? (
            shown.map((c) => (
              <button
                key={c.id}
                className="case-row"
                onClick={() => onOpen(c.id)}
              >
                <div
                  className={cx(
                    "case-icon",
                    c.result?.outcome === "supported" && "good",
                  )}
                >
                  {active(c) ? (
                    <LoaderCircle size={18} className="spin" />
                  ) : c.result?.outcome === "supported" ? (
                    <CheckCheck size={19} />
                  ) : c.status === "failed" ? (
                    <XCircle size={19} />
                  ) : (
                    <CircleHelp size={19} />
                  )}
                </div>
                <div className="case-copy">
                  <strong>{c.title}</strong>
                  <div className="case-meta">
                    <Github size={12} />
                    {c.repository}
                    <span>·</span>
                    <code>{c.commit_sha.slice(0, 7)}</code>
                    <span className="source-tag">
                      {c.source === "demo"
                        ? "OWNED FIXTURE"
                        : c.source.toUpperCase()}
                    </span>
                  </div>
                </div>
                <div className="case-outcome">
                  <Status value={c.result?.outcome || c.status} />
                  <small>{date(c.created_at)}</small>
                </div>
                <ChevronRight className="row-chevron" size={17} />
              </button>
            ))
          ) : (
            <Empty
              title={search ? "No matching investigations" : "Nothing here yet"}
            >
              {search
                ? "Try a different repository, commit, or failure description."
                : "Start a browser lab investigation or import a GitHub workflow."}
            </Empty>
          )}
          <div className="panel-footer">
            <LockKeyhole size={13} />
            Evidence is scoped to the investigation and pinned to its commit.
          </div>
        </section>
        <aside className="right-column">
          <section className="process-card">
            <div className="eyebrow">THE FAILURELAB METHOD</div>
            <h2>
              A diagnosis should
              <br />
              survive an experiment.
            </h2>
            <div className="process-steps">
              {[
                [
                  FileText,
                  "Collect the evidence",
                  "Logs, code, screenshots, and traces.",
                ],
                [
                  Network,
                  "Build a hypothesis",
                  "Retrieve context. Cite every explanation.",
                ],
                [
                  FlaskConical,
                  "Try to disprove it",
                  "Compare baseline and intervention.",
                ],
                [
                  ShieldCheck,
                  "Leave a clear record",
                  "Supported, contradicted, or inconclusive.",
                ],
              ].map(([Icon, title, text], i) => {
                const Component = Icon as typeof FileText;
                return (
                  <div className="process-step" key={i}>
                    <span>
                      <Component size={17} />
                    </span>
                    <div>
                      <strong>{title as string}</strong>
                      <p>{text as string}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <button className="text-button" onClick={onNew}>
              Try a browser experiment <ArrowRight size={15} />
            </button>
          </section>
          <section className="quiet-card">
            <Beaker size={20} />
            <div>
              <strong>A transparent starting point</strong>
              <p>
                Owned fixtures make the workflow reproducible. Live integrations
                and model modes are labeled throughout.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </>
  );
}

function CaseDetail({
  item,
  refresh,
  back,
  onError,
}: {
  item: Case;
  refresh: () => void;
  back: () => void;
  onError: (s: string) => void;
}) {
  const [tab, setTab] = useState("overview");
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const result = item.result;
  const evidence = result?.evidence || item.payload?.evidence || [];
  const chosen = evidence.find((e) => e.id === selectedEvidence) || evidence[0];
  function cite(id: string) {
    setSelectedEvidence(id);
    setTab("evidence");
  }
  async function exportReport(format: string) {
    try {
      await download(
        `/investigations/${encodeURIComponent(item.id)}/report?format=${format}`,
        `${item.id}.${format === "markdown" ? "md" : "json"}`,
      );
    } catch (e) {
      onError((e as Error).message);
    }
  }
  return (
    <>
      <button className="back-link" onClick={back}>
        <ArrowLeft size={15} />
        All investigations
      </button>
      <div className="detail-heading">
        <div>
          <div className="eyebrow">
            {item.id}{" "}
            <span>
              {" "}
              /{" "}
              {item.source === "demo"
                ? "OWNED SYNTHETIC INCIDENT"
                : item.source.toUpperCase()}
            </span>
          </div>
          <h1>{item.title}</h1>
          <div className="detail-meta">
            <Github size={15} />
            {item.repository}
            <span>·</span>
            <GitBranch size={14} />
            <code>{item.commit_sha.slice(0, 7)}</code>
            <span>·</span>
            {date(item.created_at)}
          </div>
        </div>
        <Status value={result?.outcome || item.status} />
      </div>
      {active(item) && (
        <div className="notice progress">
          <LoaderCircle className="spin" size={19} />
          <div>
            <strong>Investigation in progress · {short(item.stage)}</strong>
            <p>
              Evidence and completed stages are saved as the workflow advances.
            </p>
          </div>
        </div>
      )}
      {item.status === "failed" && (
        <div className="notice danger">
          <TriangleAlert size={20} />
          <div>
            <strong>Investigation stopped</strong>
            <p>{item.error}</p>
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  await api(
                    `/investigations/${encodeURIComponent(item.id)}/retry`,
                    {
                      method: "POST",
                    },
                  );
                  refresh();
                } catch (e) {
                  onError((e as Error).message);
                }
              }}
            >
              Retry from checkpoint
            </button>
          </div>
        </div>
      )}
      <div className="detail-toolbar">
        <div className="tabs">
          {[
            ["overview", "Overview"],
            ["evidence", `Evidence (${evidence.length})`],
            ["experiments", `Experiments (${result?.experiments.length || 0})`],
            ["timeline", "Activity"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={cx(tab === key && "selected")}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {(result || item.status === "failed") && (
          <div className="toolbar-actions">
            <button
              className="button small secondary"
              onClick={async () => {
                try {
                  const next = await api<{ id: string }>(
                    `/investigations/${encodeURIComponent(item.id)}/rerun`,
                    { method: "POST" },
                  );
                  location.assign(`?case=${next.id}`);
                } catch (e) {
                  onError((e as Error).message);
                }
              }}
            >
              <Play size={14} />
              Run again
            </button>
            <button
              className="button small secondary"
              disabled={!result}
              onClick={() => exportReport("markdown")}
            >
              <ArrowDownToLine size={14} />
              Export
            </button>
            <button
              className="button small primary"
              disabled={!result}
              onClick={() => setReviewing(true)}
            >
              <Check size={14} />
              Review
            </button>
          </div>
        )}
      </div>
      {tab === "overview" && (
        <div className="detail-grid">
          <div>
            {result ? (
              <>
                <section className={cx("conclusion", result.outcome)}>
                  <div className="section-kicker">
                    <ShieldCheck size={17} />
                    INVESTIGATION FINDING
                  </div>
                  <h2>{result.summary}</h2>
                  <p>
                    {result.outcome === "supported"
                      ? "Supported in the recorded environment. Review the experiment and its limits before applying a change."
                      : "The system has kept uncertainty visible. Additional evidence is needed to establish a cause."}
                  </p>
                </section>
                <div className="section-title">
                  <h2>Hypotheses</h2>
                  <span>{result.hypotheses.length} evaluated</span>
                </div>
                {result.hypotheses.map((h, i) => (
                  <section className="hypothesis panel" key={h.id}>
                    <div className="hypothesis-head">
                      <span className="hypothesis-number">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <Status value={h.status} />
                    </div>
                    <h3>{h.title}</h3>
                    <p>{h.explanation}</p>
                    <div className="citation-row">
                      <small>SUPPORTING EVIDENCE</small>
                      {h.evidence_ids.map((id) => (
                        <button onClick={() => cite(id)} key={id}>
                          <FileText size={12} />
                          {id}
                          <ChevronRight size={12} />
                        </button>
                      ))}
                    </div>
                  </section>
                ))}
                {result.missing_evidence.length > 0 && (
                  <section className="notice warning">
                    <CircleHelp size={20} />
                    <div>
                      <strong>What is still needed</strong>
                      <ul>
                        {result.missing_evidence.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  </section>
                )}
              </>
            ) : (
              <Empty title="Building the evidence trail">
                The report will appear after collection, diagnosis, and bounded
                experiments finish.
              </Empty>
            )}
          </div>
          <aside>
            <section className="panel run-details">
              <h3>Run details</h3>
              <dl>
                <dt>Test</dt>
                <dd>{item.test_name}</dd>
                <dt>Commit</dt>
                <dd className="mono break">{item.commit_sha}</dd>
                <dt>Engine</dt>
                <dd>
                  {result?.versions.mode === "baseline"
                    ? "Deterministic baseline"
                    : result?.versions.model || "Awaiting diagnosis"}
                </dd>
                <dt>Retrieval</dt>
                <dd>{result?.versions.retrieval_mode || "Pending"}</dd>
                <dt>Duration</dt>
                <dd>
                  {result
                    ? duration(result.metrics.duration_ms)
                    : "In progress"}
                </dd>
                <dt>Model calls</dt>
                <dd>{result?.metrics.model_calls ?? "—"}</dd>
                <dt>Estimated model cost</dt>
                <dd>
                  {result
                    ? result.metrics.estimated_model_cost_usd === null
                      ? "Pricing not configured"
                      : `$${result.metrics.estimated_model_cost_usd.toFixed(4)}`
                    : "—"}
                </dd>
              </dl>
              <small>Model cost excludes browser compute and hosting.</small>
            </section>
            {evidence.find((e) => e.kind === "image") && (
              <section className="panel screenshot-card">
                <div className="panel-heading">
                  <h3>At the point of failure</h3>
                </div>
                <button
                  className="image-button"
                  onClick={() =>
                    cite(evidence.find((e) => e.kind === "image")!.id)
                  }
                >
                  <ArtifactImage
                    caseId={item.id}
                    name={evidence.find((e) => e.kind === "image")!.artifact!}
                  />
                </button>
                <p>Actual browser capture. Open to inspect evidence.</p>
              </section>
            )}
            {(item.reviews?.length || 0) > 0 && (
              <section className="panel review-history">
                <h3>Human review</h3>
                {item.reviews?.map((r) => (
                  <div key={r.id}>
                    <Status value={r.decision} />
                    <p>{r.note}</p>
                    <small>{date(r.at)}</small>
                  </div>
                ))}
              </section>
            )}
          </aside>
        </div>
      )}
      {tab === "evidence" && (
        <div className="evidence-layout">
          <section className="panel evidence-list">
            <div className="panel-heading">
              <h3>Source evidence</h3>
              <Database size={16} />
            </div>
            {evidence.map((e) => (
              <button
                className={cx(chosen?.id === e.id && "selected")}
                onClick={() => setSelectedEvidence(e.id)}
                key={e.id}
              >
                <FileText size={17} />
                <span>
                  <strong>{e.title}</strong>
                  <small>
                    {e.kind} · {e.id}
                  </small>
                </span>
                <ChevronRight size={14} />
              </button>
            ))}
          </section>
          {chosen ? (
            <EvidenceDetail item={chosen} caseId={item.id} onError={onError} />
          ) : (
            <Empty title="No evidence collected yet" />
          )}
        </div>
      )}
      {tab === "experiments" && (
        <>
          {result?.experiments.length ? (
            result.experiments.map((e) => (
              <section className="panel experiment-card" key={e.hypothesis_id}>
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">
                      {e.hypothesis_id} / CONTROLLED INTERVENTION
                    </div>
                    <h2>{short(e.intervention)}</h2>
                  </div>
                  <Status value={e.verdict} />
                </div>
                <div className="experiment-body">
                  <div className="comparison">
                    <div>
                      <span>BASELINE</span>
                      <strong>
                        {e.baseline_passes}
                        <small> / {e.repetitions}</small>
                      </strong>
                      <p>passing runs</p>
                      <div className="run-dots">
                        {Array.from({ length: e.repetitions }, (_, i) => (
                          <span
                            key={i}
                            className={i < e.baseline_passes ? "pass" : "fail"}
                          >
                            {i < e.baseline_passes ? (
                              <Check size={14} />
                            ) : (
                              <X size={14} />
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                    <ArrowRight size={24} />
                    <div>
                      <span>WITH INTERVENTION</span>
                      <strong>
                        {e.intervention_passes}
                        <small> / {e.repetitions}</small>
                      </strong>
                      <p>passing runs</p>
                      <div className="run-dots">
                        {Array.from({ length: e.repetitions }, (_, i) => (
                          <span
                            key={i}
                            className={
                              i < e.intervention_passes ? "pass" : "fail"
                            }
                          >
                            {i < e.intervention_passes ? (
                              <Check size={14} />
                            ) : (
                              <X size={14} />
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <pre className="terminal">{e.observations.join("\n")}</pre>
                  <div className="artifact-grid">
                    {e.artifacts
                      .filter((a) => a.endsWith(".png"))
                      .map((a) => (
                        <div key={a}>
                          <small>
                            {a.includes("baseline")
                              ? "Baseline capture"
                              : "Intervention capture"}
                          </small>
                          <ArtifactImage caseId={item.id} name={a} />
                        </div>
                      ))}
                  </div>
                  <div className="experiment-footer">
                    <span>
                      <Clock3 size={14} />
                      {duration(e.duration_ms)} ·{" "}
                      {e.environment.chromium
                        ? `Chromium ${e.environment.chromium}`
                        : e.environment.runner}
                    </span>
                    {e.artifacts
                      .filter((a) => a.endsWith(".zip"))
                      .map((a) => (
                        <button
                          className="text-button"
                          key={a}
                          onClick={() =>
                            download(
                              `/artifacts/${encodeURIComponent(item.id)}/${a}`,
                              a,
                            ).catch((err) => onError(err.message))
                          }
                        >
                          <ArrowDownToLine size={13} />
                          {a.includes("baseline")
                            ? "Baseline trace"
                            : "Intervention trace"}
                        </button>
                      ))}
                  </div>
                </div>
              </section>
            ))
          ) : (
            <Empty title="No experiments to show">
              Unknown causes require better evidence before a meaningful
              intervention can be designed.
            </Empty>
          )}
          <div className="notice">
            <CircleHelp size={18} />
            <span>
              Fresh browser contexts and interleaved runs reduce contamination.
              Small run counts do not establish statistical certainty for
              intermittent failures.
            </span>
          </div>
        </>
      )}
      {tab === "timeline" && (
        <section className="panel timeline">
          <div className="panel-heading">
            <h2>Investigation activity</h2>
            <span className="muted">Durable event history</span>
          </div>
          {item.events?.map((event, i) => (
            <div className="timeline-event" key={event.id}>
              <div className="timeline-marker">
                {i === (item.events?.length || 0) - 1 && active(item) ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <Check size={14} />
                )}
              </div>
              <div>
                <span className="event-stage">{short(event.stage)}</span>
                <p>{event.message}</p>
                <small>{date(event.at)}</small>
              </div>
            </div>
          ))}
        </section>
      )}
      {reviewing && (
        <ReviewDialog
          item={item}
          close={() => setReviewing(false)}
          done={() => {
            setReviewing(false);
            refresh();
          }}
        />
      )}
    </>
  );
}

function EvidenceDetail({
  item,
  caseId,
  onError,
}: {
  item: Evidence;
  caseId: string;
  onError: (s: string) => void;
}) {
  return (
    <section className="panel evidence-view">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            {item.kind.toUpperCase()} / {item.id}
          </span>
          <h2>{item.title}</h2>
        </div>
        {item.source.startsWith("https://github.com/") && (
          <a
            className="icon-button"
            href={item.source}
            target="_blank"
            rel="noreferrer"
            aria-label="Open source on GitHub"
          >
            <ExternalLink size={17} />
          </a>
        )}
      </div>
      <div className="evidence-source">{item.source}</div>
      {item.kind === "image" && item.artifact ? (
        <ArtifactImage caseId={caseId} name={item.artifact} />
      ) : (
        <pre className="evidence-code">
          {item.content.split("\n").map((line, i) => (
            <span key={i}>
              <i>{i + 1}</i>
              <code>{line || " "}</code>
            </span>
          ))}
        </pre>
      )}
      <div className="evidence-hash">
        <LockKeyhole size={14} />
        <span>
          SHA-256 <code>{item.sha || "Not yet hashed"}</code>
        </span>
      </div>
      {item.artifact?.endsWith(".zip") && (
        <button
          className="button secondary"
          onClick={() =>
            download(
              `/artifacts/${encodeURIComponent(caseId)}/${item.artifact}`,
              item.artifact!,
            ).catch((e) => onError(e.message))
          }
        >
          <ArrowDownToLine size={15} />
          Download original trace
        </button>
      )}
    </section>
  );
}

function ReviewDialog({
  item,
  close,
  done,
}: {
  item: Case;
  close: () => void;
  done: () => void;
}) {
  const [decision, setDecision] = useState("accepted");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/investigations/${encodeURIComponent(item.id)}/reviews`, {
        method: "POST",
        body: JSON.stringify({ decision, note }),
      });
      done();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Review the investigation" close={close}>
      <p className="muted">
        Your decision is recorded alongside the original evidence. It does not
        change experimental results.
      </p>
      <form onSubmit={submit}>
        <label className="field">
          Decision
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
          >
            <option value="accepted">Accept the finding</option>
            <option value="rejected">Reject the finding</option>
            <option value="needs_evidence">Request more evidence</option>
          </select>
        </label>
        <label className="field">
          Review note
          <textarea
            minLength={3}
            maxLength={2000}
            required
            rows={4}
            placeholder="Explain your decision and any remaining uncertainty…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save review"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Evaluations() {
  const [data, setData] = useState<Evaluation>();
  const [error, setError] = useState("");
  useEffect(() => {
    api<Evaluation>("/evaluations")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">MEASURE, THEN IMPROVE</div>
        <h1>The evaluation bench.</h1>
        <p>Reproducible cases. Explicit baselines. Results you can inspect.</p>
      </div>
      {error ? (
        <div role="alert" className="notice danger">
          {error}
        </div>
      ) : !data ? (
        <div className="loading">
          <LoaderCircle className="spin" />
          Loading evaluation results
        </div>
      ) : !data.available ? (
        <Empty title="No benchmark has been run">{data.message}</Empty>
      ) : (
        <>
          <div className="stats">
            <Stat
              label="Authored cases"
              value={data.case_count}
              note="Signature regression dataset"
              icon={<Database size={18} />}
            />
            <Stat
              label="Configurations"
              value={data.variants.length}
              note="Log-only and retrieved context"
              icon={<Layers3 size={18} />}
            />
            <Stat
              label="Evaluation mode"
              value={<span className="stat-word">{data.mode}</span>}
              note="Recorded explicitly for each run"
              icon={<Beaker size={18} />}
            />
            <Stat
              label="Run duration"
              value={duration(data.duration_ms)}
              note={date(data.generated_at)}
              icon={<Clock3 size={18} />}
            />
          </div>
          <div className="notice warning">
            <TriangleAlert size={18} />
            <span>
              This authored regression set checks known failure signatures. It
              does not establish held-out or production accuracy.
            </span>
          </div>
          <section className="panel evaluation-table">
            <div className="panel-heading">
              <h2>Configuration comparison</h2>
              <span className="mono">{data.dataset}</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Configuration</th>
                    <th>Top-1 accuracy</th>
                    <th>95% interval</th>
                    <th>Valid citation IDs</th>
                    <th>Unknown-case abstention</th>
                  </tr>
                </thead>
                <tbody>
                  {data.variants.map((v) => (
                    <tr key={v.name}>
                      <td>
                        <strong>{short(v.name)}</strong>
                        <small>{v.cases} authored cases</small>
                      </td>
                      <td>
                        <div className="metric-bar">
                          <span style={{ width: percent(v.top1_accuracy) }} />
                        </div>
                        {percent(v.top1_accuracy)}
                      </td>
                      <td>{v.accuracy_interval_95.map(percent).join(" – ")}</td>
                      <td>{percent(v.citation_validity)}</td>
                      <td>{percent(v.unknown_abstention_accuracy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="workspace-grid eval-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>Case-level results</h2>
                <span className="count">{data.case_count}</span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Expected</th>
                      <th>Predicted</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results
                      .filter((r) => r.variant === "retrieval")
                      .map((r) => (
                        <tr key={r.id}>
                          <td className="mono">{r.id}</td>
                          <td>{short(r.expected)}</td>
                          <td>{short(r.predicted)}</td>
                          <td>
                            {r.correct ? (
                              <Check className="green" size={17} />
                            ) : (
                              <X className="red" size={17} />
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="panel evaluation-notes">
              <h3>How to read these results</h3>
              {data.limitations.map((x, i) => (
                <p key={x}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  {x}
                </p>
              ))}
              <div className="command">
                <Terminal size={15} />
                <code>uv run failurelab evaluate</code>
              </div>
              <small>
                Run with --model to evaluate configured live inference. That
                consumes model tokens.
              </small>
            </section>
          </div>
        </>
      )}
    </>
  );
}

function Integrations({
  config,
  onImport,
}: {
  config?: Config;
  onImport: () => void;
}) {
  const [name, setName] = useState("@playwright/test");
  const [version, setVersion] = useState("1.51.0");
  const [metadata, setMetadata] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function lookup(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setMetadata(
        JSON.stringify(
          await api(
            `/integrations/npm?package=${encodeURIComponent(name)}&version=${encodeURIComponent(version)}`,
          ),
          null,
          2,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">REAL SOURCES, CLEAR BOUNDARIES</div>
        <h1>Connect the evidence.</h1>
        <p>Bring failing runs into a versioned, reproducible investigation.</p>
      </div>
      <div className="integration-grid">
        <section className="panel integration-card">
          <div className="integration-icon">
            <Github size={27} />
          </div>
          <div className="integration-title">
            <h2>GitHub Actions</h2>
            <Status
              value={config?.github_configured ? "connected" : "not configured"}
            />
          </div>
          <p>
            Collect workflow metadata, failed job logs, commit patches, and
            retained diagnostic artifacts.
          </p>
          <div className="config-block">
            <small>ALLOWED REPOSITORIES</small>
            {config?.github_repositories.length ? (
              config.github_repositories.map((r) => <code key={r}>{r}</code>)
            ) : (
              <code>FAILURELAB_GITHUB_REPOSITORIES=owner/repo</code>
            )}
          </div>
          <p className="small-copy">
            Private repositories require a server-side token. Workflow webhooks
            use HMAC signature validation and deduplicate delivery.
          </p>
          <button className="button secondary" onClick={onImport}>
            <Plus size={15} />
            Import workflow run
          </button>
        </section>
        <section className="panel integration-card">
          <div className="integration-icon green-icon">
            <FlaskConical size={27} />
          </div>
          <div className="integration-title">
            <h2>Isolated execution</h2>
            <Status
              value={config?.runner_configured ? "connected" : "local fixtures"}
            />
          </div>
          <p>
            Owned fixtures run in network-blocked browser contexts. External
            repositories require a separately isolated runner.
          </p>
          <div className="config-block">
            <small>EXECUTION BOUNDARY</small>
            <code>
              {config?.runner_configured
                ? "Remote runner configured"
                : "Repository execution disabled locally"}
            </code>
          </div>
          <p className="small-copy">
            The API server never clones or executes imported repository code.
            Runner setup and its manifest contract are documented in
            docs/runner-protocol.md.
          </p>
        </section>
        <section className="panel integration-card npm-card">
          <div className="integration-title">
            <h2>
              <Code2 size={23} />
              npm registry
            </h2>
            <span className="source-tag">PUBLIC API</span>
          </div>
          <p>Inspect the exact dependency version involved in a failure.</p>
          <form className="npm-form" onSubmit={lookup}>
            <label className="field">
              Package
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              Version
              <input
                required
                value={version}
                onChange={(e) => setVersion(e.target.value)}
              />
            </label>
            <button className="button secondary" disabled={busy}>
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Search size={15} />
              )}
              Look up
            </button>
          </form>
          {error && (
            <div className="notice danger" role="alert">
              {error}
            </div>
          )}
          {metadata && <pre className="terminal">{metadata}</pre>}
        </section>
      </div>
    </>
  );
}

function Configuration({
  config,
  onAuth,
}: {
  config?: Config;
  onAuth: () => void;
}) {
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">REPRODUCIBILITY STARTS HERE</div>
        <h1>Workspace configuration.</h1>
        <p>
          Active server settings. Credentials are never exposed to this
          interface.
        </p>
      </div>
      <section className="panel settings-panel">
        <div className="panel-heading">
          <h2>Runtime</h2>
          <span className="source-tag">READ ONLY</span>
        </div>
        {[
          ["Inference mode", config?.model_mode],
          ["Model", config?.model_name],
          ["Vision input", config?.vision_enabled ? "Enabled" : "Disabled"],
          ["Retrieval", config?.retrieval_mode],
          ["Maximum model calls", config?.max_model_calls],
          ["Maximum experiments", config?.max_experiments],
          [
            "Background worker",
            config?.worker_enabled ? "Enabled" : "Disabled",
          ],
          [
            "Authentication",
            config?.authentication
              ? "Bearer token required"
              : "Local loopback workspace",
          ],
          ["Version", config?.version],
        ].map(([label, value]) => (
          <div className="setting-row" key={label}>
            <strong>{label}</strong>
            <span>{value ?? "—"}</span>
          </div>
        ))}
        <div className="panel-footer">
          Change environment variables in .env and restart the server to apply
          settings.
        </div>
      </section>
      <section className="notice">
        <LockKeyhole size={20} />
        <div>
          <strong>Workspace access token</strong>
          <p>
            If this server requires authentication, set your browser session
            token here. It is stored only for this tab session.
          </p>
          <button className="button secondary" onClick={onAuth}>
            Set access token
          </button>
        </div>
      </section>
      <section className="panel docs-card">
        <BookOpen size={24} />
        <div>
          <h3>Everything needed to operate the system</h3>
          <p>
            See README.md for setup; docs/architecture.md for system design;
            docs/evaluation.md for methodology; and docs/deployment.md for
            operational checks.
          </p>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="text-button"
          >
            Explore the API reference <ExternalLink size={14} />
          </a>
        </div>
      </section>
    </>
  );
}

export default function App() {
  const [page, setPage] = useState("investigations");
  const [cases, setCases] = useState<Case[]>([]);
  const [config, setConfig] = useState<Config>();
  const [caseId, setCaseId] = useState<string | null>(() => {
    const candidate = new URLSearchParams(location.search).get("case");
    return candidate && /^inv-[a-f0-9]{12}$/.test(candidate) ? candidate : null;
  });
  const [item, setItem] = useState<Case>();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [auth, setAuth] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [mobile, setMobile] = useState(false);
  async function refresh() {
    try {
      const [all, configuration] = await Promise.all([
        api<Case[]>("/investigations"),
        api<Config>("/config"),
      ]);
      setCases(all);
      setConfig(configuration);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await refresh();
      if (!cancelled) timer = setTimeout(poll, 2000);
    }
    void poll();
    const onAuth = () => setAuth(true);
    window.addEventListener("failurelab-auth", onAuth);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      window.removeEventListener("failurelab-auth", onAuth);
    };
  }, []);
  useEffect(() => {
    if (!caseId) {
      setItem(undefined);
      return;
    }
    const selectedCaseId = caseId;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const c = await api<Case>(
          `/investigations/${encodeURIComponent(selectedCaseId)}`,
        );
        if (live) setItem(c);
      } catch (e) {
        if (live) setError((e as Error).message);
      }
      if (live) timer = setTimeout(poll, 1500);
    }
    setItem(undefined);
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [caseId]);
  function open(id: string) {
    setCaseId(id);
    setPage("investigations");
    history.replaceState(null, "", `?case=${id}`);
    window.scrollTo(0, 0);
  }
  function navigate(next: string) {
    setPage(next);
    setCaseId(null);
    history.replaceState(null, "", "/");
    setMobile(false);
    setSearch("");
  }
  async function refreshDetail() {
    await refresh();
    if (caseId)
      setItem(await api<Case>(`/investigations/${encodeURIComponent(caseId)}`));
  }
  const navigation = [
    { key: "investigations", label: "Investigations", icon: Layers3 },
    { key: "evaluations", label: "Evaluation bench", icon: Activity },
    { key: "integrations", label: "Integrations", icon: Network },
    { key: "settings", label: "Configuration", icon: Settings2 },
  ];
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={cx("sidebar", mobile && "mobile-open")}>
        <button
          className="brand"
          onClick={() => navigate("investigations")}
          aria-label="FailureLab home"
        >
          <div className="brand-symbol">
            <FlaskConical size={24} />
          </div>
          <span>
            failurelab<span className="brand-dot">.</span>
          </span>
        </button>
        <button
          className="workspace-switch"
          onClick={() => navigate("settings")}
        >
          <span className="workspace-avatar">FL</span>
          <span>
            Engineering workspace<small>Local workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {navigation.map((n) => (
            <button
              key={n.key}
              className={cx(page === n.key && "selected")}
              onClick={() => navigate(n.key)}
            >
              <n.icon size={18} />
              {n.label}
              {n.key === "investigations" && <span>{cases.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="engine-card">
            <span className="live">
              <i />
              {config?.model_mode === "chat"
                ? "Model engine"
                : "Baseline engine"}
            </span>
            <p>
              {config?.model_mode === "chat"
                ? config.model_name
                : "Deterministic diagnostics. Real browser experiments."}
            </p>
            <button onClick={() => navigate("settings")}>
              View configuration <ArrowRight size={13} />
            </button>
          </div>
          <a href="/docs" target="_blank" rel="noreferrer">
            <BookOpen size={16} />
            API reference
            <ExternalLink size={13} />
          </a>
          <div className="sidebar-footnote">
            FAILURELAB <span>v{config?.version || "0.1.1"}</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobile(!mobile)}
              aria-label="Toggle navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{navigation.find((n) => n.key === page)?.label}</strong>
          </div>
          <div className="topbar-right">
            {page === "investigations" && !caseId && (
              <label className="search">
                <Search size={16} />
                <input
                  aria-label="Search investigations"
                  placeholder="Search investigations…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <kbd>/</kbd>
              </label>
            )}
            <span className="local-badge">
              <span />
              Local workspace
            </span>
            <button
              className="avatar"
              onClick={() => navigate("settings")}
              aria-label="Workspace settings"
            >
              FL
            </button>
          </div>
        </header>
        <main id="main">
          {error && (
            <div className="notice danger global-error" role="alert">
              <TriangleAlert size={18} />
              <span>{error}</span>
              <button
                className="icon-button"
                onClick={() => setError("")}
                aria-label="Dismiss error"
              >
                <X size={16} />
              </button>
            </div>
          )}
          {loading ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              Connecting to your workspace…
            </div>
          ) : page === "investigations" ? (
            caseId ? (
              item ? (
                <CaseDetail
                  key={caseId}
                  item={item}
                  refresh={() => {
                    void refreshDetail();
                  }}
                  back={() => navigate("investigations")}
                  onError={setError}
                />
              ) : (
                <div className="loading">
                  <LoaderCircle className="spin" />
                  Loading investigation…
                </div>
              )
            ) : (
              <Dashboard
                cases={cases}
                search={search}
                onOpen={open}
                onNew={() => setCreating(true)}
              />
            )
          ) : page === "evaluations" ? (
            <Evaluations />
          ) : page === "integrations" ? (
            <Integrations config={config} onImport={() => setCreating(true)} />
          ) : (
            <Configuration config={config} onAuth={() => setAuth(true)} />
          )}
          <footer className="main-footer">
            <span>
              <ShieldCheck size={13} />
              Built around evidence. Honest about uncertainty.
            </span>
            <span>FailureLab / Engineering workspace</span>
          </footer>
        </main>
      </div>
      {creating && (
        <NewInvestigation
          config={config}
          close={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            open(id);
            void refresh();
          }}
        />
      )}
      {auth && (
        <Modal title="Workspace authentication" close={() => setAuth(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sessionStorage.setItem("failurelab-token", accessToken);
              setAuth(false);
              setError("");
              void refresh();
            }}
          >
            <p className="muted">
              Enter the FAILURELAB_API_TOKEN configured on this server.
            </p>
            <label className="field">
              Access token
              <input
                autoComplete="off"
                type="password"
                required
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button className="button primary">Connect workspace</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
