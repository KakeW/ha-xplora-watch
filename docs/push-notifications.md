# Push message notifications

Enable **Receive push messages** in the integration's options.
Polling can remain off. Each new chat push emits a Home Assistant event named
`xplora_watch_message`. This does not mark a message read or fetch location.

The user confirmed both text and voice notifications through HA to their iPhone
on 2026-09-14. The official iOS bundle also names `chat_emoticon`, `chat_image`
and `chat_video`; these still need live verification. Media is not downloaded
or attached to notifications.

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
