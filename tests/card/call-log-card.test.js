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

  it("renders call direction and number clearly without exposing raw duration values", () => {
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
            call_log_list: [
              {
                time: "2026-10-18T16:18:13Z",
                callName: "Isi",
                callNumber: "+358401234567",
                callType: 1,
                callMode: 2,
                duration: 1792402190,
              },
              {
                time: "2026-10-18T17:18:13Z",
                data: { call_name: "Amanda", call_number: "+358501234567", call_type: "2", call_time: 1792405790 },
              },
            ],
            list: [],
          },
        },
      },
      callService: async (...args) => calls.push(args),
    };

    expect(el.shadowRoot.textContent).toContain("Lapsi soitti · Isi");
    expect(el.shadowRoot.textContent).toContain("Lapselle soitettiin · Amanda");
    expect(el.shadowRoot.textContent).toContain("Numero: +358401234567");
    expect(el.shadowRoot.textContent).toContain("Numero: +358501234567");
    expect(el.shadowRoot.textContent).not.toContain("1792402190");
    expect(el.shadowRoot.textContent).not.toContain("1792405790");
    expect(el.shadowRoot.textContent).not.toContain("Call mode");
    const callIcons = [...el.shadowRoot.querySelectorAll("li ha-icon")];
    expect(callIcons.map((icon) => icon.getAttribute("icon"))).toEqual(["mdi:phone-incoming", "mdi:phone-outgoing"]);
    expect(callIcons.every((icon) => icon.classList.contains("call-direction"))).toBe(true);
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
