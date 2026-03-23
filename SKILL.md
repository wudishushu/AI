---
name: crypto-team
description: 币圈三兄弟 - 加密货币交易策略工具集（已封装为技能）
---

# 🐭 币圈三兄弟技能

已封装为独立技能，可按需调用。

## 功能模块

### 1. 自动巡检 (crypto_team_auto.py)
**定时任务模式：**
```bash
# 添加到crontab（每10分钟运行）
*/10 * * * * cd ~/.openclaw/skills/crypto-team/scripts && python3 crypto_team_auto.py >> crypto_team_log.md 2>&1
```

**配置：**
- `DISABLED = True` - 静默模式（只巡检不推送）
- `DISABLED = False` - 正常模式（发现信号会推送）

**功能：**
- 自动巡检持仓
- V2/V3/V4 策略分析
- 止盈止损监控
- 做空机会检测

### 2. 行情分析 (market_analyst_pro.py)
```bash
python3 ~/.openclaw/skills/crypto-team/scripts/market_analyst_pro.py [币种]
```
- 技术指标分析 (MA/RSI/布林带/ATR)
- 买卖信号评分
- 风控建议

### 3. 持仓诊断 (crypto_diagnostic.py)
```bash
python3 ~/.openclaw/skills/crypto-team/scripts/crypto_diagnostic.py
```
- 持仓监控
- 涨跌预警
- 24h行情异动

### 4. 交易操作 (crypto_trader.py)
```bash
python3 ~/.openclaw/skills/crypto-team/scripts/crypto_trader.py [命令]
```
- 市价/限价买入卖出
- 撤单
- 仓位管理

## 激活条件

当用户提及以下内容时激活：
- "炒币"、"加密货币"、"合约"
- "交易"、"买入"、"卖出"
- "行情分析"、"持仓"
- "币圈三兄弟"

## 定时任务设置

### 启用自动巡检
```bash
# 添加定时任务
(crontab -l 2>/dev/null; echo '*/10 * * * * cd ~/.openclaw/skills/crypto-team/scripts && python3 crypto_team_auto.py >> crypto_team_log.md 2>&1') | crontab -
```

### 启用推送
编辑 `crypto_team_auto.py`，将 `DISABLED = True` 改为 `DISABLED = False`

### 查看日志
```bash
tail -f ~/.openclaw/skills/crypto-team/scripts/crypto_team_log.md
```

## 配置

- OKX API: 已配置在 TOOLS.md
- 默认交易对: USDT-M 永续合约

## 注意事项

- ⚠️ 高杠杆风险 (100x)
- ⚠️ 建议低杠杆操作 (10-20x)
- ⚠️ 严格设置止盈止损
- ⚠️ 默认静默模式，不推送消息
