"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type VetReport = {
  id: string;
  species: string;
  severity: string;
  village_name: string;
  mortality_count: number;
  created_at_device: string;
  received_at_server: string;
  status: string;
  optional_provider_status: Record<string, string>;
  risk_assessment: TriageDecision | null;
  case: {
    id: string;
    state: string;
    version: number;
    suspected_status: string;
    verified_status: string;
    lab_status: string;
  } | null;
};

type TriageDecision = {
  urgency_tier: "LOW" | "VET_REVIEW" | "EMERGENCY";
  urgency_probabilities: Record<"LOW" | "VET_REVIEW" | "EMERGENCY", number>;
  suspected_condition_likelihoods: Record<string, number>;
  rule_matches: Array<{
    rule_id: string;
    message: string;
    validation_status: string;
  }>;
  override_applied: boolean;
  uncertainty: number;
  model_version: string | null;
  rule_version: string;
  threshold_version: string;
  feature_schema_version: string;
  calibration_status: string;
  contributions: Array<{
    feature: string;
    message: string;
    contribution: number;
  }>;
  decision_trace: Array<Record<string, unknown>>;
  clinical_notice: string;
};

export default function VetQueuePage() {
  const [reports, setReports] = useState<VetReport[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const page = await apiFetch<{ items: VetReport[] }>(
        "/api/v1/vet/cases?page=1&page_size=100",
      );
      setReports(page.items);
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not load queue",
      );
    }
  }, []);
  useEffect(() => void load(), [load]);

  return (
    <AppShell allowedRoles={["VETERINARIAN", "ADMIN"]}>
      <p className="eyebrow">Veterinary review</p>
      <h1>Preliminary triage queue</h1>
      <p className="notice">
        Suspected patterns and urgency are decision support, not confirmed
        diagnoses. Veterinary verification is required and the original
        prediction remains immutable after review.
      </p>
      <button className="secondary" onClick={() => void load()}>
        Refresh queue
      </button>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="table-wrap">
        <table data-testid="vet-queue">
          <thead>
            <tr>
              <th>Report</th>
              <th>Preliminary triage</th>
              <th>Subject</th>
              <th>Observation</th>
              <th>Timing</th>
              <th>Optional services</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.id} data-report-id={report.id}>
                <td>
                  <code>{report.id}</code>
                  <div>{report.status.replaceAll("_", " ")}</div>
                  {report.case && (
                    <Link
                      className="button-link"
                      href={`/vet/cases/${report.case.id}`}
                    >
                      Review case
                    </Link>
                  )}
                  {report.case && (
                    <small>
                      Suspected: {report.case.suspected_status} · Verified:{" "}
                      {report.case.verified_status} · Lab:{" "}
                      {report.case.lab_status}
                    </small>
                  )}
                </td>
                <td data-testid={`triage-${report.id}`}>
                  {report.risk_assessment ? (
                    <>
                      <strong data-testid="urgency-tier">
                        Urgency:{" "}
                        {report.risk_assessment.urgency_tier.replaceAll(
                          "_",
                          " ",
                        )}
                      </strong>
                      <div>
                        LOW{" "}
                        {Math.round(
                          report.risk_assessment.urgency_probabilities.LOW *
                            100,
                        )}
                        %{" · "}REVIEW{" "}
                        {Math.round(
                          report.risk_assessment.urgency_probabilities
                            .VET_REVIEW * 100,
                        )}
                        %{` · `}EMERGENCY{" "}
                        {Math.round(
                          report.risk_assessment.urgency_probabilities
                            .EMERGENCY * 100,
                        )}
                        %
                      </div>
                      <div>
                        Uncertainty:{" "}
                        {Math.round(report.risk_assessment.uncertainty * 100)}%
                      </div>
                      {report.risk_assessment.override_applied && (
                        <div className="danger-text">
                          Demo red-flag override applied
                        </div>
                      )}
                      <details>
                        <summary>
                          Evidence, versions, and decision trace
                        </summary>
                        <p>{report.risk_assessment.clinical_notice}</p>
                        <div>
                          Model:{" "}
                          {report.risk_assessment.model_version ??
                            "unavailable"}
                          <br />
                          Rules: {report.risk_assessment.rule_version}
                          <br />
                          Thresholds: {report.risk_assessment.threshold_version}
                          <br />
                          Features:{" "}
                          {report.risk_assessment.feature_schema_version}
                          <br />
                          Calibration:{" "}
                          {report.risk_assessment.calibration_status.replaceAll(
                            "_",
                            " ",
                          )}
                        </div>
                        <h3>Suspected patterns</h3>
                        <ul>
                          {Object.entries(
                            report.risk_assessment
                              .suspected_condition_likelihoods,
                          ).map(([condition, likelihood]) => (
                            <li key={condition}>
                              {condition.replaceAll("_", " ")}:{" "}
                              {Math.round(likelihood * 100)}%
                            </li>
                          ))}
                        </ul>
                        <h3>Feature contributions</h3>
                        <ul>
                          {report.risk_assessment.contributions.map((item) => (
                            <li key={item.feature}>{item.message}</li>
                          ))}
                        </ul>
                        {report.risk_assessment.rule_matches.map((rule) => (
                          <p key={rule.rule_id}>
                            {rule.message} (
                            {rule.validation_status.replaceAll("_", " ")})
                          </p>
                        ))}
                        <pre>
                          {JSON.stringify(
                            report.risk_assessment.decision_trace,
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </>
                  ) : (
                    "Triage pending; base report remains recorded."
                  )}
                </td>
                <td>
                  {report.species}
                  <div>{report.village_name}</div>
                </td>
                <td>
                  {report.severity}
                  <div>Mortality: {report.mortality_count}</div>
                </td>
                <td>
                  Device: {new Date(report.created_at_device).toLocaleString()}
                  <br />
                  Server: {new Date(report.received_at_server).toLocaleString()}
                </td>
                <td>
                  {Object.entries(report.optional_provider_status).map(
                    ([name, value]) => (
                      <div key={name}>
                        {name}: {value}
                      </div>
                    ),
                  )}
                </td>
              </tr>
            ))}
            {!reports.length && (
              <tr>
                <td colSpan={6}>No synchronized reports are waiting.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
