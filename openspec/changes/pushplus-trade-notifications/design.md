## Context

`AppSettings` is the single persisted application-settings aggregate. Its non-secret fields are stored on `app_settings`, while credentials such as the MX API key are stored through `SecretStoreRepository`; updates use a revision check through `/api/aniu/settings`. The main-settings UI is a tabbed surface, and the `TradeTool` calls `MxPaperTradingClient.trade()` after parsing and preflighting a limit order. The PushPlus skill defines a JSON `POST /send` contract, with `channel=webhook` requiring a configured channel code in `option` and `channel=cmcc` requiring no option.

## Goals / Non-Goals

**Goals:**

- Add a single, revision-safe PushPlus configuration to the existing settings aggregate.
- Keep PushPlus credentials out of API responses and application logs.
- Send one concise transaction summary after a successful buy/sell tool result, while isolating notification failures from trade success.
- Make channel and webhook-specific validation explicit and testable.

**Non-Goals:**

- No PushPlus delivery-result polling, callback endpoint, topic/friend management, or Open API integration.
- No support for channels other than `wechat`, `webhook`, and `cmcc`.
- No notification for cancellations, account queries, run summaries, or historical trades.
- No retry queue or durable outbox; a failed notification is logged and is not replayed automatically.

## Decisions

### 1. Model notification settings as a nested value object with a separate secret

Add a `PushplusSettings` value object to `AppSettings` containing `enabled`, `channel`, and optional `webhook_option`. Persist those non-secret values in a new `pushplus_settings_json` column on `app_settings`. Persist the PushPlus Token through the existing secret store under a dedicated `pushplus_token` key.

The settings DTO/API exposes `enabled`, `channel`, `webhook_option_configured`/masked metadata, and `token_configured`/masked metadata, while update requests accept the token as a write-only field. This mirrors the existing MX credential boundary and avoids introducing a second credential store.

Alternative considered: store the token in the JSON settings column. Rejected because it would bypass the repository's encryption and secret-redaction conventions.

### 2. Use a single selected channel per notification

The UI and API select one channel from the supported enum. The notifier maps it to the PushPlus `/send` body: `channel=wechat` or `channel=cmcc` without `option`, and `channel=webhook` with the configured channel code in `option`. The request uses `template=txt` so all three channels receive a predictable plain-text transaction summary.

Alternative considered: expose a multi-select and call `/batchSend`. Rejected for this scope because it adds per-channel option ordering, partial-success reporting, and more complicated settings without being required by the request.

### 3. Inject a notifier into the existing trade tool path

Create a small PushPlus client/notifier boundary that owns the HTTP request and message formatting. `AgentRuntimeFactory` supplies it when registering MX tools; `TradeTool.run()` keeps the parsed intent, calls the existing MX trade client, and only after a successful response attempts a notification. Notification exceptions are caught, logged with the selected channel and safe error text, and never propagated as trade errors.

The notifier reads the current settings and secret through a session-factory-backed settings repository at send time, so long-running workers do not hold stale tokens or toggles. The successful trade payload is normalized into stock name, code, direction, quantity, executed price, and total amount. Stock name is taken from the upstream trade result when present, with the related order/position snapshot as a fallback; the code remains available as a last-resort display value rather than preventing the original trade from completing.

Alternative considered: send from run-summary generation. Rejected because it cannot reliably distinguish an individual successful trade from a run with no trade and would delay the notification until the summary stage.

### 4. Keep the notification request synchronous but bounded

The notifier performs one awaited HTTP POST with a short client timeout and no automatic retries. This guarantees the tool has an opportunity to emit the message before returning, while the exception boundary preserves trade success if PushPlus is unavailable. The PushPlus response is checked for HTTP success and the documented response code; response bodies are never logged with the token.

Alternative considered: background task submission. Rejected because process shutdown or worker completion could discard an in-flight notification, and this feature does not yet have a durable outbox.

### 5. Add a backward-compatible database migration

Extend the startup schema upgrade to add `pushplus_settings_json` with an empty/default object when it is absent. Existing rows therefore load as disabled with no token. No data migration is required, and rollback can remove the feature code while leaving the additive column unused.

### 6. Extend the main-settings tab with a focused form

Add a `pushplus` tab/navigation item and a dedicated settings component. The form uses the existing query/mutation, revision-conflict, secret-input, and toast patterns. It shows the enabled toggle, channel selector, write-only Token field, and webhook option only when `webhook` is selected; save responses update the settings query cache without exposing secrets.

## Risks / Trade-offs

- [PushPlus credentials may be leaked] → Store only via `SecretStoreRepository`, redact request bodies and errors, and expose configured/last-four metadata only.
- [Upstream trade payload shape may vary] → Centralize field extraction and test common envelope variants; use order/position fallback and a nonempty code-based display fallback.
- [PushPlus latency can extend a tool call] → Use a bounded HTTP timeout and no retries; catch every integration failure after the MX trade succeeds.
- [A setting update can race with a running trade] → Resolve settings immediately before sending and retain existing revision conflict handling; a trade already submitted is never rolled back.
- [Existing SQLite files lack the new column] → Run the additive startup migration before settings access and cover fresh/legacy database fixtures.

## Migration Plan

1. Add the domain, persistence, API, notifier, and UI changes with tests.
2. On startup, add `pushplus_settings_json` for existing databases; defaults remain disabled.
3. Deploy with PushPlus disabled by default. Users configure and explicitly enable it from the new tab.
4. To roll back, disable the setting or remove the notifier wiring; the additive column and secret entry are harmless unused data.
