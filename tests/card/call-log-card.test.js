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

  it("renders call records from the dedicated call-history cache", () => {
    const calls = [];
    const el = document.createElement("xplora-watch-call-log-card");
    el.setConfig({ entity: "sensor.watch_message" });
    document.body.appendChild(el);
    el.hass = {
      states: {
        "sensor.watch_message": {
          entity_id: "sensor.watch_message",
          state: "ok",
          last_updated: "2026-10-19T10:00:00Z",
          attributes: {
            call_log_list: [{
              time: "2026-10-18T16:18:13Z",
              callName: "Test contact",
              callNumber: "+358401234567",
              callType: "VOICE",
              callMode: "OUTGOING",
              duration: "00:02:14",
            }],
            list: [],
          },
        },
      },
      callService: async (...args) => calls.push(args),
    };

    expect(el.shadowRoot.textContent).toContain("Call · Test contact");
    expect(el.shadowRoot.textContent).toContain("00:02:14");
    expect(el.shadowRoot.textContent).toContain("OUTGOING");
    expect(el.shadowRoot.textContent).toContain(new Date("2026-10-18T16:18:13Z").toLocaleString());
    expect(calls).toEqual([]);
  });

  it("renders cached power events without duplicating the chat-feed copy", () => {
    const el = document.createElement("xplora-watch-call-log-card");
    el.setConfig({ entity: "sensor.watch_message" });
    document.body.appendChild(el);
    const event = { type: "POWER_OFF", msgId: "off-1", create: 1700000000 };
    el.hass = {
      states: {
        "sensor.watch_message": {
          entity_id: "sensor.watch_message",
          state: "ok",
          attributes: { call_log_list: [event], list: [event] },
        },
      },
      callService: async () => {},
    };

    expect(el.shadowRoot.textContent.match(/Watch switched off/g)).toHaveLength(1);
  });
});
