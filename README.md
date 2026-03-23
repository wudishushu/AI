# 🐭 币圈三兄弟

加密货币交易策略工具集 - 行情分析、持仓诊断、交易操作一体化解决方案。

[English](./README_EN.md) | [中文](./README.md)

---

## 📋 项目简介

币圈三兄弟是一套针对OKX交易所的自动化交易工具集，专注于USDT永续合约交易。包含三大核心模块：行情分析、持仓诊断、交易操作。

> ⚠️ **风险提示**：加密货币合约交易风险极高，请确保已充分了解风险后再使用。本工具仅供学习参考，不构成投资建议。

---

## 🎯 功能模块

### 1. 行情分析 (market_analyst_pro.py)

专业技术指标分析工具，支持多币种实时分析。

```bash
python3 scripts/market_analyst_pro.py [币种]
```

**分析指标：**
- 📊 MA均线系统 (5/10/20/60)
- 📈 RSI相对强弱指标
- 🎯 布林带支撑压力
- ⚡ ATR波动率
- 🔄 MACD指标

**输出：**
- 买卖信号评分 (1-10分)
- 支撑位/压力位
- 风控建议 (止损/止盈/仓位)

---

### 2. 持仓诊断 (crypto_diagnostic.py)

实时监控持仓状态，异常自动预警。

```bash
python3 scripts/crypto_diagnostic.py
```

**功能：**
- 📋 持仓列表查询
- 💰 资产统计
- 📈 盈亏计算
- 🚨 涨跌预警 (可配置阈值)
- 📊 24h行情异动

---

### 3. 交易操作 (crypto_trader.py)

支持市价/限价交易、撤单、仓位管理。

```bash
python3 scripts/crypto_trader.py [命令]
```

**支持命令：**
| 命令 | 说明 |
|------|------|
| `status` | 查看账户状态 |
| `buy <币种> <数量>` | 市价买入 |
| `sell <币种> <数量>` | 市价卖出 |
| `buy_limit <币种> <数量> <价格>` | 限价买入 |
| `sell_limit <币种> <数量> <价格>` | 限价卖出 |
| `cancel` | 撤单 |

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- OKX账号及API密钥

### 安装

```bash
# 克隆项目
git clone https://github.com/wudishushu/AI.git
cd AI

# 安装依赖
pip install requests hmac hashlib
```

### 配置API

在脚本中配置您的OKX API密钥：

```python
API_KEY = "your_api_key"
SECRET_KEY = "your_secret_key"
PASSPHRASE = "your_passphrase"
```

### 运行

```bash
# 分析BTC行情
python3 scripts/market_analyst_pro.py BTC

# 查看持仓
python3 scripts/crypto_diagnostic.py

# 账户状态
python3 scripts/crypto_trader.py status
```

---

## 📁 项目结构

```
crypto-team/
├── README.md                    # 中文说明
├── README_EN.md                 # English
├── SKILL.md                     # OpenClaw技能说明
├── .gitignore                   # Git忽略配置
└── scripts/
    ├── market_analyst_pro.py    # 行情分析
    ├── crypto_diagnostic.py     # 持仓诊断
    └── crypto_trader.py         # 交易操作
```

---

## ⚙️ 可选：自动巡检 (已禁用)

如需开启自动巡检功能，编辑 `crypto_team_auto.py`：

```python
DISABLED = False  # 设为False启用
```

### 添加定时任务

```bash
# 每10分钟运行
*/10 * * * * cd /path/to/scripts && python3 crypto_team_auto.py >> crypto_team_log.md 2>&1
```

### 风控参数

| 参数 | 值 |
|------|-----|
| 最大杠杆 | 100x (建议10-20x) |
| 止盈 | 5% |
| 止损 | 3% |
| 单币仓位 | ≤30% |

---

## 🔧 依赖

- `requests` - HTTP请求
- `hmac` - API签名
- `hashlib` - 加密
- `json` - 数据处理

安装依赖：
```bash
pip install requests
```

---

## 📝 开源协议

MIT License - 请自由使用，但需承担风险。

---

## ⚠️ 免责声明

1. 本工具仅供学习参考，不构成投资建议
2. 加密货币交易风险极高，可能导致全部损失
3. 请确保已充分了解交易规则和风险
4. 使用本工具即表示您同意自行承担风险

---

## 🐭 关于

Made with ❤️ by 无敌鼠鼠

如有问题，欢迎提交 Issue 或 Pull Request！
