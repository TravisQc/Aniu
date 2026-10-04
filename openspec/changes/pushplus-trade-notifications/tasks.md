## 1. Settings Domain and Persistence

- [x] 1.1 Add a validated `PushplusSettings` value object and supported-channel enum with disabled-by-default behavior; verify unit tests cover defaults, unsupported channels, and webhook-option rules.
- [x] 1.2 Extend `AppSettings`, update commands, DTOs, and repository mapping for PushPlus non-secret settings; verify existing settings tests still pass and a round trip preserves enabled/channel/webhook values.
- [x] 1.3 Persist the PushPlus Token through `SecretStoreRepository` under a dedicated key without including it in serialized settings; verify repository tests assert encryption-path usage and response redaction.
- [x] 1.4 Add the additive `pushplus_settings_json` SQLite startup migration with a disabled/empty default; verify both a fresh schema and a legacy database load successfully.

## 2. Settings API and Frontend Configuration

- [x] 2.1 Extend `/api/aniu/settings` request/response schemas and service validation for PushPlus settings, including write-only token updates and webhook-specific validation; verify API tests cover enable, disable, invalid channel, missing webhook option, revision conflict, and masked responses.
- [x] 2.2 Add the PushPlus settings query/mutation types and client bindings, then regenerate or update the generated OpenAPI TypeScript schema; verify frontend type-checking succeeds.
- [x] 2.3 Add a “推送设置” main-settings tab and form using the existing revision-conflict, secret-input, loading/error, and toast patterns; verify component tests cover default disabled state, channel switching, conditional webhook field, save, and secret non-display.

## 3. PushPlus Notification Boundary

- [x] 3.1 Implement a bounded async PushPlus `/send` client using JSON POST, `template=txt`, supported channel mapping, and webhook `option`; verify unit tests assert exact request bodies for `wechat`, `cmcc`, and `webhook` and reject non-success responses.
- [x] 3.2 Implement trade-result normalization and plain-text message formatting for stock name, stock code, buy/sell direction, executed quantity, and total amount, including upstream envelope variants and order/position fallback; verify unit tests cover buy, sell, missing optional envelope nesting, and amount formatting.
- [x] 3.3 Implement a settings-aware trade notifier that resolves the latest enabled configuration at send time, skips disabled/unconfigured settings, and logs safe diagnostic failures without logging credentials; verify tests cover disabled, missing token, timeout, and PushPlus error cases.

## 4. Trade Integration

- [x] 4.1 Inject the notifier boundary through `AgentRuntimeFactory` and MX tool registration without changing existing read/cancel tool behavior; verify runtime construction tests still register the same tool set when notifications are disabled.
- [x] 4.2 Update `TradeTool` to notify only after a successful buy/sell response, preserving the original trade result when notification fails; verify tests cover successful buy/sell notification, blocked/failed trade silence, cancel/read silence, and push-failure isolation.
- [x] 4.3 Ensure the notifier uses the executed trade quantity/price returned by the simulator and does not infer a trade from a generic run or summary; verify run/tool activity tests keep zero-trade runs notification-free.

## 5. Verification and Delivery

- [x] 5.1 Add or update backend fixtures/fakes for PushPlus HTTP and settings secrets; verify the focused backend test suites pass for settings, MX tools, and notifier behavior.
- [x] 5.2 Add or update frontend mocks and navigation tests for the new tab; verify the focused frontend test suite and lint/type-check pass.
- [x] 5.3 Run the full backend and frontend test commands plus OpenAPI export validation; verify no existing settings, trading, or generated-schema tests regress.
