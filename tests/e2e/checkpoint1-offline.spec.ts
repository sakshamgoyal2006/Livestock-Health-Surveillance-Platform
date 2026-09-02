import { expect, test } from "@playwright/test";

const apiBaseUrl = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

test("two offline reports synchronize exactly once and appear once in the vet queue", async ({
  context,
  page,
}) => {
  await page.goto("/login");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/dashboard/);

  await page.goto("/registry");
  const suffix = Date.now().toString();
  await page.getByTestId("farm-name").fill(`Synthetic E2E Farm ${suffix}`);
  await page.getByTestId("farm-village").fill("Synthetic E2E Village");
  await page.getByTestId("create-farm").click();
  await expect(page.getByRole("status")).toContainText("created");
  await page.getByTestId("animal-tag").fill(`SYN-E2E-${suffix}`);
  await page.getByTestId("create-animal").click();
  await expect(page.getByRole("status")).toContainText("Animal");

  await page.goto("/report/new");
  await expect(page.getByTestId("report-subject")).toContainText(
    `SYN-E2E-${suffix}`,
  );
  const subjectValue = await page
    .getByTestId("report-subject")
    .locator("option")
    .filter({ hasText: `SYN-E2E-${suffix}` })
    .getAttribute("value");
  expect(subjectValue).not.toBeNull();
  await page.getByTestId("report-subject").selectOption(subjectValue!);

  await context.setOffline(true);
  for (let index = 0; index < 2; index += 1) {
    await page.getByTestId("report-next").click();
    await page
      .getByTestId("report-severity")
      .selectOption(index === 0 ? "MODERATE" : "SEVERE");
    await page.getByTestId("report-mortality").fill(index.toString());
    await page.getByTestId("report-next").click();
    await page.getByTestId("report-village").fill("Synthetic E2E Village");
    await page.getByTestId("report-consent").check();
    await page.getByTestId("submit-report").click();
    await expect(page.getByTestId("report-stored")).toContainText("offline");
  }

  const reportIds = await page.evaluate(async () => {
    const request = indexedDB.open("sih-offline-cp1");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const transaction = db.transaction("mutations", "readonly");
    const getAll = transaction.objectStore("mutations").getAll();
    const rows = await new Promise<Array<{ payload: { id: string } }>>(
      (resolve, reject) => {
        getAll.onsuccess = () => resolve(getAll.result);
        getAll.onerror = () => reject(getAll.error);
      },
    );
    return rows.map((row) => row.payload.id);
  });
  expect(reportIds).toHaveLength(2);

  await context.setOffline(false);
  await page.goto("/sync");
  await page.getByTestId("sync-now").click();
  await expect
    .poll(async () => page.locator('[data-sync-state="ACKED"]').count())
    .toBe(2);

  const replayStatuses = await page.evaluate(async (baseUrl) => {
    const open = indexedDB.open("sih-offline-cp1");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    const getAll = db
      .transaction("mutations", "readonly")
      .objectStore("mutations")
      .getAll();
    const rows = await new Promise<Array<Record<string, unknown>>>(
      (resolve, reject) => {
        getAll.onsuccess = () => resolve(getAll.result);
        getAll.onerror = () => reject(getAll.error);
      },
    );
    const mutations = rows.map((row) => ({
      client_mutation_id: row.client_mutation_id,
      idempotency_key: row.idempotency_key,
      mutation_type: row.mutation_type,
      base_version: row.base_version,
      created_at_device: row.created_at_device,
      payload: row.payload,
    }));
    const token = localStorage.getItem("sih.dev.token");
    const response = await fetch(`${baseUrl}/api/v1/sync/batch`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ mutations }),
    });
    const payload = (await response.json()) as {
      results: Array<{ status: string }>;
    };
    return payload.results.map((result) => result.status);
  }, apiBaseUrl);
  expect(replayStatuses).toEqual(["DUPLICATE", "DUPLICATE"]);

  await page.goto("/login");
  await page.getByTestId("role-select").selectOption("VETERINARIAN");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/vet\/queue/);
  for (const reportId of reportIds) {
    await expect(page.locator(`tr[data-report-id="${reportId}"]`)).toHaveCount(
      1,
    );
  }
  const synchronizedRows = page.locator(
    reportIds.map((reportId) => `tr[data-report-id="${reportId}"]`).join(","),
  );
  const emergencyRow = synchronizedRows.filter({ hasText: "Mortality: 1" });
  await expect(emergencyRow).toHaveCount(1);
  const emergencyTriage = emergencyRow.locator('[data-testid^="triage-"]');
  await expect(emergencyTriage.getByTestId("urgency-tier")).toContainText(
    "EMERGENCY",
  );
  await expect(emergencyTriage).toContainText("Demo red-flag override applied");
  await emergencyTriage
    .getByText("Evidence, versions, and decision trace")
    .click();
  await expect(emergencyTriage).toContainText(
    "suspected conditions are not diagnoses",
  );
  await expect(emergencyTriage).toContainText("interpretable-risk-demo-1.0.0");
  await expect(emergencyTriage).toContainText("rules-demo-1.0.0");
  await expect(emergencyTriage).toContainText("triage-features-v1.0.0");
});
