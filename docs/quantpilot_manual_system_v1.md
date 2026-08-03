# QuantPilot 人工交易系统 v1

这条入口把现有的日度生产输入、七个 DeepSeek 桌、QPTY 自定义板块、TDX
Level1 和盘中预测状态连成一条不接券商、不下单的 Windows 工作流。候选顺序始终
来自已有 `production_input`；AI 只做注释和风险提示，部分或全部 AI 失败都不会清空
候选。

## 每日三个动作

在仓库根目录运行。API 密钥只从当前进程的 `DEEPSEEK_API_KEY` 读取；不要把密钥
写入命令、JSON、PowerShell 文件、日志、Markdown、测试快照或 Git。更新代码后，
在项目 `.venv` 内执行一次

```powershell
python -m pip install -e ".[windows-runtime,live-ai]"
```

只跑 AI 分析时可简化安装 `python -m pip install -e ".[live-ai]"`；两种方式都只
写入项目 `.venv`，不要手动安装到全局 Python。`live-ai` extra 提供
OpenAI-compatible 传输 SDK，支持并验证的范围为 `openai>=1.109.1,<2`（1.109.1
是实际完成离线测试和安装验证的版本；当前代码使用 `reasoning_effort`、
`extra_body` 和 `response_format`，更早的 1.x 不在支持范围）。`openai` 包仅是
DeepSeek 的 OpenAI-compatible transport SDK，不是独立 Provider。已手动安装的
2.x 不属于当前正式支持范围（尚未证明成功响应和 usage 解析完整兼容），正式安装
extra 时可能被降级到 1.109.1 系。

实际 AI Provider 是 DeepSeek：`openai` Python 包只作为兼容传输 SDK，
`base_url` 仍指向 `https://api.deepseek.com`，模型仍是 DeepSeek V4，从不切换
OpenAI endpoint。请求使用 `response_format={"type": "json_object"}`；DeepSeek
要求 Provider 实际收到的 system/user message 中包含字面量 `json`（不区分大小写），
否则在生成前返回 400。七个 Desk 共用 `DeepSeekAdvisoryAgent.build_prompt` 中的
同一段 `JSON_OUTPUT_CONTRACT_LINES` 结构化输出契约，统一要求：返回恰好一个有效
JSON 对象、响应只含 JSON、不用 Markdown 代码围栏、JSON 前后不含散文。

盘后分析并发布 `QPTY / QP候选`：

```powershell
.\scripts\windows\quantpilot-after-close.ps1 -ProductionInput "D:\QuantPilotData\production_input_2026-08-03.json"
```

包装器会显式传入 `--enable-live-ai`。只有现有
`DeepSeekStructuredEvidenceClient` 真正进入 `chat.completions.create` 后才计为一次
physical model call；确定性 fallback、离线结果和缺少客户端依赖的失败都计为零。

次日开盘前启动 Level1 监控（默认四小时）：

```powershell
.\scripts\windows\quantpilot-intraday.ps1
```

收盘后生成 JSON 和 Markdown 结果报告：

```powershell
.\scripts\windows\quantpilot-end-of-day.ps1
```

需要把三个动作顺序跑完时：

```powershell
.\scripts\windows\quantpilot-run-day.ps1 -ProductionInput "D:\QuantPilotData\production_input_2026-08-03.json"
```

持仓是可选项。可传入以股票代码为键、包含 `quantity`、`sellable_quantity` 和
`average_cost` 的 JSON；它只用于人工 T+1 提示，不会阻止监控，也不会生成订单。

## 状态与持久化

人工界面的初始 `WAIT` 对应现有引擎内部的 `WATCH`。状态序列是：

`WAIT -> ENTRY -> HOLD -> WEAKENING -> EXIT / INVALIDATED`

系统只消费已完成的一分钟 K 线。初始 WAIT 和可见状态切换先写入
`intraday/marker_events.json`、CSV 和当前状态文件，然后才尝试 TQ 传输。同一个
`signal_id` 不会重复；重启后不能把新标记插到该股票已保存的最后时间之前。
某个股票的历史数据或快照失败只记录为该股票错误，其他股票继续运行。

默认输出目录是 `.cache/quantpilot_manual_system_v1`，主要文件包括：

- `after_close_report.json` / `.md`
- `manual_plan.json`
- `intraday/market_data.json`
- `intraday/marker_events.json` / `.csv`
- `intraday/current_states.json`
- `intraday_report.json`
- `end_of_day_report.json` / `.md`

Windows PowerShell 5.1 读取报告时必须显式指定 UTF-8：

```powershell
$report = Get-Content -LiteralPath ".cache\quantpilot_manual_system_v1\after_close_report.json" -Raw -Encoding UTF8 | ConvertFrom-Json
```

仓库内 PowerShell 包装器只含 ASCII 字符；`QP候选` 由 Python 参数默认值提供。CLI
的单行机器输出会把非 ASCII 字符转义，因此 PowerShell 5.1 可以稳定解析。

这条人工工作流不读取账户能力、费率、Continuous Paper、PostgreSQL、Grafana、
测试存储或订单权限。

## 普通 K 线标记

首次运行盘后阶段会生成可安装包：

`<SystemDir>\tdx_marker_bundle\QP_MANUAL_MARKERS.formula.txt`

在通达信公式管理器新建主图公式 `QP_MANUAL_MARKERS`，粘贴该文件内容。盘中 Python
进程必须保持运行；Level1 和标记发布共用同一个已初始化的 TQ 会话。打开 QPTY
股票的一分钟普通 K 线，公式应显示买、持、弱、卖、失效和入场/失效/目标价位。
标记数据来自同一份持久事件日志，历史基线不会重复弹出警报。

`send_bt_data` 返回 `ErrorId=0` 只表示传输被接受。只有用户在真实 Windows
通达信普通 K 线上观察到标记，才能把可视叠加从
`pending_windows_visual_confirmation` 视为通过；未通过时，QPTY、`send_warn`
以及 JSON/CSV 仍是立即可用的回退。

## 有界真实验收

保持通达信已登录，并在环境中设置密钥后运行：

```powershell
.\scripts\windows\quantpilot-acceptance.ps1 -ProductionInput "D:\QuantPilotData\production_input_2026-08-03.json" -TdxUserDir "D:\tongdaxin\PYPlugins\user" -Duration 5
```

机器可读输出要求真实模型调用、至少一个成功桌、真实模型名、已落盘 AI 报告、非空
候选、QPTY 发布成功、盘中服务已启动、标记适配器已初始化，且券商和下单调用均为
零。正确验收证据（来自 `after_close_report.json` 的 `deepseek` 节）：

- `physical_model_calls > 0`
- `successful_desk_count > 0`
- `actual_deepseek_models` 非空
- `broker_calls == 0`
- `order_submission_calls == 0`

其中 `physical_model_calls` 只统计真正执行到 `chat.completions.create` 的请求：
Provider 返回 400/401/403/404/429/5xx 时该 Desk 计为 `failed`、`physical_call`
为 true，且不计入成功桌；import、配置或传输前失败计为零；确定性 fallback 不计
为 physical call，也不伪装成 DeepSeek 成功结果。全部自动检查通过时
`automated_checks_passed=true`；在用户真正看到普通 K 线标记前，整体 `accepted`
仍为 `false` 且状态为
`automated_runtime_passed_chart_observation_pending`，绝不由 `ErrorId=0` 推断可见。
