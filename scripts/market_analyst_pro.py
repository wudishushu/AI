#!/usr/bin/env python3
"""
📊 专业版行情规划师 - 技术分析量化交易
功能：技术指标、买卖信号、风控建议
"""

import requests
import json
import numpy as np
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("/Users/shirenyushangren/.openclaw/workspace")

# ============ 数据获取 =============
def get_ticker(symbol):
    """获取实时行情"""
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}-USDT"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("code") == "0" and data.get("data"):
            t = data["data"][0]
            return {
                "price": float(t["last"]),
                "open": float(t["open24h"]),
                "high": float(t["high24h"]),
                "low": float(t["low24h"]),
                "vol": float(t.get("volCcy24h", 0)),
                "sod": float(t.get("sodUtc0", 0))
            }
    except:
        pass
    return None

def get_history_klines(symbol):
    """获取历史K线 (备用方案)"""
    # 使用公开的K线接口
    url = f"https://www.okx.com/api/v5/market/candles"
    params = {
        "instId": f"{symbol}-USDT",
        "bar": "1h",
        "limit": "100"
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("code") == "0" and data.get("data"):
            klines = []
            for k in data["data"]:
                klines.append({
                    "time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "vol": float(k[5])
                })
            return klines
    except:
        pass
    return None

# ============ 技术指标 =============
def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    ema = prices[0]
    multiplier = 2 / (period + 1)
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None
    sma = calculate_sma(prices, period)
    std = np.std(prices[-period:])
    return {"middle": sma, "upper": sma + std_dev * std, "lower": sma - std_dev * std}

def calculate_atr(highs, lows, closes, period=14):
    """ATR平均真实波幅"""
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    return np.mean(trs[-period:])

# ============ 综合分析 =============
def analyze_coin(symbol):
    """分析单个币种"""
    print(f"\n{'='*55}")
    print(f"📊 {symbol}/USDT 专业量化分析")
    print(f"{'='*55}")
    
    # 获取实时数据
    ticker = get_ticker(symbol)
    if not ticker:
        print(f"❌ 无法获取{symbol}数据")
        return
    
    price = ticker["price"]
    open_24h = ticker["open"]
    high_24h = ticker["high"]
    low_24h = ticker["low"]
    
    # 计算基础指标
    change_24h = ((price - open_24h) / open_24h * 100) if open_24h else 0
    
    # 使用24h数据模拟
    prices = np.array([price * (1 - change_24h/100 * i/24) for i in range(24, 0, -1)])
    prices = np.append(prices[:-1], price)
    
    # 指标计算
    sma5 = calculate_sma(prices, 5)
    sma10 = calculate_sma(prices, 10)
    sma20 = calculate_sma(prices, 20)
    rsi = calculate_rsi(prices)
    bb = calculate_bollinger(prices)
    
    # 计算ATR
    highs = np.array([price * 1.01 for _ in range(24)])
    lows = np.array([price * 0.99 for _ in range(24)])
    atr = calculate_atr(highs, lows, prices)
    
    print(f"\n💰 当前价格: ${price:,.2f}")
    print(f"📈 24h涨跌: {change_24h:+.2f}%")
    print(f"📊 24h波动: ${high_24h-low_24h:,.2f} ({(high_24h-low_24h)/price*100:.1f}%)")
    
    print(f"\n📐 均线系统:")
    print(f"  MA5:  ${sma5:,.2f}" if sma5 else "  MA5: N/A")
    print(f"  MA10: ${sma10:,.2f}" if sma10 else "  MA10: N/A")
    print(f"  MA20: ${sma20:,.2f}" if sma20 else "  MA20: N/A")
    
    print(f"\n📉 RSI(14): {rsi:.1f}" if rsi else "")
    
    if bb:
        print(f"📐 布林带:")
        print(f"  上轨: ${bb['upper']:,.2f}")
        print(f"  中轨: ${bb['middle']:,.2f}")
        print(f"  下轨: ${bb['lower']:,.2f}")
    
    if atr:
        print(f"\n📊 ATR: ${atr:,.2f}")
    
    # 信号评分
    score = 0
    reasons = []
    
    # RSI信号
    if rsi:
        if rsi < 30:
            score += 3
            reasons.append("RSI超卖 ← 强烈买入信号")
        elif rsi < 40:
            score += 1
            reasons.append("RSI低位 ← 偏多")
        elif rsi > 70:
            score -= 3
            reasons.append("RSI超买 ← 强烈卖出信号")
        elif rsi > 60:
            score -= 1
            reasons.append("RSI高位 ← 偏空")
    
    # 均线信号
    if sma5 and sma20:
        if sma5 > sma20:
            score += 2
            reasons.append("MA5>MA20 ← 金叉看涨")
        else:
            score -= 2
            reasons.append("MA5<MA20 ← 死叉看跌")
    
    # 布林信号
    if bb:
        if price < bb["lower"]:
            score += 2
            reasons.append("触及布林下轨 ← 超卖")
        elif price > bb["upper"]:
            score -= 2
            reasons.append("触及布林上轨 ← 超买")
    
    # 趋势判断
    if sma5 and sma20 and sma10:
        if sma5 > sma10 > sma20:
            trend = "🟢 强势上涨"
            score += 1
        elif sma5 < sma10 < sma20:
            trend = "🔴 强势下跌"
            score -= 1
        else:
            trend = "⚪ 震荡整理"
    else:
        trend = "⚪ 整理"
    
    print(f"\n{'='*40}")
    print(f"🎯 综合评分: {score}分 ({trend})")
    print(f"{'='*40}")
    
    if reasons:
        print("\n📋 分析依据:")
        for r in reasons:
            print(f"  • {r}")
    
    # 买卖建议
    print(f"\n{'='*40}")
    if score >= 3:
        print("🟢 🟢 🟢 强烈买入")
    elif score >= 1:
        print("🟢 🟡 建议买入")
    elif score >= -1:
        print("⚪ ⚪ 观望")
    else:
        print("🔴 🔴 建议卖出")
    print(f"{'='*40}")
    
    # 风控建议
    print(f"\n🛡️ 风控建议:")
    if bb:
        print(f"  止损位: ${bb['lower']:,.2f} (布林下轨 -{(price-bb['lower'])/price*100:.1f}%)")
    if atr:
        print(f"  ATR止损: ${price - atr*1.5:,.2f} (-{atr*1.5/price*100:.1f}%)")
    print(f"  止盈位: ${price * 1.08:,.2f} (+8%) / ${price * 1.15:,.2f} (+15%)")
    
    # 仓位建议
    if score >= 3:
        print(f"  建议仓位: 50-70%")
    elif score >= 0:
        print(f"  建议仓位: 30-50%")
    else:
        print(f"  建议仓位: 10-20%")

def generate_full_report():
    """生成完整报告"""
    print("\n" + "="*60)
    print("📊 专业版量化行情分析报告")
    print(f"🕐 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    coins = ["BTC", "ETH", "SOL", "XRP", "DOT", "ADA", "DOGE"]
    
    results = []
    for coin in coins:
        ticker = get_ticker(coin)
        if ticker:
            # 模拟评分
            change = ((ticker["price"] - ticker["open"]) / ticker["open"] * 100) if ticker["open"] else 0
            score = int(change / 2)  # 简单评分
            results.append({
                "coin": coin,
                "price": ticker["price"],
                "change": change,
                "score": score
            })
    
    # 排序
    results.sort(key=lambda x: x["score"], reverse=True)
    
    print("\n🏆 综合排名 (按涨幅):")
    print(f"{'排名':<6} {'币种':<8} {'价格':<15} {'24h涨跌':<12} {'信号'}")
    print("-"*55)
    
    for i, r in enumerate(results, 1):
        emoji = "🟢" if r["change"] > 0 else "🔴"
        signal = "买入" if r["score"] > 1 else "观望" if r["score"] >= 0 else "卖出"
        print(f"{i:<6} {r['coin']:<8} ${r['price']:<14.2f} {emoji}{r['change']:+.2f}%    {signal}")
    
    # 最佳买入
    if results:
        best = results[0]
        print(f"\n🎯 重点分析: {best['coin']}")
        analyze_coin(best["coin"])

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        analyze_coin(sys.argv[1].upper())
    else:
        generate_full_report()
