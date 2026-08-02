# QuantPilot 人工交易系统 v1

这条入口把现有的日度生产输入、七个 DeepSeek 桌、QPTY 自定义板块、TDX
Level1 和盘中预测状态连成一条不接券商、不下单的 Windows 工作流。候选顺序始终
来自已有 `production_input`；AI 只做注释和风险提示，部分或全部 AI 失败都不会清空
候选。

## 每日三个动作

在仓库根目录运行。API 密钥只从当前进程的 `DEEPSEEK_API_KEY` 读取；不要把密钥
写入命令、JSON 或 PowerShell 文件。更新代码后先按现有 Windows 安装方式执行一次
`python -m pip install -e ".[windows-runtime]"`，确保既有 DeepSeek 客户端依赖可用。

盘后分析并发布 `QPTY / QP候选`：

```powershell
.\scripts\windows\quantpilot-after-close.ps1 -ProductionInput "D:\QuantPilotData\production_input_2026-08-03.json"
```

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
零。全部自动检查通过时 `automated_checks_passed=true`；在用户真正看到普通 K 线
标记前，整体 `accepted` 仍为 `false` 且状态为
`automated_runtime_passed_chart_observation_pending`，绝不由 `ErrorId=0` 推断可见。
