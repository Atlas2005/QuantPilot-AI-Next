# 通达信公式：QuantPilot 人工信号桥

本文档提供日频人工信号和盘中预测信号的通达信公式文本，供人工选股与持仓监控使用。
QuantPilot 负责分析，通达信只负责显示和人工操作。

## 前提

- 必须已安装 TQCenter（天勤）插件并配置 SIGNALS_TQ 虚拟合约。
- `publish_tdx_signals_tq_v1.py` 已成功运行并推送了 16 列数据。
- 公式通过 `SIGNALS_TQ` 读取数据。

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
| 11 | factor_score                       | float | 复用因子模块的综合分 |
| 12 | material_change                    | bool  | 相对上一条已发布记录是否发生实质变化 |
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

SIGNAL_VALID := SIGNALS_TQ#1;
PRED_STATE   := SIGNALS_TQ#2;
ENTRY_PROB   := SIGNALS_TQ#3;
CONT_PROB    := SIGNALS_TQ#4;
EXIT_PROB    := SIGNALS_TQ#5;
ENTRY_LOW    := SIGNALS_TQ#7;
ENTRY_HIGH   := SIGNALS_TQ#8;
INVALIDATION := SIGNALS_TQ#9;
TARGET1      := SIGNALS_TQ#10;
MATERIAL     := SIGNALS_TQ#12;
ENTRY_SIG    := SIGNALS_TQ#13;
HOLD_SIG     := SIGNALS_TQ#14;
WEAKENING    := SIGNALS_TQ#15;
EXIT_SIG     := SIGNALS_TQ#16;

VALID := SIGNAL_VALID = 1 AND MATERIAL = 1;

ENTRY_LOW_LINE: IF(VALID, ENTRY_LOW, DRAWNULL), COLORCYAN, DOTLINE;
ENTRY_HIGH_LINE: IF(VALID, ENTRY_HIGH, DRAWNULL), COLORCYAN, DOTLINE;
INVALIDATION_LINE: IF(VALID, INVALIDATION, DRAWNULL), COLORGREEN, DOTLINE;
TARGET1_LINE: IF(VALID, TARGET1, DRAWNULL), COLORRED, DOTLINE;

DRAWICON(VALID AND ENTRY_SIG = 1, LOW * 0.99, 1);
DRAWICON(VALID AND EXIT_SIG = 1, HIGH * 1.01, 2);
DRAWTEXT(VALID AND ENTRY_SIG = 1, LOW * 0.98,
        'QP-ENTRY ' + NUMTOSTR(ENTRY_PROB, 0) + '%'), COLORRED;
DRAWTEXT(VALID AND HOLD_SIG = 1, LOW * 0.98,
        'QP-HOLD ' + NUMTOSTR(CONT_PROB, 0) + '%'), COLORYELLOW;
DRAWTEXT(VALID AND WEAKENING = 1, HIGH * 1.02,
        'QP-WEAKENING'), COLORGRAY;
DRAWTEXT(VALID AND EXIT_SIG = 1, HIGH * 1.02,
        'QP-EXIT ' + NUMTOSTR(EXIT_PROB, 0) + '%'), COLORGREEN;
```

## 公式 1: QP_XG（选股公式）

**重要：QP_XG 只能有一个布尔输出。**

```c
{ QuantPilot 人工信号桥 - 选股公式 QP_XG }
{ 用途：条件选股，筛选 BUY 信号标的 }
{ 注意：此为参考信号，不构成精准买卖点建议 }

SIGNAL_VALID := SIGNALS_TQ#1;     { signal_valid }
CANDIDATE    := SIGNALS_TQ#2;     { candidate_flag }
ACTION       := SIGNALS_TQ#3;     { action_code }
FRESH        := SIGNALS_TQ#14;    { freshness_valid }
BUY_SIG      := SIGNALS_TQ#15;    { buy_signal }
CONFIDENCE   := SIGNALS_TQ#4;     { confidence_pct }
RISK         := SIGNALS_TQ#7;     { risk_pct }
FACTOR_RANK  := SIGNALS_TQ#6;     { factor_rank }
T1_SELLABLE  := SIGNALS_TQ#10;    { t1_sellable }
POS_STATE    := SIGNALS_TQ#9;     { position_state_code }
QUANTITY     := SIGNALS_TQ#11;    { current_quantity }

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

SIGNAL_VALID := SIGNALS_TQ#1;
ACTION       := SIGNALS_TQ#3;
CONFIDENCE   := SIGNALS_TQ#4;
FACTOR_RAW   := SIGNALS_TQ#5;
FACTOR_RANK  := SIGNALS_TQ#6;
RISK         := SIGNALS_TQ#7;
LIQUIDITY    := SIGNALS_TQ#8;
FRESH        := SIGNALS_TQ#14;
BUY_SIG      := SIGNALS_TQ#15;
SELL_SIG     := SIGNALS_TQ#16;

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

SIGNAL_VALID := SIGNALS_TQ#1;
ACTION       := SIGNALS_TQ#3;
CONFIDENCE   := SIGNALS_TQ#4;
POS_STATE    := SIGNALS_TQ#9;
T1_SELLABLE  := SIGNALS_TQ#10;
QUANTITY     := SIGNALS_TQ#11;
AVG_COST     := SIGNALS_TQ#12;
HOLDING      := SIGNALS_TQ#13;
FRESH        := SIGNALS_TQ#14;
BUY_SIG      := SIGNALS_TQ#15;
SELL_SIG     := SIGNALS_TQ#16;

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

SIGNAL_VALID := SIGNALS_TQ#1;
ACTION       := SIGNALS_TQ#3;
CONFIDENCE   := SIGNALS_TQ#4;
FACTOR_RANK  := SIGNALS_TQ#6;
POS_STATE    := SIGNALS_TQ#9;
QUANTITY     := SIGNALS_TQ#11;
AVG_COST     := SIGNALS_TQ#12;
FRESH        := SIGNALS_TQ#14;
BUY_SIG      := SIGNALS_TQ#15;
SELL_SIG     := SIGNALS_TQ#16;

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
2. QP_XG 安装为**选股公式**（条件选股）。
3. QP_RANK 安装为**副图公式**。
4. QP_STATE 安装为**副图公式**。
5. QP_OVERVIEW 安装为**主图叠加公式**（可选）。

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

- 这些公式依赖 SIGNALS_TQ 虚拟合约数据，需要 TQCenter 插件配合使用。
- QP_XG 只有一个布尔输出（`QP_XG`），符合通达信选股公式规范。
- 所有信号均为参考性质，不构成精准买卖点建议。
- 实际交易决策由人工完成，QuantPilot 不下达任何订单。
- `SIGNALS_TQ#N` 语法表示读取 TQ 虚拟合约的第 N 列数据。
