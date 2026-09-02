import type { ReportPayload } from "@sih/contracts";

export interface PreliminaryGuidance {
  tier: "PROMPT_VET_REVIEW" | "ROUTINE_VET_REVIEW";
  reasons: string[];
  message: string;
}

export function offlinePreliminaryGuidance(
  report: Pick<
    ReportPayload,
    "mobility" | "respiration" | "mortality_count" | "severity"
  >,
): PreliminaryGuidance {
  const reasons: string[] = [];
  if (report.mobility === "UNABLE_TO_STAND")
    reasons.push("animal unable to stand");
  if (report.respiration === "DIFFICULT")
    reasons.push("difficult breathing reported");
  if (report.mortality_count > 0) reasons.push("mortality reported");
  if (report.severity === "SEVERE")
    reasons.push("reporter selected severe symptoms");
  return {
    tier: reasons.length ? "PROMPT_VET_REVIEW" : "ROUTINE_VET_REVIEW",
    reasons,
    message: reasons.length
      ? "Seek prompt veterinary review. This offline demonstration check is not clinically validated."
      : "Report saved for veterinary review. No diagnosis has been made.",
  };
}
