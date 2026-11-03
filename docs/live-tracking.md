# Live location tracking

Open the watch's current-location map and select **Start live tracking** (Finnish:
**Aloita live-seuranta**). Choose 5, 15 or 30 minutes. **Stop live tracking** ends the
session early. The watch's primary guardian account is required.

The integration calls Xplora's `startTrackingWatch`, then reads the latest stored
watch location every 15 seconds without issuing repeated `askWatchLocate` commands.
The map receives position updates through Home Assistant's normal entity updates;
you do not need to refresh the dashboard. The displayed fix age is still the watch's
reported timestamp. An active session does not mean that every read produced a new fix.
The card shows **Waiting for a new location** until it receives a fix timestamped
after the session started.
When the location-history sensor is enabled, new live fixes are also merged into
the local history archive under the date of the fix.

The session runs in Home Assistant, shared across browsers, and continues if you close
the map. It sends `endTrackingWatch` at expiry, on manual stop, integration unload,
and normal Home Assistant shutdown. An abrupt power loss cannot send a stop request.
If Xplora does not confirm stopping, the card displays an error and lets you retry Stop.

Automation actions:

```yaml
action: xplora_watch.start_live_tracking
data:
  device_id: YOUR_WATCH_DEVICE_ID
  duration_minutes: 5
```

```yaml
action: xplora_watch.stop_live_tracking
data:
  device_id: YOUR_WATCH_DEVICE_ID
```

The action accepts 1–30 minutes. Starting an already active session reuses it rather
than extending it or starting another loop. Three consecutive read failures stop the
session; authentication or rate-limit failures stop it immediately.

API evidence: the operator-supplied Xplora iOS bundle's `schema.graphqls`, lines
7586–7603, documents more frequent reports ("like per 15s"), asynchronous push, and
the Manager/own-ward restriction. The vendored client also exposes the start/end
queries. These are static interface facts. Actual watch cadence, permissions, and
the meaning of individual integer acknowledgement codes still require a real-watch
test. This implementation accepts a non-negative integer acknowledgement and rejects
missing values or the client's negative failure sentinel.
