import type {
  ReportPayload,
  SyncMutation,
  SyncMutationResult,
  SyncState,
} from "@sih/contracts";
import { openDB, type DBSchema, type IDBPDatabase } from "idb";

import { API_BASE_URL, getToken } from "./api";

export interface QueuedMutation extends SyncMutation {
  state: SyncState;
  attempts: number;
  next_attempt_at: string;
  last_error: string | null;
  resource_id: string | null;
}

interface OfflineDatabase extends DBSchema {
  mutations: {
    key: string;
    value: QueuedMutation;
    indexes: { "by-state": SyncState };
  };
  drafts: {
    key: string;
    value: { id: string; payload: Partial<ReportPayload>; saved_at: string };
  };
  references: {
    key: string;
    value: { key: string; value: unknown; updated_at: string };
  };
  media: {
    key: string;
    value: LocalMedia;
  };
}

export interface LocalMedia {
  id: string;
  blob: Blob;
  mime_type: "image/jpeg" | "image/png";
  checksum_sha256: string;
  state: "PENDING" | "UPLOADING" | "COMPLETE" | "FAILED";
  uploaded_chunks: number;
  last_error: string | null;
}

let databasePromise: Promise<IDBPDatabase<OfflineDatabase>> | null = null;
const SYNC_LEASE_MS = 60_000;

function database(): Promise<IDBPDatabase<OfflineDatabase>> {
  if (!databasePromise) {
    databasePromise = openDB<OfflineDatabase>("sih-offline-cp1", 2, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          const mutationStore = db.createObjectStore("mutations", {
            keyPath: "client_mutation_id",
          });
          mutationStore.createIndex("by-state", "state");
          db.createObjectStore("drafts", { keyPath: "id" });
          db.createObjectStore("references", { keyPath: "key" });
        }
        if (oldVersion < 2) db.createObjectStore("media", { keyPath: "id" });
      },
    });
  }
  return databasePromise;
}

export async function resetDatabaseHandleForTests(): Promise<void> {
  if (databasePromise) (await databasePromise).close();
  databasePromise = null;
}

export async function queueReport(
  payload: ReportPayload,
): Promise<QueuedMutation> {
  const mutation: QueuedMutation = {
    client_mutation_id: crypto.randomUUID(),
    idempotency_key: `report:${payload.id}:${crypto.randomUUID()}`,
    mutation_type: "CREATE_REPORT",
    base_version: null,
    created_at_device: payload.created_at_device,
    payload,
    state: "PENDING",
    attempts: 0,
    next_attempt_at: new Date().toISOString(),
    last_error: null,
    resource_id: null,
  };
  await (await database()).put("mutations", mutation);
  return mutation;
}

export async function saveDraft(
  id: string,
  payload: Partial<ReportPayload>,
): Promise<void> {
  await (
    await database()
  ).put("drafts", { id, payload, saved_at: new Date().toISOString() });
}

export async function removeDraft(id: string): Promise<void> {
  await (await database()).delete("drafts", id);
}

export async function setReference(key: string, value: unknown): Promise<void> {
  await (
    await database()
  ).put("references", { key, value, updated_at: new Date().toISOString() });
}

export async function getReference<T>(key: string): Promise<T | null> {
  const row = await (await database()).get("references", key);
  return (row?.value as T | undefined) ?? null;
}

export async function listMutations(): Promise<QueuedMutation[]> {
  return (await (await database()).getAll("mutations")).sort((a, b) =>
    b.created_at_device.localeCompare(a.created_at_device),
  );
}

export function chunkBlob(blob: Blob, chunkSize = 512 * 1024): Blob[] {
  const chunks: Blob[] = [];
  for (let offset = 0; offset < blob.size; offset += chunkSize) {
    chunks.push(
      blob.slice(offset, Math.min(offset + chunkSize, blob.size), blob.type),
    );
  }
  return chunks;
}

export async function prepareImage(file: File): Promise<LocalMedia> {
  if (
    !["image/jpeg", "image/png"].includes(file.type) ||
    file.size > 10 * 1024 * 1024
  ) {
    throw new Error("Choose a JPEG or PNG image no larger than 10 MiB.");
  }
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context)
    throw new Error("Image compression is unavailable on this device.");
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (value) =>
        value ? resolve(value) : reject(new Error("Image compression failed.")),
      "image/jpeg",
      0.76,
    ),
  );
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await blob.arrayBuffer(),
  );
  const checksum = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  const media: LocalMedia = {
    id: crypto.randomUUID(),
    blob,
    mime_type: "image/jpeg",
    checksum_sha256: checksum,
    state: "PENDING",
    uploaded_chunks: 0,
    last_error: null,
  };
  await (await database()).put("media", media);
  return media;
}

function wireMutation(mutation: QueuedMutation): SyncMutation {
  return {
    client_mutation_id: mutation.client_mutation_id,
    idempotency_key: mutation.idempotency_key,
    mutation_type: mutation.mutation_type,
    base_version: mutation.base_version,
    created_at_device: mutation.created_at_device,
    payload: mutation.payload,
  };
}

async function performSync(force = false): Promise<SyncMutationResult[]> {
  const token = getToken();
  if (!token || !navigator.onLine) return [];
  const db = await database();
  const all = await db.getAll("mutations");
  const now = new Date();
  const pending = all.filter((item) => {
    const attemptIsDue = new Date(item.next_attempt_at) <= now;
    // A navigation can abort the browser request after the server has already
    // accepted it. A user-forced sync must reclaim that lease immediately;
    // the unchanged UUID/idempotency key makes the replay safe server-side.
    if (item.state === "SYNCING") return force || attemptIsDue;
    return (
      (item.state === "PENDING" || item.state === "FAILED") &&
      (force || attemptIsDue)
    );
  });
  if (!pending.length) return [];

  const tx = db.transaction("mutations", "readwrite");
  for (const item of pending) {
    await tx.store.put({
      ...item,
      state: "SYNCING",
      attempts: item.attempts + 1,
      next_attempt_at: new Date(Date.now() + SYNC_LEASE_MS).toISOString(),
    });
  }
  await tx.done;

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/sync/batch`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ mutations: pending.map(wireMutation) }),
    });
    if (!response.ok)
      throw new Error(`Sync endpoint returned ${response.status}`);
    const body = (await response.json()) as { results: SyncMutationResult[] };
    const resultById = new Map(
      body.results.map((result) => [result.client_mutation_id, result]),
    );
    const updateTx = db.transaction("mutations", "readwrite");
    for (const item of pending) {
      const result = resultById.get(item.client_mutation_id);
      if (!result) {
        await updateTx.store.put(
          backoff(item, "Server omitted this mutation result"),
        );
      } else if (result.status === "APPLIED" || result.status === "DUPLICATE") {
        await updateTx.store.put({
          ...item,
          state: "ACKED",
          attempts: item.attempts + 1,
          resource_id: result.resource_id,
          last_error: null,
        });
      } else {
        await updateTx.store.put({
          ...backoff(item, result.error?.message ?? result.status),
          state: result.status === "CONFLICT" ? "CONFLICT" : "FAILED",
        });
      }
    }
    await updateTx.done;
    for (const item of pending) {
      const result = resultById.get(item.client_mutation_id);
      if (
        (result?.status === "APPLIED" || result?.status === "DUPLICATE") &&
        result.resource_id
      ) {
        await uploadMediaRefs(
          (item.payload as ReportPayload).media_refs ?? [],
          result.resource_id,
        );
      }
    }
    return body.results;
  } catch (error) {
    const updateTx = db.transaction("mutations", "readwrite");
    for (const item of pending) {
      await updateTx.store.put(
        backoff(item, error instanceof Error ? error.message : "Sync failed"),
      );
    }
    await updateTx.done;
    return [];
  }
}

let syncInFlight: Promise<SyncMutationResult[]> | null = null;

export function syncPending(force = false): Promise<SyncMutationResult[]> {
  if (syncInFlight) return syncInFlight;
  syncInFlight = performSync(force).finally(() => {
    syncInFlight = null;
  });
  return syncInFlight;
}

async function uploadMediaRefs(
  assetIds: string[],
  reportId: string,
): Promise<void> {
  const token = getToken();
  if (!token) return;
  const db = await database();
  for (const assetId of assetIds) {
    const media = await db.get("media", assetId);
    if (!media || media.state === "COMPLETE") continue;
    const chunks = chunkBlob(media.blob);
    let uploadedChunks = media.uploaded_chunks;
    try {
      await db.put("media", { ...media, state: "UPLOADING", last_error: null });
      for (
        let index = media.uploaded_chunks;
        index < chunks.length;
        index += 1
      ) {
        const form = new FormData();
        form.set("asset_id", media.id);
        form.set("report_id", reportId);
        form.set("chunk_index", String(index));
        form.set("total_chunks", String(chunks.length));
        form.set("checksum_sha256", media.checksum_sha256);
        form.set("file", chunks[index], `chunk-${index}.jpg`);
        const response = await fetch(
          `${API_BASE_URL}/api/v1/media/presign-or-upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: form,
          },
        );
        if (!response.ok)
          throw new Error(`Optional image upload returned ${response.status}`);
        uploadedChunks = index + 1;
        await db.put("media", {
          ...media,
          state: "UPLOADING",
          uploaded_chunks: uploadedChunks,
          last_error: null,
        });
      }
      await db.put("media", {
        ...media,
        state: "COMPLETE",
        uploaded_chunks: chunks.length,
        last_error: null,
      });
    } catch (error) {
      await db.put("media", {
        ...media,
        state: "FAILED",
        uploaded_chunks: uploadedChunks,
        last_error:
          error instanceof Error
            ? error.message
            : "Optional image upload failed",
      });
    }
  }
}

function backoff(item: QueuedMutation, message: string): QueuedMutation {
  const attempts = item.attempts + 1;
  const delaySeconds = Math.min(300, 2 ** Math.min(attempts, 8));
  return {
    ...item,
    state: "FAILED",
    attempts,
    last_error: message,
    next_attempt_at: new Date(Date.now() + delaySeconds * 1000).toISOString(),
  };
}
