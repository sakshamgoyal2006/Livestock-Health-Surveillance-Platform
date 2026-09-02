import { expect, test } from "@playwright/test";

test("offline report reaches vet verification and independent GIS layers", async ({
  context,
  page,
}) => {
  await page.goto("/login");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/dashboard/);

  const suffix = Date.now().toString();
  await page.goto("/registry");
  await page.getByTestId("farm-name").fill(`Synthetic CP3 Farm ${suffix}`);
  await page.getByTestId("farm-village").fill("Village B");
  await page.getByTestId("create-farm").click();
  await expect(page.getByRole("status")).toContainText("created");
  await page.getByTestId("animal-tag").fill(`SYN-CP3-${suffix}`);
  await page.getByTestId("create-animal").click();
  await expect(page.getByRole("status")).toContainText("Animal");

  await page.goto("/report/new");
  const subject = page
    .getByTestId("report-subject")
    .locator("option")
    .filter({ hasText: `SYN-CP3-${suffix}` });
  await page.getByTestId("report-subject").selectOption((await subject.getAttribute("value"))!);
  await context.setOffline(true);
  await page.getByTestId("report-next").click();
  await page.getByTestId("report-severity").selectOption("MODERATE");
  await page.getByTestId("report-next").click();
  await page.getByTestId("report-village").fill("Village B");
  await page.getByTestId("report-consent").check();
  await page.getByTestId("submit-report").click();
  await expect(page.getByTestId("report-stored")).toContainText("offline");
  const reportId = await page.evaluate(async () => {
    const request = indexedDB.open("sih-offline-cp1");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const getAll = db.transaction("mutations", "readonly").objectStore("mutations").getAll();
    const rows = await new Promise<Array<{ payload: { id: string } }>>((resolve, reject) => {
      getAll.onsuccess = () => resolve(getAll.result);
      getAll.onerror = () => reject(getAll.error);
    });
    return rows.at(-1)!.payload.id;
  });

  await context.setOffline(false);
  await page.goto("/sync");
  await page.getByTestId("sync-now").click();
  await expect.poll(async () => page.locator('[data-sync-state="ACKED"]').count()).toBe(1);

  await page.goto("/login");
  await page.getByTestId("role-select").selectOption("VETERINARIAN");
  await page.getByTestId("login-submit").click();
  const row = page.locator(`tr[data-report-id="${reportId}"]`);
  await expect(row).toHaveCount(1);
  await row.getByRole("link", { name: "Review case" }).click();
  await expect(page.getByTestId("truth-statuses")).toContainText("PENDING");
  await page.getByTestId("assign-case").click();
  await page.getByTestId("start-review").click();
  await page.getByLabel("Verified label").fill("SYNTHETIC_RESPIRATORY_SYNDROME");
  await page.getByRole("button", { name: "Correct label" }).click();
  await expect(page.getByTestId("truth-statuses")).toContainText("VET_VERIFIED");
  await expect(page.getByTestId("truth-statuses")).toContainText("NOT_REQUESTED");

  await page.goto("/login");
  await page.getByTestId("role-select").selectOption("DISTRICT_OFFICER");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/officer/);
  await expect(page.getByTestId("surveillance-map")).toBeVisible();
  await expect(page.getByTestId("suspected-layer").first()).toBeVisible();
  await expect(page.getByTestId("verified-layer").first()).toBeVisible();
  await expect(page.getByTestId("lab-layer").first()).toBeVisible();
  await expect(page.getByTestId("hotspot-candidate").first()).toContainText(
    "not a confirmed outbreak",
  );
});
