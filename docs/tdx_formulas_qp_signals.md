# 通达信公式：QuantPilot 人工信号桥

本文档提供日频人工信号和盘中预测信号的通达信公式文本，供人工选股与持仓监控使用。
QuantPilot 负责分析，通达信只负责显示和人工操作。

## 前提

- 必须已安装 TQCenter（天勤）插件，且通达信已经打开并登录。
- 外部 Python 脚本是支持的启动方式；脚本必须先调用 `tq.initialize(...)`，并在看图期间保持同一个连接存活。
- 公式的已验证语法是 `SIGNALS_TQ(ID, TYPE)`。本桥使用 `TYPE=0`，例如
  `T1:SIGNALS_TQ(1,0);`。
- `send_bt_data` 的 `data_list` 是按时间组织的行式矩阵：
  `data_list[i]` 对应 `time_list[i]`，行内第 N 个数值字符串由
  `SIGNALS_TQ(N,0)` 读取。`count` 必须等于时间记录数
  `len(time_list)`，不是信号列数。
- 发送前，每一个载荷标量都会被校验为有限的**数值字符串**；QuantPilot
  正式载荷的每一行固定为 16 列。
- `ErrorId=0` 只证明 TQ 接受了传输，不证明普通 K 线公式已经能够读到数据。

### Windows 普通 K 线资格烟雾测试

先单独运行非方形的 3 时间点 × 2 信号列探针。把 `--start` 改为普通
`000001.SZ` 一分钟图中连续存在的 3 根 K 线的第一根时间：

```powershell
python scripts/smoke_tdx_tq_display_v1.py --tdx-user-dir "D:\tongdaxin\PYPlugins\user" --symbol 000001.SZ --start 20260731140000 --probe non-square --hold-seconds 300
```

烟雾测试期间不要关闭 Python 窗口。在普通 `000001.SZ` 一分钟图上使用：

```c
T1:SIGNALS_TQ(1,0);
T2:SIGNALS_TQ(2,0);
```

三个时间点应依次看到 `(11.51,11.61)`、`(11.52,11.62)`、
`(11.53,11.63)`。旧的 2×2 探针是方阵，转置前后仍为 2×2，因此不能机械地
证明行列方向；3×2 探针消除了这个歧义。

精确复现官方 2 时间点 × 6 信号列形状时，单独运行：

```powershell
python scripts/smoke_tdx_tq_display_v1.py --tdx-user-dir "D:\tongdaxin\PYPlugins\user" --symbol 000001.SZ --start 20260731140000 --probe official-shape --hold-seconds 300
```

载荷两行严格为
`["1","143.41","200","0","0","0"]` 和
`["0","0","0","1","143.48","200"]`，`count=2`。

最后单独发送 QuantPilot 7 时间点 × 16 列测试状态；`--start` 所在图表必须
连续覆盖 7 根一分钟 K 线：

```powershell
python scripts/smoke_tdx_tq_display_v1.py --tdx-user-dir "D:\tongdaxin\PYPlugins\user" --symbol 000001.SZ --start 20260731140000 --probe quantpilot --hold-seconds 300
```

加载本文的 `QP_PREDICTION` 后，目标可见结果是“买 / 持 / 弱 / 卖 / 失效”
以及入场、失效、目标价位。
命令输出 JSON Lines，包含实际加载的 `tqcenter.py` 路径和 SHA-256、公开 API
签名、docstring、源码位置/摘要、精确载荷形状、TQ 返回值和 `run_id`。
`formula_set_data_info`、
`exec_to_tdx` 和返回的 `run_id` 都不会被当作本次发送的输入。

当前支持状态：`send_bt_data` 传输已支持；普通 K 线叠加在这条 Windows
烟雾测试产生可见结果前仍为 **pending / 未证明**。不要把 `ErrorId=0` 写成
“叠加成功”。

## 立即可用的 TQ 可见性回退

普通 K 线叠加未证明不会阻塞体验流程。回退直接复用现有体验计划和生命周期：

- 盘后把现有有序 top-N 候选写入 `QP体验` 自定义板块；不重新选股；
- 在 ENTRY、WEAKENING、EXIT、INVALIDATED 状态切换时调用 `send_warn`；
- 盘后在本机 API 支持时调用 `send_message`，内容包含候选排名和已缓存的
  DeepSeek 立场；
- 完整证据仍保留在现有 `latest_prediction.json` / `.csv`；不连接券商、不下单。

盘后命令（将前三个输入路径替换成当日已有生产文件；不需要手工编辑 JSON）：

```powershell
python scripts/run_continuous_paper_cycle_v1.py --production-manifest "runtime\production_candidate_manifest_v1.json" --decision-session 2026-08-03 --state-path "runtime\continuous_paper_state.json" --report-path "runtime\continuous_paper_2026-08-03.json" --input-json "runtime\continuous_paper_input_2026-08-03.json" --experience-plan-path "runtime\tdx_experience_plan_2026-08-04.json" --experience-top-n 10 --publish-tq-visibility --tdx-user-dir "D:\tongdaxin\PYPlugins\user" --tq-block-name "QP体验"
```

盘中 live-shadow 命令（只监控体验计划内的标的，并同时启用 TQ warning 回退）：

```powershell
python scripts/run_tdx_prediction_integration_v1.py --mode live-shadow --experience-plan "runtime\tdx_experience_plan_2026-08-04.json" --tdx-user-dir "D:\tongdaxin\PYPlugins\user" --start-time 20260804093000 --end-time 20260804150000 --history-count 500 --duration 14400 --store-provider memory --report-path "runtime\tdx_live_shadow_2026-08-04.json" --tdx-output-dir "runtime\tdx_signals_2026-08-04" --publish-to-tq --tq-block-name "QP体验"
```

`send_user_block`、`send_warn`、`send_message` 会按实际安装的 `tqcenter.py`
公开签名绑定参数；未知的必填参数不会被猜测。`send_message` 不可用时不会撤销
已经成功写入的候选板块。普通 K 线状态始终保持
`pending_windows_visual_confirmation`，直到图表上实际看到数值。

## TQ 列映射（16 列）

| ID | 字段名                  | 类型    | 含义                                   |
|----|-------------------------|---------|----------------------------------------|
| 1  | signal_valid            | bool    | 信号有效（1=有效，0=无效）             |
| 2  | candidate_flag          | bool    | 存在活跃候选标的                       |
| 3  | action_code             | int     | 0=NONE, 1=BUY, 2=HOLD, 3=SELL          |
| 4  | confidence_pct          | int     | 候选置信度 × 100                       |
| 5  | factor_score_raw        | float   | 因子综合原始分                         |
| 6  | factor_rank             | int     | 因子排名                               |
| 7  | risk_pct                | int     | 风险分 × 100                           |
| 8  | liquidity_pct           | int     | 流动性分 × 100                         |
| 9  | position_state_code     | int     | 0=未持仓, 1=持仓, 2=T+1锁定            |
| 10 | t1_sellable             | bool    | T+1可卖                                |
| 11 | current_quantity        | int     | 当前持仓股数                           |
| 12 | average_cost            | float   | 平均成本                               |
| 13 | holding_period_sessions | int     | 持仓周期（约交易时段数）               |
| 14 | freshness_valid         | bool    | 数据未过期                             |
| 15 | buy_signal              | bool    | 买入信号（action==BUY）                |
| 16 | sell_signal             | bool    | 卖出信号（action==SELL）               |

### TDX Level1 盘中预测记录的列映射

当输入 JSON 的 `schema_version` 为 `tdx_prediction_signal_v1` 时，同一个
`publish_tdx_signals_tq_v1.py` 会自动切换到以下映射。不要把本表和上面的
日频/账户映射混用于同一次发布。

| ID | 字段名                             | 类型  | 含义 |
|----|------------------------------------|-------|------|
| 1  | signal_valid                       | bool  | 预测记录有效 |
| 2  | prediction_state_code              | int   | 0=WATCH, 1=ENTRY, 2=HOLD, 3=WEAKENING, 4=EXIT, 5=INVALIDATED |
| 3  | entry_probability_pct              | int   | 入场/上涨概率 × 100 |
| 4  | continuation_probability_pct       | int   | 延续概率 × 100 |
| 5  | exit_probability_pct               | int   | 退出/下跌概率 × 100 |
| 6  | expected_return_bps                | float | 预期收益（基点）；确定性未训练归一化，不代表已验证 ML 概率 |
| 7  | entry_zone_low                     | float | 入场区间下沿 |
| 8  | entry_zone_high                    | float | 入场区间上沿 |
| 9  | invalidation_price                 | float | 失效价 |
| 10 | first_target_price                 | float | 第一目标价 |
| 11 | intraday_score                     | float | 固定、未训练的盘中特征综合分 |
| 12 | material_change                    | bool  | 可见生命周期状态发生切换；同状态不重复发标记 |
| 13 | entry_signal                       | bool  | ENTRY 状态 |
| 14 | hold_signal                        | bool  | HOLD 状态 |
| 15 | weakening_signal                   | bool  | WEAKENING 状态 |
| 16 | exit_or_invalidated_signal         | bool  | EXIT 或 INVALIDATED 状态 |

`reason_code`、完整 `evidence_refs` 和 `source_components` 是字符串，不能进入
TQ 的 16 列数值通道；它们保留在同次输出的 `latest_prediction.json` 和
`latest_prediction.csv` 中。

## 公式：QP_PREDICTION（盘中预测主图叠加）

此公式仅用于 `tdx_prediction_signal_v1` 发布结果。

```c
{ QuantPilot TDX Level1 盘中预测 - 主图叠加 }
{ 只显示预测状态和价位；不读取账户，不下单 }

SIGNAL_VALID := SIGNALS_TQ(1,0);
PRED_STATE   := SIGNALS_TQ(2,0);
ENTRY_PROB   := SIGNALS_TQ(3,0);
CONT_PROB    := SIGNALS_TQ(4,0);
EXIT_PROB    := SIGNALS_TQ(5,0);
ENTRY_LOW    := SIGNALS_TQ(7,0);
ENTRY_HIGH   := SIGNALS_TQ(8,0);
INVALIDATION := SIGNALS_TQ(9,0);
TARGET1      := SIGNALS_TQ(10,0);
MATERIAL     := SIGNALS_TQ(12,0);
ENTRY_SIG    := SIGNALS_TQ(13,0);
HOLD_SIG     := SIGNALS_TQ(14,0);
WEAKENING    := SIGNALS_TQ(15,0);
EXIT_SIG     := SIGNALS_TQ(16,0);

VALID := SIGNAL_VALID = 1 AND MATERIAL = 1;

ENTRY_LOW_LINE: IF(VALID, ENTRY_LOW, DRAWNULL), COLORCYAN, DOTLINE;
ENTRY_HIGH_LINE: IF(VALID, ENTRY_HIGH, DRAWNULL), COLORCYAN, DOTLINE;
INVALIDATION_LINE: IF(VALID, INVALIDATION, DRAWNULL), COLORGREEN, DOTLINE;
TARGET1_LINE: IF(VALID, TARGET1, DRAWNULL), COLORRED, DOTLINE;

DRAWICON(VALID AND ENTRY_SIG = 1, LOW * 0.99, 1);
DRAWICON(VALID AND EXIT_SIG = 1, HIGH * 1.01, 2);
DRAWTEXT(VALID AND PRED_STATE = 1, LOW * 0.98,
        '买 ' + NUMTOSTR(ENTRY_PROB, 0) + '%'), COLORRED;
DRAWTEXT(VALID AND PRED_STATE = 2, LOW * 0.98,
        '持 ' + NUMTOSTR(CONT_PROB, 0) + '%'), COLORYELLOW;
DRAWTEXT(VALID AND PRED_STATE = 3, HIGH * 1.02,
        '弱'), COLORGRAY;
DRAWTEXT(VALID AND PRED_STATE = 4, HIGH * 1.02,
        '卖 ' + NUMTOSTR(EXIT_PROB, 0) + '%'), COLORGREEN;
DRAWTEXT(VALID AND PRED_STATE = 5, HIGH * 1.02,
        '失效'), COLORGREEN;
```

盘中体验使用的 `latest_prediction.json` 只包含生命周期状态切换，因此上述
“买/持/弱/卖/失效”不会在每根 K 线上重复绘制。候选排名、盘后量化分、
DeepSeek 立场、预测提供方和 `EXPERIMENTAL SHADOW` 标签保留在同一 JSON
记录中；TQ 的 16 列数值上限无法再容纳这些字符串字段。

## 公式 1: QP_XG（选股公式）

**重要：QP_XG 只能有一个布尔输出。**

```c
{ QuantPilot 人工信号桥 - 选股公式 QP_XG }
{ 用途：条件选股，筛选 BUY 信号标的 }
{ 注意：此为参考信号，不构成精准买卖点建议 }

SIGNAL_VALID := SIGNALS_TQ(1,0);     { signal_valid }
CANDIDATE    := SIGNALS_TQ(2,0);     { candidate_flag }
ACTION       := SIGNALS_TQ(3,0);     { action_code }
FRESH        := SIGNALS_TQ(14,0);    { freshness_valid }
BUY_SIG      := SIGNALS_TQ(15,0);    { buy_signal }
CONFIDENCE   := SIGNALS_TQ(4,0);     { confidence_pct }
RISK         := SIGNALS_TQ(7,0);     { risk_pct }
FACTOR_RANK  := SIGNALS_TQ(6,0);     { factor_rank }
T1_SELLABLE  := SIGNALS_TQ(10,0);    { t1_sellable }
POS_STATE    := SIGNALS_TQ(9,0);     { position_state_code }
QUANTITY     := SIGNALS_TQ(11,0);    { current_quantity }

{ 选股条件：有效 + 新鲜 + BUY + 置信度阈值 + 未持仓 }
COND1 := SIGNAL_VALID = 1;
COND2 := FRESH = 1;
COND3 := BUY_SIG = 1;
COND4 := CONFIDENCE >= 50;        { 置信度 >= 50% }
COND5 := POS_STATE = 0;           { 未持仓 }
COND6 := RISK <= 80;              { 风险分 <= 80% }

{ QP_XG 唯一输出 }
QP_XG: COND1 AND COND2 AND COND3 AND COND4 AND COND5 AND COND6;
```

## 公式 2: QP_RANK（排序/副图指标）

```c
{ QuantPilot 人工信号桥 - 排序公式 QP_RANK }
{ 用途：副图显示因子排名、置信度、风险等关键列 }

SIGNAL_VALID := SIGNALS_TQ(1,0);
ACTION       := SIGNALS_TQ(3,0);
CONFIDENCE   := SIGNALS_TQ(4,0);
FACTOR_RAW   := SIGNALS_TQ(5,0);
FACTOR_RANK  := SIGNALS_TQ(6,0);
RISK         := SIGNALS_TQ(7,0);
LIQUIDITY    := SIGNALS_TQ(8,0);
FRESH        := SIGNALS_TQ(14,0);
BUY_SIG      := SIGNALS_TQ(15,0);
SELL_SIG     := SIGNALS_TQ(16,0);

{ 有效性过滤 }
VALID := SIGNAL_VALID = 1 AND FRESH = 1;

{ 副图曲线 }
CONFIDENCE_LINE: IF(VALID, CONFIDENCE, 0), COLORRED;
RISK_LINE: IF(VALID, RISK, 0), COLORGREEN;
LIQUIDITY_LINE: IF(VALID, LIQUIDITY, 0), COLORBLUE;
FACTOR_SCORE_LINE: IF(VALID, FACTOR_RAW * 100, 0), COLORYELLOW;

{ 买入/卖出标记 }
DRAWICON(VALID AND BUY_SIG = 1, CONFIDENCE, 1);   { 买入图标 }
DRAWICON(VALID AND SELL_SIG = 1, CONFIDENCE, 2);  { 卖出图标 }

{ 排名标注 }
DRAWTEXT(VALID AND FACTOR_RANK > 0, CONFIDENCE,
        'R' + NUMTOSTR(FACTOR_RANK, 0)), COLORWHITE;
```

## 公式 3: QP_STATE（持仓状态副图）

```c
{ QuantPilot 人工信号桥 - 持仓状态公式 QP_STATE }
{ 用途：显示持仓状态、T+1 锁定、成本参考 }
{ 重要：此公式只显示状态，不宣称是已验证的 15 分钟精准买卖点 }

SIGNAL_VALID := SIGNALS_TQ(1,0);
ACTION       := SIGNALS_TQ(3,0);
CONFIDENCE   := SIGNALS_TQ(4,0);
POS_STATE    := SIGNALS_TQ(9,0);
T1_SELLABLE  := SIGNALS_TQ(10,0);
QUANTITY     := SIGNALS_TQ(11,0);
AVG_COST     := SIGNALS_TQ(12,0);
HOLDING      := SIGNALS_TQ(13,0);
FRESH        := SIGNALS_TQ(14,0);
BUY_SIG      := SIGNALS_TQ(15,0);
SELL_SIG     := SIGNALS_TQ(16,0);

VALID := SIGNAL_VALID = 1 AND FRESH = 1;

{ 持仓状态柱状图：0=空, 1=持仓, 2=锁定 }
STATE_BAR: IF(VALID, POS_STATE, 0), COLORSTICK;

{ 持仓量标注（仅持仓时显示） }
DRAWTEXT(VALID AND QUANTITY > 0 AND POS_STATE >= 1,
         POS_STATE + 0.5,
         '持仓:' + NUMTOSTR(QUANTITY, 0)), COLORYELLOW;

{ T+1 锁定警告 }
DRAWTEXT(VALID AND POS_STATE = 2,
         POS_STATE + 0.3,
         'T+1锁定'), COLORGREEN;

{ 可卖标记 }
DRAWTEXT(VALID AND T1_SELLABLE = 1 AND POS_STATE = 1,
         POS_STATE + 0.1,
         '可卖'), COLORRED;

{ 成本线（仅持仓时显示） }
COST_LINE: IF(VALID AND QUANTITY > 0, AVG_COST, DRAWNULL),
           COLORGRAY, DOTLINE;

{ 买入/卖出文字提示 }
DRAWTEXT(VALID AND BUY_SIG = 1 AND POS_STATE = 0,
         2.5, '← 候选买入'), COLORRED;
DRAWTEXT(VALID AND SELL_SIG = 1 AND POS_STATE = 1 AND T1_SELLABLE = 1,
         2.5, '← 候选卖出'), COLORGREEN;
DRAWTEXT(VALID AND SELL_SIG = 1 AND POS_STATE = 2,
         2.5, '← 候选卖出(T+1锁定)'), COLORGRAY;
```

## 公式 4：QP_OVERVIEW（综合概览，可选）

```c
{ QuantPilot 人工信号桥 - 综合概览 }
{ 在主图叠加显示信号摘要 }

SIGNAL_VALID := SIGNALS_TQ(1,0);
ACTION       := SIGNALS_TQ(3,0);
CONFIDENCE   := SIGNALS_TQ(4,0);
FACTOR_RANK  := SIGNALS_TQ(6,0);
POS_STATE    := SIGNALS_TQ(9,0);
QUANTITY     := SIGNALS_TQ(11,0);
AVG_COST     := SIGNALS_TQ(12,0);
FRESH        := SIGNALS_TQ(14,0);
BUY_SIG      := SIGNALS_TQ(15,0);
SELL_SIG     := SIGNALS_TQ(16,0);

VALID := SIGNAL_VALID = 1 AND FRESH = 1;

{ 信号文字标注 }
DRAWTEXT(VALID AND BUY_SIG = 1, LOW * 0.98,
        'QP-BUY R' + NUMTOSTR(FACTOR_RANK, 0)), COLORRED;
DRAWTEXT(VALID AND SELL_SIG = 1, HIGH * 1.02,
        'QP-SELL'), COLORGREEN;
DRAWTEXT(VALID AND POS_STATE > 0, HIGH * 1.04,
        '持仓' + NUMTOSTR(QUANTITY, 0) + '股'), COLORYELLOW;
```

## 安装说明

1. 将上述公式文本复制到通达信公式管理器。
2. 盘中体验将 `QP_PREDICTION` 安装为**主图叠加公式**。
3. QP_XG 安装为**选股公式**（条件选股）。
4. QP_RANK 安装为**副图公式**。
5. QP_STATE 安装为**副图公式**。
6. QP_OVERVIEW 安装为**主图叠加公式**（可选）。

## TQ 16 列限制

TQ `send_bt_data` 最多支持 16 列数据。因此：

- TQ 仅输出二值 `t1_sellable`（ID 10）：`1` = 至少存在可卖数量，`0` = 完全锁定。
- TDX 公式通过 `position_state_code`（ID 9）显示持仓/锁定状态（0=空, 1=持仓有可卖, 2=完全锁定），结合 `t1_sellable` bit 判断是否有可操作数量。

### 精确可卖数量说明

**当前所有信号输出（JSON、CSV、TQ）均不提供精确 `sellable_quantity` 字段。** 各输出仅提供以下三个字段来描述持仓可卖状态：

| 字段 | JSON/CSV 键名 | TQ ID | 含义 |
|------|-------------|-------|------|
| 总持仓数量 | `current_quantity` | 11 | 当前该标的全部持仓股数 |
| 可卖标记 | `t1_sellable` | 10 | `true`/`1` = 至少存在一部分可卖，`false`/`0` = 完全锁定 |
| 持仓状态 | `position_state` | 9 | `no_position`/`holding`/`t1_locked` |

**局限性示例**：假设持仓 300 股，其中 200 股 T+1 已结算可卖、100 股当日买入被锁定：

- `action` 可以为 `SELL`（因存在可卖数量 > 0）
- `current_quantity` 显示 `300`
- `t1_sellable` 显示 `true` / `1`
- `position_state` 显示 `holding`

**当前输出无法区分以下两种情况**：全部 300 股可卖 vs 仅 200 股可卖。`t1_sellable` 是一个布尔标记，不反映可卖数量的精确值。

**交易者下单前必须以以下来源之一为准**：
- QuantPilot execution state（`state.json` 中 `settlement_lots`）
- 券商实际持仓可卖数量界面
- 通达信持仓面板中的实际可卖数量

TQ 16 列限制由 `send_bt_data` 协议决定，不可扩展。JSON/CSV 输出受 `TdxSignal` 数据合约约束，当前版本不包含 `sellable_quantity` 字段。

## 注意事项

- 这些公式依赖 `SIGNALS_TQ(ID,0)` 数据，需要 TQCenter 插件和仍在运行的
  初始化 Python 会话配合使用。
- QP_XG 只有一个布尔输出（`QP_XG`），符合通达信选股公式规范。
- 所有信号均为参考性质，不构成精准买卖点建议。
- 实际交易决策由人工完成，QuantPilot 不下达任何订单。
- `SIGNALS_TQ(N,0)` 表示读取本次 TQ 数据会话的第 N 个信号列；不要再使用
  本文旧版本中的 `SIGNALS_TQ#N` 写法。
