"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type Evidence = {
  case: {
    id: string;
    state: string;
    version: number;
    suspected_label: string | null;
    suspected_status: string;
    verified_label: string | null;
    verified_status: string;
    lab_status: string;
  };
  raw_observations: Record<string, unknown>;
  original_prediction: {
    immutable: boolean;
    model_version: string | null;
    rule_version: string | null;
    feature_schema_version: string;
    urgency_tier: string;
    probabilities: Record<string, unknown>;
    decision_trace: Record<string, unknown>;
  };
  analysis_artifacts: Array<Record<string, unknown>>;
  media: Array<Record<string, unknown>>;
  explanations: Array<Record<string, unknown>>;
  nearby_context: Record<string, unknown>;
  weather: Record<string, unknown>;
  reviews: Array<Record<string, unknown>>;
  lab_referrals: Array<{
    id: string;
    sample_identifier: string;
    status: string;
  }>;
  lab_results: Array<Record<string, unknown>>;
  follow_ups: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
  clinical_notice: string;
};

export default function CasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [data, setData] = useState<Evidence | null>(null);
  const [label, setLabel] = useState("SYNDROME_UNSPECIFIED");
  const [sampleId, setSampleId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setData(await apiFetch<Evidence>(`/api/v1/vet/cases/${caseId}`));
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not load case",
      );
    }
  }, [caseId]);
  useEffect(() => void load(), [load]);

  async function action(path: string, body: Record<string, unknown>) {
    try {
      await apiFetch(`/api/v1/vet/cases/${caseId}${path}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessage("Action recorded with audit history.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Action failed");
    }
  }

  if (!data)
    return (
      <AppShell allowedRoles={["VETERINARIAN", "ADMIN"]}>
        <h1>Case evidence</h1>
        {error || "Loading…"}
      </AppShell>
    );
  const version = data.case.version;
  return (
    <AppShell allowedRoles={["VETERINARIAN", "ADMIN"]}>
      <p className="eyebrow">Human-in-the-loop review</p>
      <h1>Case {caseId}</h1>
      <p className="notice">{data.clinical_notice}</p>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}
      <section className="truth-strip" data-testid="truth-statuses">
        <div>
          <strong>Suspected</strong>
          <br />
          {data.case.suspected_status}: {data.case.suspected_label ?? "unknown"}
        </div>
        <div>
          <strong>Vet verified</strong>
          <br />
          {data.case.verified_status}: {data.case.verified_label ?? "pending"}
        </div>
        <div>
          <strong>Laboratory</strong>
          <br />
          {data.case.lab_status}
        </div>
      </section>
      <section className="card">
        <h2>Case actions · {data.case.state.replaceAll("_", " ")}</h2>
        <div className="actions">
          {data.case.state === "TRIAGED" && (
            <button
              data-testid="assign-case"
              onClick={() => action("/assign", { expected_version: version })}
            >
              Assign to me
            </button>
          )}
          {data.case.state === "ASSIGNED" && (
            <button
              data-testid="start-review"
              onClick={() =>
                action("/transition", {
                  expected_version: version,
                  to_state: "UNDER_REVIEW",
                  reason: "Veterinarian opened evidence review",
                })
              }
            >
              Start review
            </button>
          )}
          {data.case.state === "UNDER_REVIEW" && (
            <>
              <input
                aria-label="Verified label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
              />
              <button
                data-testid="confirm-case"
                onClick={() =>
                  action("/review", {
                    expected_version: version,
                    outcome: "CONFIRMED",
                    verified_label: label,
                    notes: "Confirmed after human review",
                  })
                }
              >
                Confirm
              </button>
              <button
                onClick={() =>
                  action("/review", {
                    expected_version: version,
                    outcome: "CORRECTED",
                    verified_label: label,
                    notes: "Corrected after human review",
                  })
                }
              >
                Correct label
              </button>
              <button
                className="secondary"
                onClick={() =>
                  action("/review", {
                    expected_version: version,
                    outcome: "INCONCLUSIVE",
                    verified_label: null,
                    notes: "Evidence is insufficient",
                  })
                }
              >
                Mark inconclusive
              </button>
              <input
                aria-label="Sample identifier"
                value={sampleId}
                placeholder="SAMPLE-2026-001"
                onChange={(event) => setSampleId(event.target.value)}
              />
              <button
                className="secondary"
                onClick={() =>
                  action("/sample-request", {
                    expected_version: version,
                    sample_identifier: sampleId,
                  })
                }
              >
                Request sample
              </button>
            </>
          )}
          <button
            className="secondary"
            onClick={() =>
              action("/follow-ups", {
                follow_up_type: "PHONE",
                notes: "Scheduled farmer follow-up",
                due_at: null,
              })
            }
          >
            Record follow-up
          </button>
          <button
            className="secondary"
            onClick={() =>
              action("/escalate", {
                level: 1,
                reason: "Additional operational review required",
              })
            }
          >
            Escalate
          </button>
        </div>
      </section>
      <div className="grid">
        <section className="card">
          <h2>Original prediction (immutable)</h2>
          <p>
            Urgency: <strong>{data.original_prediction.urgency_tier}</strong>
          </p>
          <p>
            Model: {data.original_prediction.model_version ?? "none"}
            <br />
            Rules: {data.original_prediction.rule_version}
            <br />
            Features: {data.original_prediction.feature_schema_version}
          </p>
          <pre>
            {JSON.stringify(data.original_prediction.probabilities, null, 2)}
          </pre>
        </section>
        <section className="card">
          <h2>Raw guided observations</h2>
          <pre>{JSON.stringify(data.raw_observations, null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Media and modality quality</h2>
          <pre>
            {JSON.stringify(
              { media: data.media, artifacts: data.analysis_artifacts },
              null,
              2,
            )}
          </pre>
        </section>
        <section className="card">
          <h2>Explanations and trace</h2>
          <pre>
            {JSON.stringify(
              {
                explanations: data.explanations,
                trace: data.original_prediction.decision_trace,
              },
              null,
              2,
            )}
          </pre>
        </section>
        <section className="card">
          <h2>Nearby context</h2>
          <pre>{JSON.stringify(data.nearby_context, null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Cached weather (optional)</h2>
          <pre>{JSON.stringify(data.weather, null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Audit timeline</h2>
          <pre>
            {JSON.stringify(
              {
                timeline: data.timeline,
                reviews: data.reviews,
                referrals: data.lab_referrals,
                results: data.lab_results,
                followUps: data.follow_ups,
              },
              null,
              2,
            )}
          </pre>
        </section>
      </div>
    </AppShell>
  );
}
