import type { ReportPayload } from "@sih/contracts";
import { deleteDB } from "idb";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { storeSession } from "@/lib/api";
import {
  listMutations,
  chunkBlob,
  queueReport,
  resetDatabaseHandleForTests,
  syncPending,
} from "@/lib/offline";

const report: ReportPayload = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  farm_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  animal_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  herd_id: null,
  species: "CATTLE",
  language: "en",
  age_band: "ADULT",
  symptom_onset_at: "2026-09-01T06:00:00.000Z",
  severity: "MODERATE",
  appetite: "REDUCED",
  water_intake: "UNKNOWN",
  mobility: "NORMAL",
  respiration: "NORMAL",
  visible_lesions: null,
  discharge: null,
  temperature_c: null,
  vaccination_status: "UNKNOWN",
  recent_movement: null,
  recent_contact: null,
  mortality_count: 0,
  village_name: "Synthetic Village",
  latitude: null,
  longitude: null,
  location_precision: "VILLAGE_ONLY",
  notes: null,
  media_refs: [],
  voice_transcript: null,
  consent_given: true,
  consent_version: "CP1-1",
  created_at_device: "2026-09-01T07:00:00.000Z",
  optional_provider_status: {
    image: "NOT_PROVIDED",
    voice: "NOT_PROVIDED",
    nlp: "UNAVAILABLE",
    weather: "UNAVAILABLE",
    ml: "UNAVAILABLE",
  },
};

beforeEach(async () => {
  await resetDatabaseHandleForTests();
  await deleteDB("sih-offline-cp1");
  await resetDatabaseHandleForTests();
  vi.spyOn(globalThis.crypto, "randomUUID")
    .mockReturnValueOnce("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    .mockReturnValueOnce("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee");
});

describe("durable mutation queue", () => {
  it("splits optional media into resumable chunks", () => {
    const chunks = chunkBlob(
      new Blob([new Uint8Array(1300)], { type: "image/jpeg" }),
      512,
    );
    expect(chunks.map((chunk) => chunk.size)).toEqual([512, 512, 276]);
  });

  it("preserves UUID, idempotency key, null optional data, and pending state", async () => {
    const mutation = await queueReport(report);
    await resetDatabaseHandleForTests();
    const stored = await listMutations();
    expect(stored).toHaveLength(1);
    expect(stored[0].client_mutation_id).toBe(mutation.client_mutation_id);
    expect(stored[0].idempotency_key).toContain(report.id);
    expect(stored[0].payload.temperature_c).toBeNull();
    expect(stored[0].state).toBe("PENDING");
  });

  it("acknowledges an applied server result exactly once in local state", async () => {
    const mutation = await queueReport(report);
    storeSession("test-token", {
      id: "11111111-1111-4111-8111-111111111111",
      email: "farmer@example.com",
      display_name: "Synthetic Farmer",
      role: "FARMER",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            results: [
              {
                client_mutation_id: mutation.client_mutation_id,
                status: "APPLIED",
                resource_id: report.id,
                resource_version: 1,
                received_at_server: "2026-09-01T07:01:00.000Z",
                error: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    await syncPending(true);
    await syncPending(true);
    const stored = await listMutations();
    expect(stored[0].state).toBe("ACKED");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("replays an expired syncing lease with the original mutation identity", async () => {
    const mutation = await queueReport(report);
    storeSession("test-token", {
      id: "11111111-1111-4111-8111-111111111111",
      email: "farmer@example.com",
      display_name: "Synthetic Farmer",
      role: "FARMER",
    });
    const openRequest = indexedDB.open("sih-offline-cp1");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      openRequest.onsuccess = () => resolve(openRequest.result);
      openRequest.onerror = () => reject(openRequest.error);
    });
    const transaction = db.transaction("mutations", "readwrite");
    transaction.objectStore("mutations").put({
      ...mutation,
      state: "SYNCING",
      next_attempt_at: "2000-01-01T00:00:00.000Z",
    });
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            results: [
              {
                client_mutation_id: mutation.client_mutation_id,
                status: "DUPLICATE",
                resource_id: report.id,
                resource_version: 1,
                received_at_server: "2026-09-01T07:01:00.000Z",
                error: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await syncPending();

    const stored = await listMutations();
    expect(stored[0].client_mutation_id).toBe(mutation.client_mutation_id);
    expect(stored[0].idempotency_key).toBe(mutation.idempotency_key);
    expect(stored[0].state).toBe("ACKED");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("force-replays an active syncing lease after an interrupted navigation", async () => {
    const mutation = await queueReport(report);
    storeSession("test-token", {
      id: "11111111-1111-4111-8111-111111111111",
      email: "farmer@example.com",
      display_name: "Synthetic Farmer",
      role: "FARMER",
    });
    const openRequest = indexedDB.open("sih-offline-cp1");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      openRequest.onsuccess = () => resolve(openRequest.result);
      openRequest.onerror = () => reject(openRequest.error);
    });
    const transaction = db.transaction("mutations", "readwrite");
    transaction.objectStore("mutations").put({
      ...mutation,
      state: "SYNCING",
      next_attempt_at: "2999-01-01T00:00:00.000Z",
    });
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            results: [
              {
                client_mutation_id: mutation.client_mutation_id,
                status: "DUPLICATE",
                resource_id: report.id,
                resource_version: 1,
                received_at_server: "2026-09-01T07:01:00.000Z",
                error: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await syncPending(true);

    const stored = await listMutations();
    expect(stored[0].state).toBe("ACKED");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
