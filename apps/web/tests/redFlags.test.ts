import { describe, expect, it } from "vitest";

import { offlinePreliminaryGuidance } from "@/lib/redFlags";

describe("offline preliminary guidance", () => {
  it("prompts review and clearly avoids a diagnosis for demo red flags", () => {
    const result = offlinePreliminaryGuidance({
      mobility: "UNABLE_TO_STAND",
      respiration: "DIFFICULT",
      mortality_count: 1,
      severity: "SEVERE",
    });
    expect(result.tier).toBe("PROMPT_VET_REVIEW");
    expect(result.reasons).toHaveLength(4);
    expect(result.message).toContain("not clinically validated");
  });

  it("routes even an incomplete low-severity observation to vet review", () => {
    const result = offlinePreliminaryGuidance({
      mobility: "UNKNOWN",
      respiration: "UNKNOWN",
      mortality_count: 0,
      severity: "MILD",
    });
    expect(result.tier).toBe("ROUTINE_VET_REVIEW");
    expect(result.message).toContain("No diagnosis");
  });
});
