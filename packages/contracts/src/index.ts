export type Role =
  | "FARMER"
  | "FIELD_WORKER"
  | "VETERINARIAN"
  | "DISTRICT_OFFICER"
  | "ADMIN";

export type SyncState = "PENDING" | "SYNCING" | "ACKED" | "FAILED" | "CONFLICT";
export type MutationType = "CREATE_REPORT" | "UPDATE_REPORT";

export interface UserIdentity {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface ReportPayload {
  id: string;
  farm_id: string;
  animal_id?: string | null;
  herd_id?: string | null;
  species: "CATTLE" | "BUFFALO";
  language: "en" | "mr" | "hi";
  age_band: "CALF" | "YOUNG" | "ADULT" | "UNKNOWN";
  symptom_onset_at: string;
  severity: "MILD" | "MODERATE" | "SEVERE";
  appetite: "NORMAL" | "REDUCED" | "NONE" | "UNKNOWN";
  water_intake: "NORMAL" | "REDUCED" | "NONE" | "UNKNOWN";
  mobility: "NORMAL" | "LIMPING" | "UNABLE_TO_STAND" | "UNKNOWN";
  respiration: "NORMAL" | "DIFFICULT" | "RAPID" | "UNKNOWN";
  visible_lesions: boolean | null;
  discharge: boolean | null;
  temperature_c: number | null;
  vaccination_status: "CURRENT" | "OVERDUE" | "UNKNOWN";
  recent_movement: boolean | null;
  recent_contact: boolean | null;
  mortality_count: number;
  village_name: string;
  latitude: number | null;
  longitude: number | null;
  location_precision: "EXACT" | "APPROXIMATE" | "VILLAGE_ONLY";
  notes: string | null;
  media_refs: string[];
  voice_transcript: string | null;
  consent_given: true;
  consent_version: string;
  created_at_device: string;
  optional_provider_status: {
    image: "NOT_PROVIDED" | "PENDING" | "UNAVAILABLE";
    voice: "NOT_PROVIDED" | "PENDING" | "UNAVAILABLE";
    nlp: "PENDING" | "UNAVAILABLE";
    weather: "PENDING" | "UNAVAILABLE";
    ml: "PENDING" | "UNAVAILABLE";
  };
}

export interface SyncMutation {
  client_mutation_id: string;
  idempotency_key: string;
  mutation_type: MutationType;
  base_version: number | null;
  created_at_device: string;
  payload: ReportPayload | Partial<ReportPayload>;
}

export interface SyncMutationResult {
  client_mutation_id: string;
  status: "APPLIED" | "DUPLICATE" | "CONFLICT" | "REJECTED";
  resource_id: string | null;
  resource_version: number | null;
  received_at_server: string;
  error: { code: string; message: string } | null;
}

export interface TriageDecision {
  assessment_id: string | null;
  report_id: string;
  urgency_tier: "LOW" | "VET_REVIEW" | "EMERGENCY";
  urgency_probabilities: Record<"LOW" | "VET_REVIEW" | "EMERGENCY", number>;
  suspected_condition_likelihoods: Record<string, number>;
  override_applied: boolean;
  uncertainty: number;
  insufficient_information: boolean;
  model_version: string | null;
  rule_version: string;
  threshold_version: string;
  feature_schema_version: string;
  calibration_status: "DEMO_UNVALIDATED" | "CALIBRATED" | "MODEL_UNAVAILABLE";
  modality_status: Record<string, string>;
  clinical_notice: string;
}
