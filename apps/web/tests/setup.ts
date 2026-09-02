import "fake-indexeddb/auto";

import { afterEach, beforeEach, vi } from "vitest";

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
  });
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});
