# Push message notifications

Enable **Receive push messages** in the integration's options.
Polling can remain off. Chat pushes are checked against the fetched thread by
message ID before emitting `xplora_watch_message`. Parent replies are suppressed
using the thread's sender, and notification text/type come from the actual chat
(including emoji). Push sender identifiers alone are not sufficient.

An incoming push also starts a background fetch of that watch's chat thread and
media (or all selected watches if its sender cannot be mapped directly), so the
card can use the cached messages when opened. Thread contents are
published before media downloads finish and before the notification is emitted.
Verification stops at the first matching watch and does not wait for the activity
feed. Media, activity and status refreshes continue in the background after verification.
The fetched unread messages also update the counter without waiting for polling.
Fetching does not mark messages read. The background status refresh also refreshes location. Media downloads can still
be in progress when the card opens. If verification fails or the message is absent
from the fetched window, a generic notification is emitted with `chat_unknown`;
an outgoing echo cannot be suppressed through thread verification in that case.

The user confirmed both text and voice notifications through HA to their iPhone
on 2026-09-14. The official iOS bundle also names `chat_emoticon`, `chat_image`
and `chat_video`; these still need live verification. Media is cached for the chat
card but is not attached to notifications.

Create an automation in YAML and replace the notification action with your phone's
actual action from Developer Tools > Actions:

```yaml
alias: Xplora new message
triggers:
  - trigger: event
    event_type: xplora_watch_message
actions:
  - action: notify.mobile_app_your_iphone
    data:
      title: "{{ trigger.event.data.sender_name }}: uusi viesti"
      message: "{{ trigger.event.data.text or 'Uusi viesti kellosta – avaa Xplora-kortti.' }}"
mode: queued
max: 20
```

Events contain `entry_id`, `sender_id`, `sender_name`, `message_id`,
`message_type`, `text` and `timestamp`. The sender ID is the push identifier,
not necessarily the integration's watch UID. Do not match names to watch UIDs.
Pushes apply to the account, including watches not selected for HA entities.
Filter `sender_id` or `entry_id` in automations if needed.
Verified messages also contain `wuid` and, when its watch device is registered,
`device_id`. Only this verified device identity is used for quick-reply routing.

## iOS quick replies

Import the [Xplora notification and quick-reply blueprint](https://github.com/KakeW/ha-xplora-watch/blob/main/blueprints/automation/xplora_message_quick_reply.yaml)
under Home Assistant **Settings → Automations & scenes → Blueprints → Import blueprint**.
Create an automation from it and select your watches and Companion phone device.
Disable the old Xplora message-notification automation to avoid duplicate notifications.

On the iPhone, expand/long-press the notification and select **Vastaa** (Reply).
The text-input action runs in the background; HA does not open the dashboard.
The reply is sent through `xplora_watch.send_message` to the same HA watch device
that produced the verified notification. The blueprint handles both notifications
and replies without holding a waiting automation open. Empty replies and devices
not selected in the blueprint are ignored. Each phone should use its own blueprint
automation. A real iPhone/Apple Watch test is still needed to confirm the displayed
input UI and end-to-end sending on the user's devices.

This uses Companion's documented `behavior: textInput`, `activationMode: background`
and `mobile_app_notification_action.reply_text` fields:
[Actionable Notifications](https://companion.home-assistant.io/docs/notifications/actionable-notifications/).

Receiver credentials and the most recent 2048 sender/message identifiers are
stored privately in `.storage/xplora_watch.<entry_id>.push`. Back them up with HA
and do not post this file in issues. Message contents are not stored there.
The receiver reconnects after failures and retries failed startup after five
minutes. Registration is repeated after HA observes a replaced Xplora session.

Replay protection is persisted before firing the event: this suppresses normal
restart duplicates, but a crash between persistence and event delivery can lose
an alert. This is not a guaranteed-delivery messaging service. Replays older than
the retained ID window can generate another event.

Enabling push registers HA as a recipient on your Xplora account and may replace
the official app's recipient. Disabling stops the HA listener; it does not restore
the old app token. Sign into the official app again to register it there.
The temporary Mac receiver is not required once HA is enabled.
