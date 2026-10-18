import { beforeAll, describe, expect, it } from "vitest";

import { loadBundle } from "./helpers.js";

beforeAll(async () => {
  await loadBundle();
});

describe("call log cache-first rendering", () => {
  it("renders cached call events without requesting the server on open", () => {
    const calls = [];
    const el = document.createElement("xplora-watch-call-log-card");
    el.setConfig({ entity: "sensor.watch_message" });
    document.body.appendChild(el);
    el.hass = {
      states: {
        "sensor.watch_message": {
          entity_id: "sensor.watch_message",
          state: "ok",
          last_updated: "2026-06-27T10:00:00Z",
          attributes: {
            wuid: "watch1",
            entry_id: "entry1",
            list: [{ type: "POWER_ON", msgId: "on-1", create: 1700000000 }],
          },
        },
      },
      callService: async (...args) => calls.push(args),
    };

    expect(el.shadowRoot.textContent).toContain("Watch switched on");
    expect(calls).toEqual([]);
  });
});
