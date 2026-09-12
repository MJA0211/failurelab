export type Evidence = {
  id: string;
  title: string;
  kind: string;
  content: string;
  source: string;
  sha: string;
  artifact?: string;
};
export type Hypothesis = {
  id: string;
  cause: string;
  title: string;
  explanation: string;
  evidence_ids: string[];
  status: string;
};
export type Experiment = {
  hypothesis_id: string;
  intervention: string;
  baseline_passes: number;
  intervention_passes: number;
  repetitions: number;
  verdict: string;
  duration_ms: number;
  observations: string[];
  artifacts: string[];
  environment: Record<string, string>;
};
export type Report = {
  outcome: string;
  summary: string;
  hypotheses: Hypothesis[];
  experiments: Experiment[];
  evidence: Evidence[];
  missing_evidence: string[];
  limitations: string[];
  metrics: {
    duration_ms: number;
    model_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_model_cost_usd: number | null;
  };
  versions: {
    mode: string;
    model: string;
    prompt: string;
    retrieval_mode: string;
  };
  evidence_digest: string;
  retrieval: { id: string; rank: number; score: number }[];
};
export type Case = {
  id: string;
  title: string;
  repository: string;
  commit_sha: string;
  test_name: string;
  source: string;
  scenario: string;
  status: string;
  stage: string;
  created_at: string;
  updated_at: string;
  attempts: number;
  error?: string;
  result?: Report;
  payload?: { evidence: Evidence[] };
  events?: {
    id: number;
    at: string;
    stage: string;
    message: string;
    data: unknown;
  }[];
  reviews?: { id: number; at: string; decision: string; note: string }[];
};
export type Config = {
  version: string;
  model_mode: string;
  model_name: string;
  retrieval_mode: string;
  github_configured: boolean;
  github_repositories: string[];
  runner_configured: boolean;
  worker_enabled: boolean;
  max_experiments: number;
  max_model_calls: number;
  vision_enabled: boolean;
  authentication: boolean;
};
export type Evaluation = {
  available: boolean;
  message?: string;
  generated_at: string;
  dataset: string;
  dataset_sha256: string;
  mode: string;
  case_count: number;
  duration_ms: number;
  variants: {
    name: string;
    cases: number;
    correct: number;
    top1_accuracy: number;
    top3_accuracy: number;
    accuracy_interval_95: number[];
    citation_validity: number;
    abstention_rate: number;
    unknown_abstention_accuracy: number;
  }[];
  results: {
    id: string;
    variant: string;
    expected: string;
    predicted: string;
    correct: boolean;
    abstained: boolean;
  }[];
  limitations: string[];
};
