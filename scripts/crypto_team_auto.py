#!/usr/bin/env python3
# ========== 禁用配置 ==========
DISABLED = True  # 设为True则禁用所有监控和推送（静默模式）
# ==============================

if DISABLED:
    import sys
    print("⚠️ 本脚本已禁用（静默模式）")
    sys.exit(0)

"""
币圈三兄弟 - 定时自动运行脚本 V4 (优化版)
功能：
1. 自动巡检持仓
2. 无持仓时启动V2策略分析
3. 有持仓时也持续监控市场机会
4. 止盈止损监控提醒
5. 做空机会检测

V4优化:
- 即使有持仓也继续扫描市场机会
- 新增止盈止损监控 (止盈5%, 止损-3%)
- 新增做空机会检测 (RSI超买时)
- 有持仓时也检测做空机会

用法: 添加到crontab
*/10 * * * * cd /Users/shirenyushangren/.openclaw/workspace && python3 crypto_team_auto.py >> /tmp/crypto_team.log 2>&1
"""

import hmac
import hashlib
import base64
import requests
import json
import os
import sys
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict

# V3策略模块 (多维确认)
try:
    from rsi_strategy_v3 import scan_all_coins_all as v3_scan_all
    HAS_V3_STRATEGY = True
except:
    HAS_V3_STRATEGY = False
    print("⚠️ V3策略模块未加载")

# 舆情分析模块
try:
    from sentiment_analysis import get_global_sentiment, analyze_coin_sentiment
    HAS_SENTIMENT = True
except:
    HAS_SENTIMENT = False
    print("⚠️ 舆情模块未加载")

# 收益统计模块
try:
    from profit_stats import record_trade
    HAS_PROFIT_STATS = True
except:
    HAS_PROFIT_STATS = False

# 前向声明
def record_opportunity(coin, direction, entry_price, score=0, reasons=""):
    pass

# 推送通知模块 (使用OpenClaw原生飞书)
NOTIFY_QUEUE_FILE = "/Users/shirenyushangren/.openclaw/workspace/.notify_queue.json"

def queue_notify(title, content):
    """将通知加入队列"""
    try:
        import json
        queue = []
        if os.path.exists(NOTIFY_QUEUE_FILE):
            with open(NOTIFY_QUEUE_FILE, "r") as f:
                queue = json.load(f)
        
        queue.append({
            "title": title,
            "content": content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        with open(NOTIFY_QUEUE_FILE, "w") as f:
            json.dump(queue, f, ensure_ascii=False)
        
        print(f"✅ 通知已加入队列: {title}")
    except Exception as e:
        print(f"⚠️ 通知队列失败: {e}")

def process_notify_queue():
    """处理通知队列并发送飞书消息"""
    if not os.path.exists(NOTIFY_QUEUE_FILE):
        return
    
    try:
        import json
        with open(NOTIFY_QUEUE_FILE, "r") as f:
            queue = json.load(f)
        
        if not queue:
            return
        
        msg = queue.pop(0)
        
        with open(NOTIFY_QUEUE_FILE, "w") as f:
            json.dump(queue, f)
        
        # 发送飞书消息
        title = msg.get("title", "")
        content = msg.get("content", "")
        text = f"🐭 {title}\n\n{content}"
        
        print(f"📢 发送通知: {title}")
        
        # 使用OpenClaw CLI发送飞书消息
        import subprocess
        
        result = subprocess.run(
            ["openclaw", "message", "send", 
             "--channel", "feishu",
             "--target", "ou_d42a845b7f627665f57fdc2f410322e8",
             "--message", text],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0 and "Sent via Feishu" in result.stdout:
            print(f"✅ 飞书通知已发送: {title}")
        else:
            print(f"⚠️ 飞书通知发送失败: {result.stderr[:100] if result.stderr else result.stdout[:100]}")
            # 重新加入队列
            queue.insert(0, msg)
            with open(NOTIFY_QUEUE_FILE, "w") as f:
                json.dump(queue, f)
        
    except Exception as e:
        print(f"⚠️ 处理通知队列失败: {e}")

def get_support(coin):
    """获取币种支撑位 (MA20 + 布林下轨)"""
    try:
        url = f"https://www.okx.com/api/v5/market/kline?instId={coin}-USDT-SWAP&bar=1h&limit=50"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("code") == "0" and data["data"]:
            candles = [[float(x[1]), float(x[4])] for x in data["data"][::-1]]  # [open, close]
            
            # MA20
            closes = [c[1] for c in candles[-20:]]
            ma20 = sum(closes) / 20
            
            # 布林下轨
            std = statistics.stdev(closes)
            bb_lower = ma20 - 2 * std
            
            # 支撑位取两者较低者
            support = min(ma20, bb_lower)
            
            return {
                "support": support,
                "ma20": ma20,
                "bb_lower": bb_lower,
                "current": closes[-1]
            }
    except:
        pass
    return None

def get_multi_timeframe_ma(coin):
    """多周期MA分析: 1h(大趋势) + 5m(短线) + 1m(超短)"""
    try:
        result = {}
        
        # 1小时线 - 大趋势
        r1 = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1h&limit=30", timeout=10)
        if r1.json().get("code") == "0":
            closes = [float(x[4]) for x in r1.json()["data"][::-1]]
            ma5 = sum(closes[-5:]) / 5
            ma20 = sum(closes[-20:]) / 20
            result["1h"] = {"ma5": ma5, "ma20": ma20, "trend": "金叉" if ma5 > ma20 else "死叉"}
        
        # 5分钟线 - 短线
        r5 = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=5m&limit=50", timeout=10)
        if r5.json().get("code") == "0":
            closes = [float(x[4]) for x in r5.json()["data"][::-1]]
            ma5 = sum(closes[-5:]) / 5
            ma20 = sum(closes[-20:]) / 20
            result["5m"] = {"ma5": ma5, "ma20": ma20, "trend": "金叉" if ma5 > ma20 else "死叉"}
        
        # 1分钟线 - 超短
        r1m = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1m&limit=50", timeout=10)
        if r1m.json().get("code") == "0":
            closes = [float(x[4]) for x in r1m.json()["data"][::-1]]
            ma5 = sum(closes[-5:]) / 5
            ma20 = sum(closes[-20:]) / 20
            result["1m"] = {"ma5": ma5, "ma20": ma20, "trend": "金叉" if ma5 > ma20 else "死叉"}
        
        return result
    except:
        pass
    return None

# ============ 舆情分析模块 ============
TAVILY_API_KEY = "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"

def get_sentiment():
    """获取市场舆情/情绪"""
    try:
        # 搜索加密货币新闻
        url = "https://api.tavily.com/search"
        headers = {"Content-Type": "application/json"}
        data = {
            "query": "bitcoin ethereum crypto market news",
            "api_key": TAVILY_API_KEY,
            "max_results": 3,
            "include_answer": True
        }
        
        resp = requests.post(url, json=data, headers=headers, timeout=15)
        result = resp.json()
        
        # 获取各币种涨跌计算情绪
        prices = get_prices()
        if not prices:
            return None, "无法获取"
        
        changes = [d["change"] for d in prices.values()]
        avg_change = sum(changes) / len(changes)
        
        if avg_change > 2:
            sentiment = "乐观 🟢"
        elif avg_change > 0:
            sentiment = "偏多 🟡"
        elif avg_change > -2:
            sentiment = "中性 😐"
        else:
            sentiment = "悲观 🔴"
        
        return sentiment, f"平均涨跌 {avg_change:+.1f}%"
    except Exception as e:
        return None, f"获取失败: {e}"

def filter_by_sentiment(coin, prices):
    """根据舆情过滤币种"""
    sentiment, _ = get_sentiment()
    
    # 获取该币种涨跌幅
    change = prices.get(coin, {}).get("change", 0)
    
    # 舆情悲观时，只买跌超过2%的
    if sentiment and "悲观" in sentiment:
        if change >= -2:
            return False, "舆情悲观"
    
    # 舆情乐观时，可以买
    return True, "通过"
from datetime import datetime
from pathlib import Path
from typing import Dict

# ============ 配置 =============
API_KEY = "4ef7631d-a7cb-4050-abfc-8a7ffe9c10d5"
SECRET_KEY = "EAF62B2E51A2AE8B4D03A7F22CB4DF3C"
PASSPHRASE = "Gen.248613"

# 策略配置
MAX_LEVERAGE = 100  # 最大杠杆 100倍!
AUTO_TRADE = True  # 自动交易模式
# ================================

WORKSPACE = Path("/Users/shirenyushangren/.openclaw/workspace")
LOG_FILE = WORKSPACE / "crypto_team_log.md"

def log(msg):
    """日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def generate_signature(timestamp, method, path, body=""):
    message = timestamp + method + path + body
    mac = hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def okx_request(method, path, body=""):
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    signature = generate_signature(timestamp, method, path, body)
    
    url = f"https://www.okx.com{path}"
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=15)
        else:
            resp = requests.post(url, headers=headers, data=body, timeout=15)
        return resp.json()
    except Exception as e:
        log(f"❌ API失败: {e}")
        return None

def get_prices():
    """获取主流币价格"""
    symbols = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX"]
    prices = {}
    for sym in symbols:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={sym}-USDT-SWAP"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("code") == "0" and data["data"]:
                t = data["data"][0]
                last = float(t["last"])
                open_24h = float(t.get("open24h", last))
                high_24h = float(t["high24h"])
                low_24h = float(t["low24h"])
                change = ((last - open_24h) / open_24h * 100) if open_24h else 0
                
                # 区间位置
                range_24h = high_24h - low_24h
                position = ((last - low_24h) / range_24h * 100) if range_24h else 50
                
                prices[sym] = {
                    "price": last, 
                    "change": change,
                    "position": position,
                    "high": high_24h,
                    "low": low_24h
                }
        except:
            pass
    return prices

def get_balance():
    """获取余额"""
    return okx_request("GET", "/api/v5/account/balance")

def get_positions():
    """获取合约持仓"""
    return okx_request("GET", "/api/v5/account/positions?instType=SWAP")

def calc_dynamic_tp_sl(coin, side, prices):
    """
    根据行情动态计算止盈止损
    - 止盈: 距离压力位/支撑位的空间
    - 止损: 距离支撑位/压力位的空间
    - 使用ATR和24h波动区间
    """
    if coin not in prices:
        # 默认值
        return 0.05, 0.03 if side == "buy" else 0.03
    
    data = prices[coin]
    price = data["price"]
    high = data.get("high", price * 1.01)
    low = data.get("low", price * 0.99)
    
    # 计算24h波动率
    volatility = (high - low) / price * 100  # 如 5%
    
    log(f"  📊 {coin} 波动分析:")
    log(f"     当前价: ${price:.2f}")
    log(f"     24h区间: ${low:.2f} ~ ${high:.2f} (波动{violatility:.1f}%)")
    
    if side == "buy":
        # 做多: 止盈看压力位，止损看支撑位
        # 计算支撑位和压力位
        support = low  # 简单: 24h最低为支撑
        resistance = high  # 24h最高为压力
        
        # 上涨空间
        upside = (resistance - price) / price * 100
        # 下跌空间
        downside = (price - support) / price * 100
        
        log(f"     支撑位: ${support:.2f} (可跌{downside:.1f}%)")
        log(f"     压力位: ${resistance:.2f} (可涨{upside:.1f}%)")
        
        # 动态止盈: 止盈位设为压力位的80%位置
        if upside > 3:
            tp_percent = min(upside * 0.8, 10) / 100  # 最大10%
        else:
            tp_percent = 0.03  # 最小3%
        
        # 动态止损: 止损位设为支撑位的50%位置
        if downside > 2:
            sl_percent = min(downside * 0.5, 5) / 100  # 最大5%
        else:
            sl_percent = 0.02  # 最小2%
        
    else:
        # 做空: 止盈看支撑位，止损看压力位
        support = low
        resistance = high
        
        # 下跌空间
        downside = (price - support) / price * 100
        # 上涨空间
        upside = (resistance - price) / price * 100
        
        log(f"     支撑位: ${support:.2f} (可跌{downside:.1f}%)")
        log(f"     压力位: ${resistance:.2f} (可涨{upside:.1f}%)")
        
        # 动态止盈: 做空止盈是价格下跌
        if downside > 3:
            tp_percent = min(downside * 0.8, 10) / 100
        else:
            tp_percent = 0.03
        
        # 动态止损: 做空止损是价格上涨
        if upside > 2:
            sl_percent = min(upside * 0.5, 5) / 100
        else:
            sl_percent = 0.02
    
    log(f"     动态止盈: {tp_percent*100:.1f}% | 动态止损: {sl_percent*100:.1f}%")
    
    return tp_percent, sl_percent

def set_leverage(inst_id, lever):
    """设置杠杆"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    method = "POST"
    path = "/api/v5/account/set-leverage"
    
    order_data = {
        "instId": inst_id,
        "lever": str(lever),
        "mgnMode": "isolated"
    }
    
    body = json.dumps([order_data])
    message = timestamp + method + path + body
    
    result = okx_request(method, path, body)
    return result

def open_position(inst_id, side, size, lever=10):
    """开仓 - 全仓模式"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    method = "POST"
    path = "/api/v5/trade/order"
    
    order_data = {
        "instId": inst_id,
        "tdMode": "cross",  # 全仓模式
        "side": side,
        "ordType": "market",
        "sz": str(size),
        "lever": str(lever)
    }
    
    body = json.dumps(order_data)  # 不是数组!
    message = timestamp + method + path + body
    
    result = okx_request(method, path, body)
    return result

def place_limit_order(inst_id, side, price, size):
    """限价挂单"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    method = "POST"
    path = "/api/v5/trade/order"
    
    order_data = {
        "instId": inst_id,
        "tdMode": "cross",
        "side": side,
        "ordType": "limit",
        "sz": str(size),
        "px": str(price)
    }
    
    body = json.dumps(order_data)
    message = timestamp + method + path + body
    
    result = okx_request(method, path, body)
    return result

def set_tp_sl(inst_id, size, tp_price, sl_price):
    """设置止盈止损 - 全仓模式"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    method = "POST"
    path = "/api/v5/trade/order-algo"
    
    order_data = {
        "instId": inst_id,
        "tdMode": "cross",  # 全仓模式
        "side": "sell",
        "ordType": "conditional",
        "sz": str(size),
        "tpTriggerPx": str(tp_price),
        "tpOrdPx": "-1",
        "slTriggerPx": str(sl_price),
        "slOrdPx": "-1"
    }
    
    body = json.dumps(order_data)  # 不是数组!
    message = timestamp + method + path + body
    
    result = okx_request(method, path, body)
    return result

def analyze_and_trade():
    """分析并自动交易"""
    log("🎯 开始V2策略分析...")
    
    prices = get_prices()
    if not prices:
        log("❌ 无法获取价格")
        return False
    
    # 盘面预测分析（选币参考）
    log("🔮 盘面预测分析...")
    try:
        # 尝试从v2版本导入
        from market_forecast_v2 import predict_enhanced as pred_v2
        from market_forecast import predict_multi_timeframe as pred_v1
    except:
        try:
            from market_forecast import predict_enhanced
        except:
            pred_v2 = None
            pred_v1 = None
    
    if pred_v2 or pred_v1:
        predictions = []
        for coin in prices.keys():
            try:
                if pred_v2:
                    result = pred_v2(coin, "1H")
                else:
                    result = pred_v1(coin)
                if result:
                    pred = result.get("prediction") or (result.get("periods", {}).get("1H", {}).get("prediction"))
                    conf = result.get("confidence") or (result.get("periods", {}).get("1H", {}).get("confidence"))
                    if pred and pred != "震荡":
                        predictions.append({
                            "coin": coin,
                            "pred": pred,
                            "conf": conf or 50,
                            "price": prices[coin]["price"]
                        })
            except:
                pass
        
        # 按置信度排序
        predictions.sort(key=lambda x: x["conf"], reverse=True)
        
        if predictions:
            log("   热门预测:")
            for p in predictions[:3]:
                emoji = "📈" if p['pred'] == "涨" else "📉"
                log(f"      {p['coin']}: {emoji} {p['pred']} ({p['conf']}%)")
        else:
            log("   无明显趋势")
    else:
        log("   预测模块未安装")
    
    # 获取余额
    balance = get_balance()
    available = 0
    total_eq = 0
    if balance and balance.get("code") == "0":
        total_eq = float(balance["data"][0].get("totalEq", 0))
        for row in balance["data"][0]["details"]:
            if row["ccy"] == "USDT":
                available = float(row.get("availBal", 0))
                locked = float(row.get("frozenBal", 0))
    
    log(f"  💰 总资产: ${total_eq:.2f} | 可用: ${available:.2f}")
    
    # 有持仓时不检查余额
    if has_position:
        log("  ✅ 已有持仓，继续监控")
        return True
    
    if available < 5:
        log("  ⚠️ 余额不足，无法建仓")
        return False
    
    # V2策略 - 回调买入模式（修复追高问题）
    results = []
    for coin, data in prices.items():
        score = 0
        reasons = []
        
        # 获取支撑位数据
        support_data = get_support(coin)
        if not support_data:
            continue
            
        current_price = data["price"]
        support = support_data["support"]
        distance_pct = (current_price - support) / current_price * 100
        
        # 🔥 核心逻辑：等回调到支撑位再买！
        # 距离支撑位 0-2% → 强烈买入
        if 0 <= distance_pct <= 2:
            score += 5
            reasons.append(f"触及支撑 {support:.2f}")
        # 距离支撑位 2-4% → 观望等回调
        elif distance_pct < 0:
            score += 3  # 已跌破支撑，不买
            reasons.append("跌破支撑")
        elif distance_pct <= 4:
            score += 2
            reasons.append(f"接近支撑 {distance_pct:.1f}%")
        else:
            score -= 2  # 离支撑太远，不买
            reasons.append(f"离支撑远 {distance_pct:.1f}%")
        
        # 跌幅过滤：只买回调的，不追涨
        change = data["change"]
        if change < -2:  # 跌超过2%才考虑
            score += 1
            reasons.append(f"回调{abs(change):.1f}%")
        elif change > 2:  # 涨超过2%不买了
            score -= 3
            reasons.append("涨幅过大不追")
        
        # 🔥 多周期MA分析：大趋势(1h) + 短线(5m) + 超短(1m)
        ma_data = get_multi_timeframe_ma(coin)
        if ma_data:
            # 1h大趋势判断
            if "1h" in ma_data and ma_data["1h"]:
                trend_1h = ma_data["1h"]["trend"]
                if trend_1h == "死叉":
                    score -= 2
                    reasons.append("1h死叉(下跌)")
                elif trend_1h == "金叉":
                    score += 2
                    reasons.append("1h金叉(上涨)")
            
            # 5m短线判断
            if "5m" in ma_data and ma_data["5m"]:
                trend_5m = ma_data["5m"]["trend"]
                if trend_5m == "死叉":
                    score -= 1
                    reasons.append("5m死叉")
                elif trend_5m == "金叉":
                    score += 1
                    reasons.append("5m金叉")
        
        results.append({
            "coin": coin,
            "score": score,
            "reasons": reasons,
            "price": data["price"]
        })
    
    # 排序
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # 检查是否有结果
    if not results:
        # 检查做空机会
        log("  🔍 检查做空机会 (RSI超买)...")
        short_candidates = []
        for coin, data in prices.items():
            short = analyze_short_opportunity(coin, prices)
            if short and short["score"] >= 2:
                short_candidates.append(short)
        
        if short_candidates:
            short_candidates.sort(key=lambda x: x["score"], reverse=True)
            best_short = short_candidates[0]
            coin = best_short['coin']
            price = best_short['price']
            inst_id = f"{coin}-USDT-SWAP"
            
            log(f"  📉 发现做空候选: {coin}")
            log(f"     RSI: {best_short['rsi']:.0f}")
            log(f"     原因: {', '.join(best_short['reasons'])}")
            
            # ====== 团队会议讨论 - 做空 ======
            log("")
            log("="*50)
            log("🤝 团队会议 - V2策略做空讨论")
            log("="*50)
            
            log("👁️ 诊断员:")
            log(f"   - 当前持仓: {has_position}")
            log(f"   - 账户状态: 正常")
            log(f"   - RSI超买信号: {best_short['rsi']:.0f}")
            log(f"   - 建议: 通过做空")
            
            log("📊 分析师:")
            log(f"   - 做空得分: {best_short['score']}")
            log(f"   - 做空理由: {', '.join(best_short['reasons'])}")
            log(f"   - 建议: 做空 {coin}")
            
            # 动态计算止盈止损
            tp_percent, sl_percent = calc_dynamic_tp_sl(coin, "sell", prices)
            
            log("🗳️ 团队决策:")
            log(f"   - 策略: V2严格策略-做空")
            log(f"   - 交易币种: {coin}")
            log(f"   - 参考价格: ${price}")
            log(f"   - 动态止盈: {tp_percent*100:.1f}% | 动态止损: {sl_percent*100:.1f}%")
            log(f"   - 决策: 自动执行")
            log("")
            
            # 执行做空
            log(f"  🚀 执行做空: {coin} @ ${price}")
            result = open_position(inst_id, "sell", 3, 100)
            
            if result and result.get("code") == "0":
                order_id = result["data"][0]["ordId"]
                log(f"  ✅ 做空成功! 订单ID: {order_id}")
                
                # 通知和记录
                msg = f"**交易类型:** 做空\n**币种:** {coin}\n**价格:** ${price:.2f}\n**数量:** 3张"
                queue_notify("交易提醒", msg)
                if HAS_PROFIT_STATS:
                    record_trade(coin, "做空", price, 3, "开仓", 0)
                
                # 动态计算止盈止损
                tp_percent, sl_percent = calc_dynamic_tp_sl(coin, "sell", prices)
                tp_price = price * (1 - tp_percent)  # 做空止盈是价格跌
                sl_price = price * (1 + sl_percent)  # 做空止损是价格涨
                
                log(f"  🛡️ 动态止盈: {tp_percent*100:.1f}% (${tp_price:.2f})")
                log(f"  🛡️ 动态止损: {sl_percent*100:.1f}% (${sl_price:.2f})")
                
                # 必须设置止盈止损
                log(f"  ⚙️ 正在设置止盈止损...")
                tp_sl_result = set_tp_sl(inst_id, 3, tp_price, sl_price)
                
                if tp_sl_result and tp_sl_result.get("code") == "0":
                    log(f"  ✅ 止盈止损设置成功!")
                    log(f"  📢 已自动做空并设置止盈止损!")
                    return True
                else:
                    log(f"  ⚠️ 止盈止损设置失败: {tp_sl_result}")
                    log(f"  ⚠️ 开仓成功但未设置止盈止损，请手动设置!")
                    return True  # 开仓成功，只是止盈止损设置失败
            else:
                log(f"  ❌ 做空失败: {result}")
        else:
            log("  ⏳ 无交易候选，继续观望")
        return False
    
    # 选择最佳
    best = results[0]
    log(f"  📊 最佳: {best['coin']} (得分: {best['score']})")
    for r in best.get("reasons", []):
        log(f"     • {r}")
    # 只有得分>0才执行
    if best["score"] <= 0:
        log("  ⏳ 无买入信号，继续观望")
        return False
    
    # 舆情过滤
    coin = best["coin"]
    price = best["price"]
    sentiment, sentiment_info = get_sentiment()
    log(f"  📡 舆情: {sentiment} ({sentiment_info})")
    
    # 检查是否通过舆情过滤
    passed, reason = filter_by_sentiment(coin, prices)
    if not passed:
        log(f"  ❌ 舆情过滤: {coin} {reason}，跳过")
        return False
    
    # ====== 团队会议讨论 (自动记录) ======
    log("")
    log("="*50)
    log("🤝 团队会议 - V2策略开仓讨论")
    log("="*50)
    
    # Step 1: 诊断员发言
    log("👁️ 诊断员:")
    log(f"   - 当前持仓: {has_position}")
    log(f"   - 账户状态: 正常")
    log(f"   - 建议: 通过")
    
    # Step 2: 分析师发言
    log("📊 分析师:")
    log(f"   - V2得分: {best['score']}")
    log(f"   - 买入理由: {', '.join(best['reasons'])}")
    log(f"   - 舆情: {sentiment} ({sentiment_info})")
    log(f"   - 建议: 买入 {coin}")
    
    # Step 3: 讨论决策 - 动态计算止盈止损
    tp_percent, sl_percent = calc_dynamic_tp_sl(coin, "buy", prices)
    
    log("🗳️ 团队决策:")
    log(f"   - 策略: V2严格策略")
    log(f"   - 交易币种: {coin}")
    log(f"   - 参考价格: ${price}")
    log(f"   - 动态止盈: {tp_percent*100:.1f}% | 动态止损: {sl_percent*100:.1f}%")
    log(f"   - 决策: 自动执行")
    log("")
    
    # 执行建仓 - 灵活选择挂单/市价
    inst_id = f"{coin}-USDT-SWAP"
    
    # 检查是否已到支撑位
    distance_pct = abs(price - support) / support * 100
    
    if distance_pct < 0.2:
        # 距离支撑<0.5%，直接市价买入
        log(f"  🚀 执行买入: {coin} @ 市价 (距支撑{distance_pct:.2f}%)")
        result = open_position(inst_id, "buy", 3, 100)
    else:
        # 距离支撑>0.5%，挂单等回调
        log(f"  🚀 执行挂单: {coin} @ ${price} (距支撑{distance_pct:.2f}%)")
        result = place_limit_order(inst_id, "buy", price, 3)
    
    if result and result.get("code") == "0":
        order_id = result["data"][0]["ordId"]
        log(f"  ✅ 开仓成功! 订单ID: {order_id}")
        
        # 通知和记录
        msg = f"**交易类型:** 做多\n**币种:** {coin}\n**价格:** ${price:.2f}\n**数量:** 3张"
        queue_notify("交易提醒", msg)
        if HAS_PROFIT_STATS:
            record_trade(coin, "做多", price, 3, "开仓", 0)
        
        # 动态计算止盈止损
        tp_percent, sl_percent = calc_dynamic_tp_sl(coin, "buy", prices)
        tp_price = price * (1 + tp_percent)  # 做多止盈是价格上涨
        sl_price = price * (1 - sl_percent)  # 做多止损是价格跌
        
        log(f"  🛡️ 动态止盈: {tp_percent*100:.1f}% (${tp_price:.2f})")
        log(f"  🛡️ 动态止损: {sl_percent*100:.1f}% (${sl_price:.2f})")
        
        # 必须设置止盈止损
        log(f"  ⚙️ 正在设置止盈止损...")
        tp_sl_result = set_tp_sl(inst_id, 3, tp_price, sl_price)
        
        if tp_sl_result and tp_sl_result.get("code") == "0":
            log(f"  ✅ 止盈止损设置成功!")
            log(f"  📢 已自动建仓并设置止盈止损!")
            return True
        else:
            log(f"  ⚠️ 止盈止损设置失败: {tp_sl_result}")
            log(f"  ⚠️ 开仓成功但未设置止盈止损，请手动设置!")
            return True  # 开仓成功，只是止盈止损设置失败
    else:
        log(f"  ❌ 开仓失败: {result}")
        return False

def analyze_short_opportunity(coin, prices):
    """分析做空机会 - RSI超买时"""
    try:
        import statistics
        # 获取1小时K线计算RSI
        r = requests.get(f'https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1h&limit=50', timeout=10)
        if r.json().get('code') != '0':
            return None
        
        data = r.json()['data']
        closes = [float(x[4]) for x in data[::-1]]
        
        # 计算RSI
        gains = []
        losses = []
        for i in range(1, 15):
            change = closes[-i] - closes[-i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # 计算支撑/压力位
        ma20 = sum(closes[-20:]) / 20
        std = statistics.stdev(closes[-20:])
        bb_upper = ma20 + 2 * std
        bb_lower = ma20 - 2 * std
        
        current_price = prices.get(coin, {}).get('price', closes[-1])
        
        # 做空条件 (需要团队确认)
        reasons = []
        can_short = False
        
        if rsi >= 70:  # RSI超买
            reasons.append(f"RSI={rsi:.0f}超买")
            can_short = True
        
        if current_price >= bb_upper:  # 触及上轨压力
            reasons.append("触及布林上轨")
            can_short = True
        
        # 检查MA死叉
        ma5 = sum(closes[-5:]) / 5
        if ma5 < ma20:
            reasons.append("MA5<MA20死叉")
        
        if can_short:
            return {
                "coin": coin,
                "rsi": rsi,
                "price": current_price,
                "bb_upper": bb_upper,
                "reasons": reasons,
                "score": len(reasons)
            }
    except:
        pass
    return None

# ============ 快速投机策略 (V4) ============
# 更激进，适合快速抓短线机会
# 特点：
# - 使用1m/5m周期，更快反应
# - 距离支撑位可放宽到5%
# - 小止盈3% + 小止损2%，高频交易
# - 涨幅容忍度更高(<3%)

def fast_strategy_analyze():
    """快速投机策略分析 V4 (含多周期MA)
    
    多周期MA配置:
    | 周期 | 金叉得分 | 死叉扣分 |
    |------|----------|----------|
    | 1m  | +1分     | -1分     |
    | 5m  | +1分     | -1分     |
    | 1h  | +2分     | -2分     |
    """
    log("⚡ 开始快速投机策略分析 (V4)...")
    
    # 🔴 修复1: 先检查是否有持仓
    positions = get_positions()
    has_position = False
    if positions and positions.get("code") == "0":
        for p in positions.get("data", []):
            if float(p.get("pos", 0)) > 0:
                has_position = True
                log(f"  ⚠️ 已有持仓: {p.get('instId')}, 跳过快速策略")
                break
    
    if has_position:
        log("  ⚠️ 已有持仓，不执行快速策略")
        return None
    
    prices = get_prices()
    if not prices:
        return None
    
    # 获取余额
    balance = get_balance()
    available = 0
    if balance and balance.get("code") == "0":
        for row in balance["data"][0]["details"]:
            if row["ccy"] == "USDT":
                available = float(row.get("availBal", 0))
    
    if available < 5:
        log("  ⚠️ 余额不足")
        return None
    
    candidates = []
    
    for coin, data in prices.items():
        score = 0
        reasons = []
        
        # ====== 多周期MA分析 (V4新增1h) ======
        ma_data = get_multi_timeframe_ma(coin)
        
        # 1m 超短判断
        if ma_data and "1m" in ma_data and ma_data["1m"]:
            trend_1m = ma_data["1m"]["trend"]
            if trend_1m == "金叉":
                score += 1
                reasons.append("1m金叉")
            elif trend_1m == "死叉":
                score -= 1
                reasons.append("1m死叉")
        
        # 5m 短线判断
        if ma_data and "5m" in ma_data and ma_data["5m"]:
            trend_5m = ma_data["5m"]["trend"]
            if trend_5m == "金叉":
                score += 1
                reasons.append("5m金叉")
            elif trend_5m == "死叉":
                score -= 1
                reasons.append("5m死叉")
        
        # 1h 大趋势判断 (得分更高)
        if ma_data and "1h" in ma_data and ma_data["1h"]:
            trend_1h = ma_data["1h"]["trend"]
            if trend_1h == "金叉":
                score += 2
                reasons.append("1h金叉↑")
            elif trend_1h == "死叉":
                score -= 2
                reasons.append("1h死叉↓")
        
        # ====== 其他筛选条件 ======
        
        # 涨跌幅过滤 - 快速策略更宽松
        change = data["change"]
        if -3 <= change <= 3:  # 允许更大范围
            score += 1
            reasons.append(f"涨跌{change:+.1f}%")
        
        # 距离支撑位 - 放宽到5%
        support_data = get_support(coin)
        current_price = data["price"]
        if support_data:
            support = support_data["support"]
            distance_pct = (current_price - support) / current_price * 100
            
            if 0 <= distance_pct <= 5:
                score += 2
                reasons.append(f"距支撑{distance_pct:.1f}%")
        
        # RSI检查 - 不过于超买即可
        import statistics
        rsi_r = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1h&limit=30", timeout=5)
        if rsi_r.json().get("code") == "0":
            closes = [float(x[4]) for x in rsi_r.json()["data"][::-1]]
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, 15)]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, 15)]
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rsi = 100 - (100 / (1 + avg_gain/avg_loss)) if avg_loss > 0 else 50
            
            if rsi < 70:  # 不过于超买
                score += 1
                reasons.append(f"RSI={rsi:.0f}")
            else:
                score -= 2
                reasons.append(f"RSI超买{rsi:.0f}")
        
        # 得分门槛 >= 5分
        if score >= 5:
            candidates.append({
                "coin": coin,
                "price": current_price,
                "score": score,
                "reasons": reasons
            })
    
    if candidates:
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        log(f"  ⚡ 快速候选: {best['coin']} (得分:{best['score']})")
        for r in best['reasons']:
            log(f"     • {r}")
        return best
    
    log("  ⏳ 无快速信号")
    return None

def fast_strategy_trade(candidate, prices=None):
    """快速策略执行交易 - 仅通知模式"""
    coin = candidate["coin"]
    price = candidate["price"]
    inst_id = f"{coin}-USDT-SWAP"
    
    # 计算动态止盈止损
    if prices and coin in prices:
        tp_percent, sl_percent = calc_dynamic_tp_sl(coin, "buy", prices)
        tp_price = price * (1 + tp_percent)
        sl_price = price * (1 - sl_percent)
        
        log(f"  📢 快速策略发现信号: {coin}")
        log(f"     当前价格: ${price}")
        log(f"     得分: {candidate['score']}")
        log(f"     原因: {', '.join(candidate['reasons'])}")
        log(f"  📊 建议交易参数:")
        log(f"     开仓价: ${price}")
        log(f"     止盈价: ${tp_price:.2f} ({tp_percent*100:.1f}%)")
        log(f"     止损价: ${sl_price:.2f} ({sl_percent*100:.1f}%)")
    else:
        log(f"  📢 快速策略发现信号: {coin} @ ${price}")
        log(f"     得分: {candidate['score']}")
        log(f"     原因: {', '.join(candidate['reasons'])}")
    
    log(f"  ⚠️ 快速策略已改为通知模式，需要您确认后手动执行")
    log(f"  💡 如需自动执行，请将 FAST_STRATEGY_ENABLED 改为 True")
    
    # 不自动执行，只记录日志提醒用户
    return False  # 返回False表示未执行

# 快速策略开关
# True = 自动执行 (谨慎使用)
# False = 仅通知，不自动执行
FAST_STRATEGY_ENABLED = False  # 修改为False，仅通知模式！

FAST_STRATEGY_NOTIFY_COOLDOWN = 300  # 通知冷却时间(秒)，避免重复通知

def monitor_positions_and_alert():
    """监控当前持仓的止盈止损状态 (V4新增)"""
    
    # 舆情分析
    if HAS_SENTIMENT:
        try:
            global_s = get_global_sentiment()
            if global_s.get("status") == "ok":
                sentiment = global_s.get("sentiment", "中性")
                change = global_s.get("market_cap_change", 0)
                log(f"🌍 市场情绪: {sentiment} ({change:+.2f}%)")
                
                # 记录到日志
                if sentiment in ["极度乐观", "乐观"]:
                    log("   📈 市场情绪偏多")
                elif sentiment in ["极度悲观", "悲观"]:
                    log("   📉 市场情绪偏空")
        except Exception as e:
            log(f"   ⚠️ 舆情分析异常: {e}")
    
    log("🔔 监控持仓状态...")
    
    positions = get_positions()
    if not positions or positions.get("code") != "0":
        return None
    
    prices = get_prices()
    alerts = []
    
    for p in positions.get("data", []):
        if float(p.get("pos", 0)) <= 0:
            continue
        
        inst_id = p.get("instId", "")
        avg_price = float(p.get("avgPx", 0))
        pos = float(p.get("pos", 0))
        upl = float(p.get("upl", 0))
        side = p.get("posSide", "long")  # long or short
        
        # 提取币种
        coin = inst_id.replace("-USDT-SWAP", "")
        
        # 获取当前价格
        current_price = None
        if prices and coin in prices:
            current_price = prices[coin]["price"]
        
        if not current_price:
            continue
        
        # 计算盈亏比例
        if side == "long":
            pnl_pct = (current_price - avg_price) / avg_price * 100
        else:  # short
            pnl_pct = (avg_price - current_price) / avg_price * 100
        
        # 检查止盈 (5%) 和止损 (-3%)
        if pnl_pct >= 5:
            alerts.append(f"🚨 {inst_id} 达到止盈线! 盈亏: {pnl_pct:+.1f}% (${upl:.2f})")
        elif pnl_pct <= -3:
            alerts.append(f"🛑 {inst_id} 触发止损线! 盈亏: {pnl_pct:+.1f}% (${upl:.2f})")
        else:
            log(f"  📊 {inst_id}: 均价${avg_price} 现价${current_price} 盈亏{pnl_pct:+.1f}%")
    
    if alerts:
        for alert in alerts:
            log(alert)
    
    return alerts


def always_scan_opportunities():
    """V4: 始终扫描市场机会 (即使有持仓也继续分析)"""
    log("🔍 始终扫描市场机会...")
    
    prices = get_prices()
    if not prices:
        return None
    
    # 检查余额
    balance = get_balance()
    available = 0
    if balance and balance.get("code") == "0":
        for row in balance["data"][0]["details"]:
            if row["ccy"] == "USDT":
                available = float(row.get("availBal", 0))
    
    if available < 5:
        log("  ⚠️ 余额不足，跳过机会扫描")
        return None
    
    candidates = []
    
    for coin, data in prices.items():
        score = 0
        reasons = []
        
        try:
            # 获取1m K线
            r = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1m&limit=30", timeout=5)
            if r.json().get("code") != "0":
                continue
            
            closes_1m = [float(x[4]) for x in r.json()["data"][::-1]]
            current_price = closes_1m[-1]
            
            # 1m均线
            ma5_1m = sum(closes_1m[-5:]) / 5
            ma10_1m = sum(closes_1m[-10:]) / 10
            
            if ma5_1m > ma10_1m:
                score += 2
                reasons.append("1m金叉")
            
            # 5m趋势
            r5 = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=5m&limit=30", timeout=5)
            if r5.json().get("code") == "0":
                closes_5m = [float(x[4]) for x in r5.json()["data"][::-1]]
                ma5_5m = sum(closes_5m[-5:]) / 5
                ma20_5m = sum(closes_5m[-20:]) / 20
                
                if ma5_5m > ma20_5m:
                    score += 1
                    reasons.append("5m上涨")
            
            # 支撑位
            support_data = get_support(coin)
            if support_data:
                support = support_data["support"]
                distance_pct = (current_price - support) / current_price * 100
                
                if 0 <= distance_pct <= 5:
                    score += 2
                    reasons.append(f"支撑{distance_pct:.1f}%")
            
            # 涨跌幅 (快速策略更宽松)
            change = data["change"]
            if -3 <= change <= 3:
                score += 1
            
            if score >= 3:
                # 计算支撑位作为做多入场价
                support_data = get_support(coin)
                if support_data:
                    entry_price = support_data["support"]
                else:
                    entry_price = current_price
                
                candidates.append({
                    "coin": coin,
                    "score": score,
                    "reasons": reasons,
                    "price": current_price,
                    "entry_price": entry_price,
                    "change": change
                })
        
        except:
            continue
    
    # 按分数排序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    if candidates:
        log(f"  📈 发现 {len(candidates)} 个潜在机会:")
        for c in candidates[:3]:
            log(f"     {c['coin']}: 分数{c['score']} {c['reasons']}")
            # 记录机会 - 使用支撑位作为入场价
            reasons_str = str(c['reasons'])[:50]
            entry = c.get('entry_price', c['price'])
            record_opportunity(c['coin'], "long", entry, c['score'], reasons_str)
        return candidates[:3]
    
    return None
    
    return None


def detect_short_opportunities():
    """V4: 检测做空机会 (当市场超买时)"""
    log("🔍 检测做空机会...")
    
    prices = get_prices()
    if not prices:
        return None
    
    short_candidates = []
    
    for coin, data in prices.items():
        try:
            # 获取1h K线计算RSI
            r = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1h&limit=30", timeout=5)
            if r.json().get("code") != "0":
                continue
            
            closes = [float(x[4]) for x in r.json()["data"][::-1]]
            
            # RSI计算
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, 15)]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, 15)]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_loss = sum(losses) / 14 if losses else 0
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))
            
            # 获取当前价格
            current_price = data["price"]
            change = data["change"]
            
            # 做空条件: RSI > 70 (超买) + 涨幅 > 3%
            if rsi > 70 and change > 3:
                short_candidates.append({
                    "coin": coin,
                    "rsi": rsi,
                    "price": current_price,
                    "change": change
                })
                log(f"  📉 {coin}: RSI={rsi:.0f} 涨幅{change:+.1f}% (超买可做空)")
        
        except:
            continue
    
    return short_candidates if short_candidates else None



def analyze_short_opportunity_v4(coin, prices):
    """V4做空策略分析 - 多周期MA + 压力位 + RSI超买
    
    做空得分配置:
    | 周期 | 死叉得分 | 金叉扣分 |
    |------|----------|----------|
    | 1m   | +1分     | -1分     |
    | 5m   | +1分     | -1分     |
    | 1h   | +2分     | -2分     |
    
    其他条件:
    - 距离压力位 ≤5%
    - RSI > 70 (超买)
    - 涨幅 > 0%
    - 得分 ≥5分 执行做空
    """
    try:
        import statistics
        
        # 获取多周期数据
        ma_data = get_multi_timeframe_ma(coin)
        
        # 获取1h K线
        r = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1H&limit=50", timeout=10)
        if r.json().get("code") != "0":
            return None
        
        data = r.json()["data"]
        closes = [float(x[4]) for x in data[::-1]]
        
        if len(closes) < 20:
            return None
        
        current_price = prices.get(coin, {}).get("price", closes[-1])
        
        # 计算RSI
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, 15)]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, 15)]
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # 计算压力位 (布林上轨 + MA20)
        ma20 = sum(closes[-20:]) / 20
        std = statistics.stdev(closes[-20:])
        bb_upper = ma20 + 2 * std
        resistance = max(ma20, bb_upper)
        
        # 距离压力位
        distance_to_resistance = (resistance - current_price) / current_price * 100
        
        # 涨跌幅
        change = prices.get(coin, {}).get("change", 0)
        
        # V4做空评分
        score = 0
        reasons = []
        
        # 多周期MA分析 (死叉得分)
        if ma_data:
            # 1m死叉
            if "1m" in ma_data and ma_data["1m"]:
                if ma_data["1m"]["trend"] == "死叉":
                    score += 1
                    reasons.append("1m死叉")
                elif ma_data["1m"]["trend"] == "金叉":
                    score -= 1
                    reasons.append("1m金叉")
            
            # 5m死叉
            if "5m" in ma_data and ma_data["5m"]:
                if ma_data["5m"]["trend"] == "死叉":
                    score += 1
                    reasons.append("5m死叉")
                elif ma_data["5m"]["trend"] == "金叉":
                    score -= 1
                    reasons.append("5m金叉")
            
            # 1h死叉 (权重更高)
            if "1h" in ma_data and ma_data["1h"]:
                if ma_data["1h"]["trend"] == "死叉":
                    score += 2
                    reasons.append("1h死叉↓")
                elif ma_data["1h"]["trend"] == "金叉":
                    score -= 2
                    reasons.append("1h金叉↑")
        
        # 距离压力位 ≤5%
        if 0 <= distance_to_resistance <= 5:
            score += 2
            reasons.append(f"距压力{distance_to_resistance:.1f}%")
        
        # RSI > 70 超买
        if rsi > 70:
            score += 2
            reasons.append(f"RSI超买{int(rsi)}")
        
        # 涨幅 > 0% (上涨后做空)
        if change > 0:
            score += 1
            reasons.append(f"涨{change:.1f}%")
        
        # 得分门槛
        if score >= 5:
            return {
                "coin": coin,
                "price": current_price,
                "score": score,
                "rsi": rsi,
                "resistance": resistance,
                "distance": distance_to_resistance,
                "change": change,
                "reasons": reasons,
                "ma": ma_data
            }
        
    except Exception as e:
        pass
    
    return None


def detect_short_opportunities_v4():
    """V4: 检测做空机会 (多周期MA + 压力位 + RSI超买)"""
    log("🔍 检测做空机会 (V4多周期分析)...")
    
    prices = get_prices()
    if not prices:
        return None
    
    short_candidates = []
    
    for coin, data in prices.items():
        short = analyze_short_opportunity_v4(coin, prices)
        if short and short["score"] >= 5:
            short_candidates.append(short)
            
            # 计算止盈止损点位
            current_price = short["price"]
            resistance = short.get("resistance", current_price * 1.02)
            support = short.get("resistance", current_price * 0.98) * 0.95  # 预估支撑
            
            # 做空止盈止损计算
            tp_price = current_price * 0.97  # 3%止盈（价格下跌）
            sl_price = current_price * 1.02  # 2%止损（价格上涨）
            
            ma_str = "/".join([f"{k}:{v['trend']}" for k,v in short.get("ma", {}).items() if v]) if short.get("ma") else "无"
            
            log(f"  📉 {coin}: 得分={short['score']} RSI={short['rsi']:.0f} 距压力={short['distance']:.1f}%")
            log(f"     原因: {', '.join(short['reasons'])}")
            log(f"     MA: {ma_str}")
            log(f"     💰 做空点位: ${current_price:.4f}")
            log(f"     🎯 止盈: ${tp_price:.4f} (-3.0%)")
            log(f"     🛡️ 止损: ${sl_price:.4f} (+2.0%)")
    
    return short_candidates if short_candidates else None


def check_and_trade():
    """检查并自动交易 (V4优化版)"""
    log("👁️ 检查持仓状态...")
    
    # 获取持仓
    positions = get_positions()
    
    has_position = False
    position_details = []
    
    if positions and positions.get("code") == "0":
        for p in positions.get("data", []):
            pos = float(p.get("pos", 0))
            if pos != 0:  # 做多或做空只要不为0就是有持仓
                has_position = True
                inst_id = p.get("instId", "")
                avg_price = float(p.get("avgPx", 0))
                upl = float(p.get("upl", 0))
                side = "做空" if pos < 0 else "做多"
                position_details.append(f"{inst_id}: {side} ${avg_price} x{abs(pos)} (盈亏:${upl:.2f})")
    
    if has_position:
        log("  ✅ 持有仓位:")
        for detail in position_details:
            log(f"     {detail}")
        
        # V4优化: 即使有持仓也继续监控
        log("="*40)
        
        # 1. 监控止盈止损
        alerts = monitor_positions_and_alert()
        
        # 2. 持仓币种盘面预测分析
        log("="*40)
        log("🔮 持仓币种预测分析...")
        try:
            from market_forecast_v2 import predict_enhanced as pred_v2
            for p in positions.get("data", []):
                pos = float(p.get("pos", 0))
                if pos != 0:
                    coin = p.get("instId", "").replace("-USDT-SWAP", "")
                    if coin and pred_v2:
                        result = pred_v2(coin, "1H")
                        if result:
                            emoji = "📈" if result["prediction"] == "涨" else "📉" if result["prediction"] == "跌" else "➡️"
                            log(f"   {coin}: {emoji} {result['prediction']} ({result['confidence']}%)")
                            log(f"      因子: {', '.join(result['factors'][:3])}")
        except Exception as e:
            log(f"   预测分析异常: {e}")
        
        # 3. 扫描其他币种机会
        log("="*40)
        opportunities = always_scan_opportunities()
        
        # 4. 检测做空机会 (V4多周期)
        log("="*40)
        short_opps = detect_short_opportunities_v4()
        
        return False
    else:
        log("  ⚠️ 无持仓!")
        
        if AUTO_TRADE:
            # 策略1: V2严格策略 (优先)
            log("="*40)
            log("📋 运行V2严格策略...")
            v2_result = analyze_and_trade()
            
            # 策略2: V3多维确认策略 (发现强信号自动通知)
            if HAS_V3_STRATEGY:
                log("="*40)
                log("📋 运行V3多维确认策略...")
                try:
                    v3_signals = v3_scan_all()
                    if v3_signals:
                        for sig in v3_signals[:3]:
                            emoji = "🟢做多" if sig.get("direction") == "long" else "🔴做空"
                            period_name = sig.get("period_name", "")
                            log(f"   {emoji} {sig.get('coin')}: {sig.get('direction')} | {sig.get('score')}分 | {period_name}")
                        
                        # 发现强信号(≥5分)自动通知
                        strong_signals = [s for s in v3_signals if s.get("score", 0) >= 5]
                        if strong_signals:
                            # 去重检查 - 如果信号与上次相同则不发送
                            import json
                            import os
                            signal_file = "/Users/shirenyushangren/.openclaw/workspace/.last_signals.json"
                            
                            current_signals = []
                            for s in strong_signals[:3]:
                                current_signals.append({
                                    "coin": s.get("coin"),
                                    "direction": s.get("direction"),
                                    "score": s.get("score")
                                })
                            
                            # 读取上次信号
                            last_signals = []
                            if os.path.exists(signal_file):
                                try:
                                    with open(signal_file, "r") as f:
                                        last_signals = json.load(f)
                                except:
                                    last_signals = []
                            
                            # 比较是否相同
                            is_same = (current_signals == last_signals)
                            
                            # 更新信号记录
                            with open(signal_file, "w") as f:
                                json.dump(current_signals, f)
                            
                            if is_same:
                                log("   ⚠️ 信号与上次相同，跳过通知")
                            else:
                                import subprocess
                            
                            # 发送Top3信号的完整详情
                            for sig in strong_signals[:3]:
                                coin = sig.get("coin", "")
                                direction = sig.get("direction", "")
                                score = sig.get("score", 0)
                                period_name = sig.get("period_name", "")
                                
                                # 获取支撑压力和止盈止损
                                url = f"https://www.okx.com/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1H&limit=50"
                                timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                                sig_headers = {
                                    "OK-ACCESS-KEY": API_KEY,
                                    "OK-ACCESS-TIMESTAMP": timestamp,
                                    "OK-ACCESS-SIGN": generate_signature(timestamp, "GET", f"/api/v5/market/candles?instId={coin}-USDT-SWAP&bar=1H&limit=50", ""),
                                    "OK-ACCESS-PASSPHRASE": PASSPHRASE,
                                    "Content-Type": "application/json"
                                }
                                resp = requests.get(url, headers=sig_headers, timeout=10)
                                
                                if resp.status_code == 200:
                                    data = resp.json()
                                    if data.get("code") == "0" and data["data"]:
                                        candles = data["data"]
                                        closes = [float(c[4]) for c in candles]
                                        highs = [float(c[2]) for c in candles]
                                        lows = [float(c[3]) for c in candles]
                                        
                                        current = closes[0]
                                        support = min(lows[:10])
                                        resistance = max(highs[:10])
                                        
                                        # ATR计算
                                        tr_values = []
                                        for i in range(1, min(14, len(closes))):
                                            tr = max(highs[i-1] - lows[i-1], abs(highs[i-1] - closes[i]), abs(lows[i-1] - closes[i]))
                                            tr_values.append(tr)
                                        atr = sum(tr_values) / len(tr_values) if tr_values else current * 0.01
                                        
                                        if direction == "long":
                                            entry = support
                                            tp = current + atr * 2
                                            sl = support - atr
                                        else:
                                            entry = resistance
                                            tp = current - atr * 2
                                            sl = resistance + atr
                                        
                                        direction_cn = "做多" if direction == "long" else "做空"
                                        emoji = "🟢" if direction == "long" else "🔴"
                                        
                                        # 根据价格选择格式化
                                        if current < 1:
                                            fmt = ".6f"
                                        elif current < 10:
                                            fmt = ".4f"
                                        elif current < 100:
                                            fmt = ".2f"
                                        else:
                                            fmt = ".2f"
                                        
                                        msg = f"""🐭 {emoji} {coin} {direction_cn} {score}分

💵 入场: ${entry:{fmt}}
🎯 止盈: ${tp:{fmt}} ({(tp-current)/current*100:+.1f}%)
🛡️ 止损: ${sl:{fmt}} ({(current-sl)/current*100:+.1f}%)

📊 当前: ${current:{fmt}} | 周期: {period_name}"""
                                        
                                        subprocess.run(
                                            ["openclaw", "message", "send", "--target", "ou_d42a845b7f627665f57fdc2f410322e8", "--message", msg],
                                            capture_output=True, text=True
                                        )
                            
                            log("   ✅ 已推送强信号完整通知")
                except Exception as e:
                    log(f"   ⚠️ V3策略异常: {e}")
            
            # 策略3: 快速投机策略
            log("="*40)
            log("📋 运行快速投机策略...")
            
            # 获取prices用于计算止盈止损
            prices = get_prices()
            
            fast_candidate = fast_strategy_analyze()
            if fast_candidate:
                # 使用fast_strategy_trade显示完整信息（含止盈止损）
                fast_strategy_trade(fast_candidate, prices)
            
            # 也检测做空机会 (V4)
            log("="*40)
            detect_short_opportunities_v4()
        
        return True

def run():
    """主流程"""
    log("="*50)
    log("🐭 币圈三兄弟 自动巡检开始 V3 (全自动)")
    
    # 1. 行情
    log("📊 获取行情...")
    prices = get_prices()
    if prices:
        changes = [f"{k}: {v['change']:+.1f}%" for k,v in prices.items()]
        log(f"  行情: {', '.join(changes)}")
    
    # 2. 余额
    log("💰 检查余额...")
    balance = get_balance()
    if balance and balance.get("code") == "0":
        total = float(balance["data"][0].get("totalEq", 0))
        log(f"  总资产: ${total:.2f}")
    
    # 3. 盘面预测 (可选)
    try:
        from market_forecast import predict_multi_timeframe
        log("🔮 盘面预测...")
        # 只预测BTC作为参考
        pred = predict_multi_timeframe("BTC")
        if pred:
            for period, p in pred.items():
                if period == "支撑压力":
                    sr = p
                    log(f"  支撑: ${sr['support']:.0f} | 压力: ${sr['resistance']:.0f}")
                elif period == "短期预测":
                    log(f"  短期: {p['direction']} ({p['probability']}%)")
    except Exception as e:
        log(f"  预测模块异常: {e}")
    
    # 4. 检查并自动交易
    check_and_trade()
    
    # 4. 处理通知队列
    process_notify_queue()
    
    log("🐭 巡检完成")
    log("")

if __name__ == "__main__":
    import time
    import os
    
    # 时间间隔控制文件
    STATE_FILE = "/Users/shirenyushangren/.openclaw/workspace/.monitor_state.json"
    
    def load_state():
        """加载上次执行状态"""
        try:
            import json
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except:
            pass
        return {"last_run": 0, "last_action": "none"}
    
    def save_state(state):
        """保存状态"""
        try:
            import json
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
        except:
            pass
    
    def get_interval(has_position):
        """根据是否有仓位返回间隔时间(秒)"""
        # 特殊时期(3-4点)缩短间隔
        current_hour = datetime.now().hour
        if current_hour == 3:  # 3点特殊监控
            return 60 if has_position else 30  # 有仓位1分钟，无仓位30秒
        return 300 if has_position else 60  # 有仓位5分钟，无仓位1分钟
    
    # 加载状态
    state = load_state()
    last_run = state.get("last_run", 0)
    last_action = state.get("last_action", "none")
    current_time = time.time()
    
    # 获取当前持仓状态
    positions = get_positions()
    has_position = False
    if positions and positions.get("code") == "0":
        for p in positions.get("data", []):
            if float(p.get("pos", 0)) != 0:  # 做多或做空
                has_position = True
                break
    
    # 计算需要等待的时间
    interval = get_interval(has_position)
    elapsed = current_time - last_run
    
    if elapsed < interval:
        remaining = int(interval - elapsed)
        if has_position:
            log(f"⏳ 有仓位，{remaining}秒后再次执行 (间隔{interval}秒)")
        else:
            log(f"⏳ 无仓位，{remaining}秒后再次执行 (间隔{interval}秒)")
        exit(0)
    
    # 执行巡检
    run()
    
    # 保存状态
    save_state({
        "last_run": time.time(),
        "last_action": "巡检"
    })

# ========== 机会记录功能 ==========
OPPORTUNITIES_FILE = "/Users/shirenyushangren/.openclaw/workspace/.opportunities.json"

#def record_opportunity
def record_opportunity(coin, direction, entry_price, score=0, reasons=""):
    """记录交易机会"""
    try:
        import json
        opportunities = []
        if os.path.exists(OPPORTUNITIES_FILE):
            with open(OPPORTUNITIES_FILE, "r") as f:
                opportunities = json.load(f)
        
        # 计算止盈止损
        if direction == "long":
            tp_price = entry_price * 1.03
            sl_price = entry_price * 0.98
        else:
            tp_price = entry_price * 0.97
            sl_price = entry_price * 1.02
        
        opportunity = {
            "coin": coin,
            "direction": direction,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entry": entry_price,
            "tp": tp_price,
            "sl": sl_price,
            "score": score,
            "reasons": reasons,
            "status": "watching"
        }
        
        opportunities.append(opportunity)
        
        with open(OPPORTUNITIES_FILE, "w") as f:
            json.dump(opportunities, f, ensure_ascii=False)
        
        # 发送飞书通知
        emoji = "🟢做多" if direction == "long" else "🔴做空"
        tp_pct = (tp_price - entry_price) / entry_price * 100
        sl_pct = (sl_price - entry_price) / entry_price * 100
        
        direction_text = "做多" if direction == "long" else "做空"
        
        # 根据价格选择格式化
        if entry_price < 1:
            fmt = ".6f"
        elif entry_price < 10:
            fmt = ".4f"
        elif entry_price < 100:
            fmt = ".2f"
        else:
            fmt = ".2f"
        
        notify_msg = f"""🐭 {emoji} {coin} {direction_text}机会

📌 币种: {coin}
📌 方向: {direction_text}
⏰ 时间: {datetime.now().strftime('%H:%M')}

💵 入场: ${entry_price:{fmt}}
🎯 止盈: ${tp_price:{fmt}} ({tp_pct:+.1f}%)
🛡️ 止损: ${sl_price:{fmt}} ({sl_pct:+.1f}%)

📊 得分: {score}分
📝 原因: {reasons[:50]}"""
        
        queue_notify("交易机会", notify_msg)
        
        log(f"  ✅ 机会已记录: {coin} {direction}")
        
    except Exception as e:
        log(f"  ⚠️ 记录机会失败: {e}")

def get_opportunities():
    """获取记录的机会"""
    try:
        if os.path.exists(OPPORTUNITIES_FILE):
            with open(OPPORTUNITIES_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return []


# ========== 历史交易记录模块 ==========
def get_trade_history(days: int = 3, limit: int = 50) -> Dict:
    """获取历史交易记录"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-SIGN": generate_signature(timestamp, "GET", f"/api/v5/trade/fills?instType=SWAP&limit={limit}", ""),
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    
    url = f"https://www.okx.com/api/v5/trade/fills?instType=SWAP&limit={limit}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("code") == "0" and data["data"]:
            fills = data["data"]
            
            # 按日期分组
            by_date = {}
            for f in fills:
                ts = f.get("ts", "")
                if ts:
                    dt = datetime.fromtimestamp(int(ts)/1000)
                    
                    # 过滤天数
                    if (datetime.now() - dt).days > days:
                        continue
                    
                    date = dt.strftime("%Y-%m-%d")
                    
                    if date not in by_date:
                        by_date[date] = []
                    
                    coin = f.get("instId", "").replace("-USDT-SWAP", "")
                    side = "买入" if f.get("side") == "buy" else "卖出"
                    px = f.get("fillPx", "")
                    
                    by_date[date].append({
                        "time": dt.strftime("%H:%M"),
                        "coin": coin,
                        "side": side,
                        "price": px
                    })
            
            return {"status": "ok", "trades": by_date}
        
        return {"status": "error", "msg": "无数据"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


def format_trade_history(days: int = 3) -> str:
    """格式化历史交易记录为字符串"""
    history = get_trade_history(days)
    
    if history.get("status") != "ok":
        return "⚠️ 获取历史记录失败"
    
    trades = history.get("trades", {})
    
    if not trades:
        return "⚠️ 无历史交易记录"
    
    lines = []
    for date in sorted(trades.keys(), reverse=True):
        lines.append(f"\n📅 {date}")
        for t in trades[date]:
            emoji = "📈" if t["side"] == "买入" else "📉"
            lines.append(f"   {emoji} {t['time']} {t['side']} {t['coin']} @ ${t['price']}")
    
    return "\n".join(lines)
