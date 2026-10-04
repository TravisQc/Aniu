## Why

Aniu 当前能够完成模拟交易，但交易结果只能在工作台和运行记录中查看，用户无法及时获知已提交的买卖委托。接入 PushPlus 后，可以在确实产生成功交易时把关键成交/委托信息发送给指定用户，同时保留“关闭即完全不发送”的控制，降低无交易运行带来的噪声。

## What Changes

- 在主要设置中新增“推送设置”标签页，提供 PushPlus 开关、Token、渠道和渠道配置项。
- 支持 PushPlus 的 `wechat`、`webhook`、`cmcc` 三个渠道；`webhook` 支持填写已在 PushPlus 中配置的渠道编码，`wechat`/`cmcc` 使用 Token 发送。
- 在模拟交易工具成功返回交易结果后发送通知；通知包含股票名称、股票代码、买入/卖出、交易数量和交易总额。
- 对交易工具失败、被拦截、撤单、查询以及没有产生交易的运行不发送通知。
- 将 PushPlus Token 等敏感凭证按现有密钥存储机制保存，接口只返回是否配置及脱敏信息，不回显完整凭证。
- 推送失败不回滚已经成功的模拟交易；记录可诊断的失败日志，并让原交易流程继续完成。

## Capabilities

### New Capabilities

- `pushplus-trade-notifications`: 配置 PushPlus 交易通知，并在成功模拟交易后按所选渠道发送交易摘要。

### Modified Capabilities

<!-- No existing OpenSpec capabilities are present; this change introduces a new one. -->

## Impact

- 后端：扩展 `AppSettings` 及其数据库持久化、设置 API DTO/Schema 和服务；新增 PushPlus HTTP 客户端/通知服务，并在 MX `trade` 工具成功路径接入。
- 前端：扩展主要设置导航和设置表单，增加开关、Token 脱敏状态、渠道选择及 webhook 配置。
- 测试：增加 PushPlus 请求构造与错误处理、设置读写/凭证保护、成功交易与非交易场景的通知触发测试，并更新 OpenAPI 前端类型。
- 外部依赖：调用 PushPlus `POST https://www.pushplus.plus/send`；需要用户提供有效的 `PUSHPLUS_TOKEN`/应用内 Token，并遵循 `webhook` 渠道编码和 `cmcc` 绑定要求。
