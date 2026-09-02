"use client";

import type { ReportPayload } from "@sih/contracts";
import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";
import {
  getReference,
  prepareImage,
  queueReport,
  saveDraft,
  setReference,
  syncPending,
} from "@/lib/offline";
import {
  offlinePreliminaryGuidance,
  type PreliminaryGuidance,
} from "@/lib/redFlags";
import type { AnimalRecord, FarmRecord, HerdRecord } from "@/app/registry/page";

type Language = "en" | "mr" | "hi";
const copy = {
  en: {
    heading: "Report livestock health concern",
    animal: "Animal",
    signs: "Signs",
    location: "Location & consent",
    select: "Select animal or herd",
    subject: "Subject",
    onset: "Symptom onset",
    severity: "Severity",
    appetite: "Appetite",
    water: "Water intake",
    mobility: "Mobility",
    respiration: "Respiration",
    lesions: "Visible lesions",
    discharge: "Discharge",
    temperature: "Temperature °C (optional)",
    vaccination: "Vaccination",
    movement: "Recent movement",
    contact: "Recent animal contact",
    mortality: "Mortality count",
    village: "Village",
    precision: "Location precision",
    notes: "Additional observation (optional)",
    consent:
      "I consent to storing this livestock report, location precision, and timestamps for veterinary review under consent notice CP1-1.",
    back: "Back",
    continue: "Continue",
    submit: "Save and submit report",
    prompt:
      "Seek prompt veterinary review. This offline demonstration check is not clinically validated.",
    routine: "Report saved for veterinary review. No diagnosis has been made.",
    preliminary:
      "Preliminary offline demonstration only; it may change after sync.",
  },
  mr: {
    heading: "पशुधन आरोग्य समस्या नोंदवा",
    animal: "प्राणी",
    signs: "लक्षणे",
    location: "स्थान आणि संमती",
    select: "प्राणी किंवा कळप निवडा",
    subject: "प्राणी / कळप",
    onset: "लक्षणे सुरू झाल्याची वेळ",
    severity: "तीव्रता",
    appetite: "भूक",
    water: "पाणी पिणे",
    mobility: "हालचाल",
    respiration: "श्वासोच्छ्वास",
    lesions: "दिसणाऱ्या जखमा",
    discharge: "स्त्राव",
    temperature: "तापमान °C (ऐच्छिक)",
    vaccination: "लसीकरण",
    movement: "अलीकडील स्थलांतर",
    contact: "इतर प्राण्यांशी अलीकडील संपर्क",
    mortality: "मृत्यू संख्या",
    village: "गाव",
    precision: "स्थानाची अचूकता",
    notes: "अतिरिक्त निरीक्षण (ऐच्छिक)",
    consent:
      "CP1-1 संमती सूचनेनुसार हा पशुधन अहवाल, स्थानाची अचूकता आणि वेळ पशुवैद्यकीय पुनरावलोकनासाठी साठवण्यास मी संमती देतो/देते.",
    back: "मागे",
    continue: "पुढे",
    submit: "अहवाल जतन करा आणि पाठवा",
    prompt:
      "त्वरित पशुवैद्यकीय पुनरावलोकन घ्या. ही ऑफलाइन प्रात्यक्षिक तपासणी वैद्यकीयदृष्ट्या प्रमाणित नाही.",
    routine:
      "अहवाल पशुवैद्यकीय पुनरावलोकनासाठी जतन केला. कोणतेही निदान केलेले नाही.",
    preliminary:
      "हे केवळ प्राथमिक ऑफलाइन प्रात्यक्षिक आहे; सिंकनंतर ते बदलू शकते.",
  },
  hi: {
    heading: "पशुधन स्वास्थ्य समस्या दर्ज करें",
    animal: "पशु",
    signs: "लक्षण",
    location: "स्थान और सहमति",
    select: "पशु या झुंड चुनें",
    subject: "पशु / झुंड",
    onset: "लक्षण शुरू होने का समय",
    severity: "गंभीरता",
    appetite: "भूख",
    water: "पानी पीना",
    mobility: "चलना-फिरना",
    respiration: "श्वसन",
    lesions: "दिखाई देने वाले घाव",
    discharge: "स्राव",
    temperature: "तापमान °C (वैकल्पिक)",
    vaccination: "टीकाकरण",
    movement: "हाल की आवाजाही",
    contact: "अन्य पशुओं से हाल का संपर्क",
    mortality: "मृत्यु संख्या",
    village: "गाँव",
    precision: "स्थान की सटीकता",
    notes: "अतिरिक्त अवलोकन (वैकल्पिक)",
    consent:
      "मैं CP1-1 सहमति सूचना के अंतर्गत इस पशुधन रिपोर्ट, स्थान की सटीकता और समय को पशुचिकित्सकीय समीक्षा के लिए संग्रहीत करने की सहमति देता/देती हूँ।",
    back: "पीछे",
    continue: "आगे",
    submit: "रिपोर्ट सहेजें और भेजें",
    prompt:
      "शीघ्र पशुचिकित्सकीय समीक्षा लें। यह ऑफलाइन प्रदर्शन जाँच चिकित्सकीय रूप से मान्य नहीं है।",
    routine:
      "रिपोर्ट पशुचिकित्सकीय समीक्षा के लिए सहेजी गई। कोई निदान नहीं किया गया है।",
    preliminary:
      "यह केवल प्रारंभिक ऑफलाइन प्रदर्शन है; सिंक के बाद बदल सकता है।",
  },
} as const;

type FormState = {
  subject: string;
  onset: string;
  severity: "MILD" | "MODERATE" | "SEVERE";
  appetite: "NORMAL" | "REDUCED" | "NONE" | "UNKNOWN";
  water: "NORMAL" | "REDUCED" | "NONE" | "UNKNOWN";
  mobility: "NORMAL" | "LIMPING" | "UNABLE_TO_STAND" | "UNKNOWN";
  respiration: "NORMAL" | "DIFFICULT" | "RAPID" | "UNKNOWN";
  lesions: "unknown" | "true" | "false";
  discharge: "unknown" | "true" | "false";
  temperature: string;
  vaccination: "CURRENT" | "OVERDUE" | "UNKNOWN";
  movement: "unknown" | "true" | "false";
  contact: "unknown" | "true" | "false";
  mortality: string;
  village: string;
  precision: "EXACT" | "APPROXIMATE" | "VILLAGE_ONLY";
  latitude: string;
  longitude: string;
  notes: string;
  consent: boolean;
};

function localDateTime(): string {
  const value = new Date(Date.now() - 60 * 60 * 1000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

const initialForm: FormState = {
  subject: "",
  onset: localDateTime(),
  severity: "MODERATE",
  appetite: "REDUCED",
  water: "NORMAL",
  mobility: "NORMAL",
  respiration: "NORMAL",
  lesions: "unknown",
  discharge: "unknown",
  temperature: "",
  vaccination: "UNKNOWN",
  movement: "unknown",
  contact: "unknown",
  mortality: "0",
  village: "",
  precision: "VILLAGE_ONLY",
  latitude: "",
  longitude: "",
  notes: "",
  consent: false,
};

function optionalBoolean(value: "unknown" | "true" | "false"): boolean | null {
  return value === "unknown" ? null : value === "true";
}

export default function NewReportPage() {
  const [language, setLanguage] = useState<Language>("en");
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormState>(initialForm);
  const [farms, setFarms] = useState<FarmRecord[]>([]);
  const [animals, setAnimals] = useState<AnimalRecord[]>([]);
  const [herds, setHerds] = useState<HerdRecord[]>([]);
  const [online, setOnline] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [guidance, setGuidance] = useState<PreliminaryGuidance | null>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [mediaMessage, setMediaMessage] = useState("");
  const t = copy[language];

  const subjects = useMemo(
    () => [
      ...animals.map((animal) => ({
        key: `animal:${animal.id}`,
        farmId: animal.farm_id,
        label: `${animal.tag_number} · ${animal.species}`,
        species: animal.species,
        ageBand: animal.age_band,
        animalId: animal.id,
        herdId: null,
      })),
      ...herds.map((herd) => ({
        key: `herd:${herd.id}`,
        farmId: herd.farm_id,
        label: `${herd.name} · ${herd.species} herd`,
        species: herd.species,
        ageBand: "UNKNOWN" as const,
        animalId: null,
        herdId: herd.id,
      })),
    ],
    [animals, herds],
  );

  useEffect(() => {
    setOnline(navigator.onLine);
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    void (async () => {
      const cached = await Promise.all([
        getReference<FarmRecord[]>("farms"),
        getReference<AnimalRecord[]>("animals"),
        getReference<HerdRecord[]>("herds"),
      ]);
      if (cached[0]) setFarms(cached[0]);
      if (cached[1]) setAnimals(cached[1]);
      if (cached[2]) setHerds(cached[2]);
      if (navigator.onLine) {
        try {
          const fresh = await Promise.all([
            apiFetch<FarmRecord[]>("/api/v1/farms"),
            apiFetch<AnimalRecord[]>("/api/v1/animals"),
            apiFetch<HerdRecord[]>("/api/v1/herds"),
          ]);
          setFarms(fresh[0]);
          setAnimals(fresh[1]);
          setHerds(fresh[2]);
          await Promise.all([
            setReference("farms", fresh[0]),
            setReference("animals", fresh[1]),
            setReference("herds", fresh[2]),
          ]);
        } catch {
          setError("Using the registry saved on this device.");
        }
      }
    })();
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    void saveDraft(
      "active-health-report",
      form as unknown as Partial<ReportPayload>,
    );
  }, [form]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function next() {
    setError("");
    if (step === 1 && !form.subject) {
      setError("Select an animal or herd.");
      return;
    }
    setStep((current) => Math.min(3, current + 1));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const selected = subjects.find((subject) => subject.key === form.subject);
    if (!selected || !form.consent) {
      setError("Select a subject and record consent before submitting.");
      return;
    }
    const farm = farms.find((item) => item.id === selected.farmId);
    if (!farm) {
      setError("The selected farm is not available on this device.");
      return;
    }
    const createdAtDevice = new Date().toISOString();
    const payload: ReportPayload = {
      id: crypto.randomUUID(),
      farm_id: farm.id,
      animal_id: selected.animalId,
      herd_id: selected.herdId,
      species: selected.species,
      language,
      age_band: selected.ageBand,
      symptom_onset_at: new Date(form.onset).toISOString(),
      severity: form.severity,
      appetite: form.appetite,
      water_intake: form.water,
      mobility: form.mobility,
      respiration: form.respiration,
      visible_lesions: optionalBoolean(form.lesions),
      discharge: optionalBoolean(form.discharge),
      temperature_c: form.temperature ? Number(form.temperature) : null,
      vaccination_status: form.vaccination,
      recent_movement: optionalBoolean(form.movement),
      recent_contact: optionalBoolean(form.contact),
      mortality_count: Number(form.mortality),
      village_name: form.village || farm.village_name,
      latitude: form.latitude ? Number(form.latitude) : null,
      longitude: form.longitude ? Number(form.longitude) : null,
      location_precision: form.precision,
      notes: form.notes || null,
      media_refs: mediaId ? [mediaId] : [],
      voice_transcript: null,
      consent_given: true,
      consent_version: "CP1-1",
      created_at_device: createdAtDevice,
      optional_provider_status: {
        image: mediaId ? "PENDING" : "NOT_PROVIDED",
        voice: "NOT_PROVIDED",
        nlp: "UNAVAILABLE",
        weather: "UNAVAILABLE",
        ml: "UNAVAILABLE",
      },
    };
    const preliminary = offlinePreliminaryGuidance(payload);
    await queueReport(payload);
    setGuidance(preliminary);
    setMessage(
      navigator.onLine
        ? "Report stored durably on this device and queued for synchronization."
        : "Report stored durably while offline. It will synchronize when connectivity returns.",
    );
    if (navigator.onLine) await syncPending(true);
    setMediaId(null);
    setMediaMessage("");
    setForm((current) => ({
      ...initialForm,
      subject: current.subject,
      village: current.village,
      onset: localDateTime(),
    }));
    setStep(1);
  }

  return (
    <AppShell allowedRoles={["FARMER", "FIELD_WORKER"]}>
      <div className={online ? "" : "offline"} aria-live="polite">
        <span className="status-dot" />{" "}
        {online ? "Online" : "Offline · reports remain on this device"}
      </div>
      <p className="eyebrow">Guided observation</p>
      <label className="field">
        Language / भाषा / भाषा
        <select
          data-testid="report-language"
          value={language}
          onChange={(event) => setLanguage(event.target.value as Language)}
        >
          <option value="en">English</option>
          <option value="mr">मराठी</option>
          <option value="hi">हिन्दी</option>
        </select>
      </label>
      <h1 lang={language}>{t.heading}</h1>
      <p className="notice">
        Guided answers are primary. Photo, voice, NLP, weather, and ML are
        optional and unavailable in this checkpoint; that never blocks this
        report.
      </p>
      <ol className="steps" aria-label="Report progress">
        <li className={step === 1 ? "active" : ""}>1. {t.animal}</li>
        <li className={step === 2 ? "active" : ""}>2. {t.signs}</li>
        <li className={step === 3 ? "active" : ""}>3. {t.location}</li>
      </ol>
      {message && (
        <div className="success" data-testid="report-stored" role="status">
          {message}
        </div>
      )}
      {guidance && (
        <div
          className="notice"
          data-testid="preliminary-guidance"
          lang={language}
        >
          <strong>
            {guidance.tier === "PROMPT_VET_REVIEW" ? t.prompt : t.routine}
          </strong>
          {guidance.reasons.length > 0 && (
            <div>Reasons: {guidance.reasons.join(", ")}</div>
          )}
          <div>{t.preliminary}</div>
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!subjects.length && (
        <p className="card">
          No animal or herd is cached.{" "}
          <Link href="/registry">Create one while connected.</Link>
        </p>
      )}
      <form onSubmit={(event) => void submit(event)}>
        {step === 1 && (
          <section className="card">
            <h2>{t.select}</h2>
            <label className="field">
              {t.subject}
              <select
                data-testid="report-subject"
                required
                value={form.subject}
                onChange={(event) => update("subject", event.target.value)}
              >
                <option value="">Choose…</option>
                {subjects.map((subject) => (
                  <option key={subject.key} value={subject.key}>
                    {subject.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t.onset}
              <input
                data-testid="report-onset"
                type="datetime-local"
                required
                value={form.onset}
                onChange={(event) => update("onset", event.target.value)}
              />
            </label>
          </section>
        )}
        {step === 2 && (
          <section className="card">
            <h2>{t.signs}</h2>
            <div className="grid">
              <label className="field">
                {t.severity}
                <select
                  data-testid="report-severity"
                  value={form.severity}
                  onChange={(event) =>
                    update(
                      "severity",
                      event.target.value as FormState["severity"],
                    )
                  }
                >
                  <option value="MILD">Mild</option>
                  <option value="MODERATE">Moderate</option>
                  <option value="SEVERE">Severe</option>
                </select>
              </label>
              <label className="field">
                {t.appetite}
                <select
                  value={form.appetite}
                  onChange={(event) =>
                    update(
                      "appetite",
                      event.target.value as FormState["appetite"],
                    )
                  }
                >
                  <option value="NORMAL">Normal</option>
                  <option value="REDUCED">Reduced</option>
                  <option value="NONE">None</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </label>
              <label className="field">
                {t.water}
                <select
                  value={form.water}
                  onChange={(event) =>
                    update("water", event.target.value as FormState["water"])
                  }
                >
                  <option value="NORMAL">Normal</option>
                  <option value="REDUCED">Reduced</option>
                  <option value="NONE">None</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </label>
              <label className="field">
                {t.mobility}
                <select
                  value={form.mobility}
                  onChange={(event) =>
                    update(
                      "mobility",
                      event.target.value as FormState["mobility"],
                    )
                  }
                >
                  <option value="NORMAL">Normal</option>
                  <option value="LIMPING">Limping</option>
                  <option value="UNABLE_TO_STAND">Unable to stand</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </label>
              <label className="field">
                {t.respiration}
                <select
                  value={form.respiration}
                  onChange={(event) =>
                    update(
                      "respiration",
                      event.target.value as FormState["respiration"],
                    )
                  }
                >
                  <option value="NORMAL">Normal</option>
                  <option value="RAPID">Rapid</option>
                  <option value="DIFFICULT">Difficult</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </label>
              <label className="field">
                {t.lesions}
                <select
                  value={form.lesions}
                  onChange={(event) =>
                    update(
                      "lesions",
                      event.target.value as FormState["lesions"],
                    )
                  }
                >
                  <option value="unknown">Unknown / not checked</option>
                  <option value="true">Observed</option>
                  <option value="false">Not observed</option>
                </select>
              </label>
              <label className="field">
                {t.discharge}
                <select
                  value={form.discharge}
                  onChange={(event) =>
                    update(
                      "discharge",
                      event.target.value as FormState["discharge"],
                    )
                  }
                >
                  <option value="unknown">Unknown / not checked</option>
                  <option value="true">Observed</option>
                  <option value="false">Not observed</option>
                </select>
              </label>
              <label className="field">
                {t.temperature}
                <input
                  type="number"
                  min="25"
                  max="50"
                  step="0.1"
                  value={form.temperature}
                  onChange={(event) =>
                    update("temperature", event.target.value)
                  }
                />
              </label>
              <label className="field">
                {t.vaccination}
                <select
                  value={form.vaccination}
                  onChange={(event) =>
                    update(
                      "vaccination",
                      event.target.value as FormState["vaccination"],
                    )
                  }
                >
                  <option value="CURRENT">Current</option>
                  <option value="OVERDUE">Overdue</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              </label>
              <label className="field">
                {t.movement}
                <select
                  value={form.movement}
                  onChange={(event) =>
                    update(
                      "movement",
                      event.target.value as FormState["movement"],
                    )
                  }
                >
                  <option value="unknown">Unknown</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                {t.contact}
                <select
                  value={form.contact}
                  onChange={(event) =>
                    update(
                      "contact",
                      event.target.value as FormState["contact"],
                    )
                  }
                >
                  <option value="unknown">Unknown</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                {t.mortality}
                <input
                  data-testid="report-mortality"
                  type="number"
                  min="0"
                  max="100000"
                  required
                  value={form.mortality}
                  onChange={(event) => update("mortality", event.target.value)}
                />
              </label>
            </div>
          </section>
        )}
        {step === 3 && (
          <section className="card">
            <h2>{t.location}</h2>
            <label className="field">
              {t.village}
              <input
                data-testid="report-village"
                required
                value={form.village}
                placeholder="Uses farm village if blank"
                onChange={(event) => update("village", event.target.value)}
              />
            </label>
            <label className="field">
              {t.precision}
              <select
                value={form.precision}
                onChange={(event) =>
                  update(
                    "precision",
                    event.target.value as FormState["precision"],
                  )
                }
              >
                <option value="VILLAGE_ONLY">
                  Village only (privacy preserving)
                </option>
                <option value="APPROXIMATE">Approximate coordinates</option>
                <option value="EXACT">Exact coordinates</option>
              </select>
            </label>
            {form.precision !== "VILLAGE_ONLY" && (
              <div className="split">
                <label className="field">
                  Latitude
                  <input
                    type="number"
                    min="-90"
                    max="90"
                    step="any"
                    required
                    value={form.latitude}
                    onChange={(event) => update("latitude", event.target.value)}
                  />
                </label>
                <label className="field">
                  Longitude
                  <input
                    type="number"
                    min="-180"
                    max="180"
                    step="any"
                    required
                    value={form.longitude}
                    onChange={(event) =>
                      update("longitude", event.target.value)
                    }
                  />
                </label>
              </div>
            )}
            <label className="field">
              {t.notes}
              <textarea
                value={form.notes}
                maxLength={4000}
                onChange={(event) => update("notes", event.target.value)}
              />
            </label>
            <label className="field">
              Optional image (JPEG/PNG, compressed on device)
              <input
                type="file"
                accept="image/jpeg,image/png"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  setMediaMessage("Compressing image on this device…");
                  void prepareImage(file)
                    .then((media) => {
                      setMediaId(media.id);
                      setMediaMessage(
                        "Image stored locally. Its upload is optional and resumable after the base report syncs.",
                      );
                    })
                    .catch((reason) => {
                      setMediaId(null);
                      setMediaMessage(
                        reason instanceof Error
                          ? reason.message
                          : "Optional image unavailable; report can still be sent.",
                      );
                    });
                }}
              />
            </label>
            {mediaMessage && (
              <p className="muted" role="status">
                {mediaMessage}
              </p>
            )}
            <label className="checkbox">
              <input
                data-testid="report-consent"
                type="checkbox"
                checked={form.consent}
                onChange={(event) => update("consent", event.target.checked)}
              />
              {t.consent}
            </label>
          </section>
        )}
        <div className="actions">
          {step > 1 && (
            <button
              type="button"
              className="secondary"
              onClick={() => setStep((current) => current - 1)}
            >
              {t.back}
            </button>
          )}
          {step < 3 && (
            <button data-testid="report-next" type="button" onClick={next}>
              {t.continue}
            </button>
          )}
          {step === 3 && (
            <button data-testid="submit-report" type="submit">
              {t.submit}
            </button>
          )}
        </div>
      </form>
    </AppShell>
  );
}
