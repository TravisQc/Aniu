## Purpose

为模拟交易提供可控、可安全配置的 PushPlus 通知能力，让用户只在确实产生成功买入或卖出交易时收到包含关键交易信息的消息。

## ADDED Requirements

### Requirement: PushPlus notification settings are configurable

系统 SHALL 在主要设置中提供“推送设置”，允许用户查看和更新 PushPlus 通知开关、Token、发送渠道以及渠道配置。支持的渠道 SHALL 仅包括 `wechat`、`webhook` 和 `cmcc`；通知默认关闭。

#### Scenario: Default settings do not send notifications
- **WHEN** 用户首次读取主要设置且尚未配置 PushPlus
- **THEN** 推送开关为关闭状态，Token 显示为未配置，渠道为有效默认值，且系统不会发送任何 PushPlus 请求

#### Scenario: User saves enabled WeChat settings
- **WHEN** 用户提交开启状态、有效 PushPlus Token 和 `wechat` 渠道
- **THEN** 设置保存成功，后续成功交易使用该 Token 和渠道发送通知，读取设置时不得返回完整 Token

#### Scenario: User disables notifications
- **WHEN** 用户将推送开关保存为关闭
- **THEN** 设置保存成功，之后的交易不发送 PushPlus 请求，即使 Token 和渠道配置仍然存在

### Requirement: Channel configuration is validated and protected

系统 SHALL 对 PushPlus 设置执行渠道相关校验，并 SHALL 使用现有密钥保护机制保存 Token。`webhook` 渠道 SHALL 要求已配置的 PushPlus 渠道编码（对应发送接口的 `option`）；`wechat` 和 `cmcc` 不得要求 webhook 编码。设置读取接口 SHALL 仅返回是否已配置及有限的脱敏信息。

#### Scenario: Webhook settings require a channel code
- **WHEN** 用户选择 `webhook` 但未提供渠道编码，或提供空白渠道编码
- **THEN** 设置更新被拒绝并返回可定位到 webhook 配置的校验错误

#### Scenario: Unsupported channel is rejected
- **WHEN** 客户端提交除 `wechat`、`webhook`、`cmcc` 之外的渠道值
- **THEN** 设置更新被拒绝，已保存的配置保持不变

#### Scenario: Secret values are not exposed
- **WHEN** 用户读取设置或保存成功后查看响应
- **THEN** 响应不包含完整 PushPlus Token 或其他敏感凭证，只能包含 configured 状态及脱敏尾部信息（如适用）

### Requirement: Successful trades send a complete transaction summary

当 PushPlus 通知已开启且模拟交易成功产生买入或卖出结果时，系统 SHALL 向所选渠道发送一条消息。消息 SHALL 包含股票名称、股票代码、买入/卖出方向、交易数量和交易总额；发送请求 SHALL 使用 PushPlus `/send` POST API，并按渠道传递 `channel` 及 webhook 所需的 `option`。

#### Scenario: Successful buy sends a notification
- **WHEN** 模拟交易工具成功返回一笔买入交易，且推送设置已开启
- **THEN** 系统向配置的 PushPlus 渠道发送一条消息，消息包含该交易的股票名称、股票代码、买入方向、数量和交易总额

#### Scenario: Successful sell sends a notification
- **WHEN** 模拟交易工具成功返回一笔卖出交易，且推送设置已开启
- **THEN** 系统向配置的 PushPlus 渠道发送一条消息，消息包含该交易的股票名称、股票代码、卖出方向、数量和交易总额

#### Scenario: Transaction amount reflects the executed trade
- **WHEN** 成功交易返回成交数量和成交价格
- **THEN** 通知中的交易总额等于该交易实际数量乘以实际成交价格，并使用稳定的金额格式

### Requirement: Non-trades do not trigger notifications

系统 SHALL 仅对成功产生买入或卖出交易的结果触发通知。查询、撤单、被交易时段门禁拦截、参数校验失败、上游交易失败以及没有交易结果的运行 SHALL 不发送 PushPlus 消息。

#### Scenario: Failed or blocked trade sends nothing
- **WHEN** 交易工具返回错误、被阻止或未产生成功交易标识
- **THEN** 系统不调用 PushPlus 发送接口

#### Scenario: Cancel and read operations send nothing
- **WHEN** 运行仅执行撤单、账户查询、持仓查询或其他非买卖工具调用
- **THEN** 系统不调用 PushPlus 发送接口

#### Scenario: Disabled notification sends nothing
- **WHEN** 交易成功但推送开关处于关闭状态
- **THEN** 系统不调用 PushPlus 发送接口

### Requirement: Push failures do not undo trades

PushPlus 请求失败、超时或返回非成功响应时，系统 SHALL 保留已经成功的模拟交易结果，不得把交易改判为失败；系统 SHALL 记录可诊断的推送失败信息，并继续完成原有运行流程。

#### Scenario: PushPlus service returns an error
- **WHEN** 成功交易后的 PushPlus 请求返回网络错误或非成功响应
- **THEN** 交易工具仍返回成功交易结果，运行继续完成，并记录包含渠道和错误原因的推送失败日志
