# Troubleshooting

## Debug logging

```yaml
logger:
  logs:
    custom_components.xplora_watch: debug
```

## Xplora authentication expired

If Home Assistant reports that the Xplora API token expired and automatic recovery fails, the
integration starts Home Assistant's re-authentication flow. Enter the current Xplora account
password when prompted. This updates the existing config entry in place; do not remove and add the
integration again. The entry ID stays the same, so its locally stored location history remains
associated with the watches.

## Getting help

- Search [existing issues](https://github.com/distante/ha-xplora-watch/issues) before opening a
  new one.
- [Discussions](https://github.com/distante/ha-xplora-watch/discussions) is the place for
  questions that aren't bug reports.
- When filing a bug, include the **System Health** details from Home Assistant and the
  integration version, as the issue template asks.
