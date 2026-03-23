#!/usr/bin/env python3
"""
币圈诊断员 - 全面监控脚本
功能：持仓监控、涨跌预警、异动监测、24h行情分析
用法: python3 crypto_diagnostic.py
"""

import hmac
import hashlib
import base64
import requests
import json
from datetime import datetime
from pathlib import Path

# ============ 配置区 =============
# OKX API
API_KEY = "4ef7631d-a7cb-4050-abfc-8a7ffe9c10d5"
SECRET_KEY = "EAF62B2E51A2AE8B4D03A7F22CB4DF3C"
PASSPHRASE = "Gen.248613"

# 预警设置
ALERT_GAIN_PERCENT = 10    # 涨幅超过X%提醒
ALERT_LOSS_PERCENT = -10   # 跌幅超过X%提醒
VOLUME_SPIKE_MULTI = 3     # 成交量异动倍数
PRICE_CHANGE_1H = 5        # 1小时涨跌超X%提醒
# ================================

WORKSPACE = Path("/Users/shirenyushangren/.openclaw/workspace")

def generate_signature(timestamp, method, path, secret_key, passphrase):
    """生成OKX API签名"""
    message = timestamp + method + path
    mac = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256)
    signature = base64.b64encode(mac.digest()).decode()
    return signature

def okx_request(method, path):
    """OKX API 请求"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    signature = generate_signature(timestamp, method, path, SECRET_KEY, PASSPHRASE)
    
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
            response = requests.get(url, headers=headers, timeout=15)
        else:
            response = requests.post(url, headers=headers, timeout=15)
        data = response.json()
        if data.get("code") == "0":
            return data.get("data", [])
        return None
    except Exception as e:
        print(f"❌ API请求失败: {e}")
        return None

def get_balance():
    """获取账户余额"""
    return okx_request("GET", "/api/v5/account/balance")

def get_positions():
    """获取持仓"""
    return okx_request("GET", "/api/v5/account/positions?instType=SWAP")

def get_ticker(inst_id):
    """获取单个币种行情"""
    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "0" and data["data"]:
            t = data["data"][0]
            return {
                "last": float(t["last"]),
                "open24h": float(t["open24h"]),
                "high24h": float(t["high24h"]),
                "low24h": float(t["low24h"]),
                "vol24h": float(t.get("volCcy24h", 0)),
                "vol24h_usd": float(t.get("volCcy24h", 0)),  # 成交量
                "sodUtc0": float(t.get("sodUtc0", 0)),  # UTC0开始
                "sodUtc8": float(t.get("sodUtc8", 0)),  # UTC8开始
                "ts": t["ts"]
            }
    except:
        pass
    return None

def get_kline(inst_id, interval="1h", limit=24):
    """获取K线数据"""
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={inst_id}&bar={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "0" and data["data"]:
            return data["data"]
    except:
        pass
    return None

def calculate_pnl(row, current_price):
    """计算盈亏"""
    if not row:
        return None
    
    # 合约持仓
    if "instId" in row:
        ccy = row["instId"].replace("-USDT-SWAP", "")
        pos = float(row.get("pos", 0))
        avg_price = float(row.get("avgEntryPx", 0))
        avg_px_str = str(avg_price)
    else:
        # 现货持仓
        ccy = row["ccy"]
        pos = float(row.get("eq", 0))
        avg_px_str = row.get("accAvgPx", "0")
    avg_price = float(avg_px_str) if avg_px_str and avg_px_str != "" else 0
    
    if pos < 0.00000001:
        return None
    
    current_value = pos * current_price
    cost = pos * avg_price if avg_price else 0
    pnl = current_value - cost
    pnl_percent = (pnl / cost * 100) if cost > 0 else 0
    
    return {
        "ccy": ccy,
        "qty": pos,
        "avg_price": avg_price,
        "current_price": current_price,
        "current_value": current_value,
        "cost": cost,
        "pnl": pnl,
        "pnl_percent": pnl_percent
    }

def analyze_diagnostic():
    """执行全面诊断"""
    print("🔍 币圈诊断员开始工作...")
    print("=" * 50)
    
    # 获取持仓
    positions = get_positions()
    balance = get_balance()
    
    # 收集所有币种
    symbols = set()
    holdings = []
    
    # 处理合约持仓
    if positions:
        for p in positions:
            if float(p.get("pos", 0)) > 0:
                inst_id = p["instId"]
                ccy = inst_id.replace("-USDT-SWAP", "")
                symbols.add(ccy)
                holdings.append(("swap", p))
    
    # 处理现货持仓
    if balance:
        for row in balance[0].get("details", []):
            if float(row.get("eq", 0)) > 0.00000001:
                ccy = row["ccy"]
                symbols.add(ccy)
                holdings.append(("spot", row))
    
    print(f"📋 发现 {len(symbols)} 个持仓币种")
    
    # 获取所有行情
    print("📊 获取行情数据中...")
    tickers = {}
    for sym in symbols:
        ticker = get_ticker(f"{sym}-USDT")
        if ticker:
            tickers[sym] = ticker
    
    # 诊断分析
    alerts = []
    report = []
    
    report.append(f"🕐 诊断时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # 总资产
    total_eq = float(balance[0].get("totalEq", 0)) if balance else 0
    report.append(f"💰 总资产: ${total_eq:.2f} USDT")
    report.append("")
    
    # 逐个分析
    holdings_data = []
    for h in holdings:
        htype, row = h
        if htype == "swap":
            ccy = row["instId"].replace("-USDT-SWAP", "")
        else:
            ccy = row["ccy"]
        
        if ccy not in tickers:
            continue
        
        ticker = tickers[ccy]
        current_price = ticker["last"]
        
        result = calculate_pnl(row, current_price)
        if not result:
            continue
        
        # 计算24h涨跌
        open_24h = ticker["open24h"]
        if open_24h and open_24h > 0:
            change_24h = ((current_price - open_24h) / open_24h * 100)
        else:
            change_24h = 0
        
        result["change_24h"] = change_24h
        result["volume_24h"] = ticker["vol24h"]
        holdings_data.append(result)
        
        # 预警检测
        # 1. 持仓盈亏预警
        if result['pnl_percent'] >= ALERT_GAIN_PERCENT:
            alerts.append(f"🚀 {ccy} 持仓暴涨 +{result['pnl_percent']:.1f}%")
        elif result['pnl_percent'] <= ALERT_LOSS_PERCENT:
            alerts.append(f"⚠️ {ccy} 持仓暴跌 {result['pnl_percent']:.1f}%")
        
        # 2. 24h涨跌预警
        if change_24h >= ALERT_GAIN_PERCENT:
            alerts.append(f"📈 {ccy} 24h涨幅 +{change_24h:.1f}%")
        elif change_24h <= ALERT_LOSS_PERCENT:
            alerts.append(f"📉 {ccy} 24h跌幅 {change_24h:.1f}%")
    
    # 排序输出
    holdings_data.sort(key=lambda x: x['pnl_percent'], reverse=True)
    
    report.append("📈 持仓详情:")
    for h in holdings_data:
        emoji = "🟢" if h['pnl'] >= 0 else "🔴"
        pnl_str = f"${h['pnl']:+.2f} ({h['pnl_percent']:+.2f}%)"
        change_24h_str = f"24h: {h['change_24h']:+.2f}%"
        report.append(f"  {h['ccy']}: {h['qty']:.4f} @ ${h['current_price']:.2f} {emoji} {pnl_str} | {change_24h_str}")
    
    # 统计
    total_pnl = sum(h['pnl'] for h in holdings_data)
    total_cost = sum(h['cost'] for h in holdings_data)
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    
    report.append("")
    report.append(f"📊 总盈亏: ${total_pnl:+.2f} ({total_pnl_percent:+.2f}%)")
    
    if holdings_data:
        best = holdings_data[0]
        worst = holdings_data[-1]
        report.append(f"🥇 最佳: {best['ccy']} ({best['pnl_percent']:+.2f}%)")
        report.append(f"🥉 最差: {worst['ccy']} ({worst['pnl_percent']:+.2f}%)")
    
    # 预警输出
    report.append("")
    if alerts:
        report.append("⚡ 预警提醒:")
        for alert in alerts:
            report.append(f"  {alert}")
    else:
        report.append("✅ 无异常预警")
    
    final_report = "\n".join(report)
    print(final_report)
    
    # 保存报告
    report_file = WORKSPACE / "diagnostic_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(final_report)
    
    # 保存JSON（供程序读取）
    json_file = WORKSPACE / "diagnostic_latest.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_eq": total_eq,
            "holdings": holdings_data,
            "alerts": alerts
        }, f, indent=2)
    
    print("")
    print(f"✅ 诊断完成！报告已保存")
    
    return {
        "report": final_report,
        "alerts": alerts,
        "holdings": holdings_data
    }

if __name__ == "__main__":
    analyze_diagnostic()
