#!/usr/bin/env python3
"""
币圈操作员 - 交易执行脚本
功能：市价买入/卖出、限价下单、仓位管理
⚠️ 谨慎使用，需确认API权限已开启交易功能
"""

import hmac
import hashlib
import base64
import requests
import json
import math
from datetime import datetime
from pathlib import Path

# ============ 配置区 =============
API_KEY = "4ef7631d-a7cb-4050-abfc-8a7ffe9c10d5"
SECRET_KEY = "EAF62B2E51A2AE8B4D03A7F22CB4DF3C"
PASSPHRASE = "Gen.248613"

# 交易参数
TEST_MODE = False  # 测试模式 True=不真正下单, False=实盘交易
# ================================

WORKSPACE = Path("/Users/shirenyushangren/.openclaw/workspace")

def generate_signature(timestamp, method, path, secret_key, passphrase, body=""):
    """生成OKX API签名"""
    message = timestamp + method + path + body
    mac = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256)
    signature = base64.b64encode(mac.digest()).decode()
    return signature

def okx_request(method, path, body=""):
    """OKX API 请求"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    signature = generate_signature(timestamp, method, path, SECRET_KEY, PASSPHRASE, body)
    
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
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            response = requests.post(url, headers=headers, data=body, timeout=15)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, data=body, timeout=15)
        else:
            return None
        
        data = response.json()
        return data
    except Exception as e:
        print(f"❌ API请求失败: {e}")
        return None

def get_balance(ccy="USDT"):
    """获取单个币种余额"""
    data = okx_request("GET", "/api/v5/account/balance")
    if data and data.get("code") == "0":
        for row in data["data"][0].get("details", []):
            if row["ccy"] == ccy:
                return {
                    "ccy": ccy,
                    "available": float(row.get("availBal", 0)),
                    "frozen": float(row.get("frozenBal", 0)),
                    "balance": float(row.get("eq", 0))
                }
    return None

def get_ticker(inst_id):
    """获取行情"""
    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "0" and data["data"]:
            t = data["data"][0]
            return {
                "last": float(t["last"]),
                "bid": float(t["bidPx"]),   # 买一价
                "ask": float(t["askPx"]),   # 卖一价
                "vol24h": float(t.get("volCcy24h", 0))
            }
    except:
        pass
    return None

def market_order(inst_id, side, size, tdMode="cash"):
    """
    市价单下单
    inst_id: 合约如 ETH-USDT-SWAP，现货如 BTC-USDT
    side: buy 或 sell
    size: 数量
    """
    path = "/api/v5/trade/order"
    method = "POST"
    
    # 现货用 instId=XXX-USDT, 合约用 XXX-USDT-SWAP
    order_data = {
        "instId": inst_id,
        "tdMode": tdMode,
        "side": side,
        "ordType": "market",
        "sz": str(size)
    }
    
    body = json.dumps(order_data)
    
    print(f"\n{'='*50}")
    print(f"🔄 市价单 {'买入' if side == 'buy' else '卖出'}")
    print(f"  币种: {inst_id}")
    print(f"  数量: {size}")
    print(f"  模式: {'测试' if TEST_MODE else '实盘'}")
    print(f"{'='*50}")
    
    if TEST_MODE:
        print("⚠️ 测试模式 - 未实际下单")
        return {"code": "0", "test": True, "order_data": order_data}
    
    result = okx_request(method, path, body)
    return result

def limit_order(inst_id, side, size, price, tdMode="cash", is_swap=False, leverage=10):
    """
    限价单下单
    inst_id: 币种
    side: buy 或 sell
    size: 数量 (币数)
    price: 价格
    is_swap: 是否是合约
    leverage: 杠杆倍数
    """
    path = "/api/v5/trade/order"
    method = "POST"
    
    # 合约用全仓模式
    if is_swap:
        tdMode = "cross"
    
    order_data = {
        "instId": inst_id,
        "tdMode": tdMode,
        "side": side,
        "ordType": "limit",
        "sz": str(size),
        "px": str(price)
    }
    
    # 合约添加杠杆
    if is_swap:
        order_data["lever"] = str(leverage)
    
    body = json.dumps(order_data)
    
    print(f"\n{'='*50}")
    print(f"🔄 限价单 {'买入' if side == 'buy' else '卖出'}")
    print(f"  币种: {inst_id}")
    print(f"  数量: {size}")
    print(f"  价格: ${price}")
    print(f"  模式: {'测试' if TEST_MODE else '实盘'}")
    print(f"{'='*50}")
    
    if TEST_MODE:
        print("⚠️ 测试模式 - 未实际下单")
        return {"code": "0", "test": True, "order_data": order_data}
    
    result = okx_request(method, path, body)
    return result

def cancel_order(inst_id, ordId):
    """撤单"""
    path = "/api/v5/trade/cancel-order"
    method = "POST"
    
    order_data = {
        "instId": inst_id,
        "ordId": ordId
    }
    
    body = json.dumps([order_data])
    
    print(f"\n❌ 撤单: {inst_id} #{ordId}")
    
    if TEST_MODE:
        print("⚠️ 测试模式 - 未实际撤单")
        return {"code": "0", "test": True}
    
    return okx_request(method, path, body)

def get_orders(inst_id="", state="all"):
    """查询订单"""
    path = f"/api/v5/trade/orders-history?instType=SPOT&state={state}"
    if inst_id:
        path += f"&instId={inst_id}"
    
    return okx_request("GET", path)

def get_account_config():
    """获取账户配置"""
    return okx_request("GET", "/api/v5/account/config")

def show_status():
    """显示交易员状态"""
    print("\n" + "="*50)
    print("💰 币圈操作员状态")
    print("="*50)
    
    # 检查API权限
    config = get_account_config()
    if config and config.get("code") == "0":
        acct = config["data"][0]
        print(f"✅ API连接正常")
        print(f"  账户ID: {acct.get('acctLv', 'N/A')}")
        
        # 检查交易权限
        perm = acct.get("perm", "")
        trade_perm = "trade" in perm.lower()
        if trade_perm:
            print(f"  交易权限: ✅ 已开启")
        else:
            print(f"  交易权限: ⚠️ 未开启 (仅查看)")
    else:
        print(f"❌ API连接失败: {config}")
    
    # USDT余额
    usdt = get_balance("USDT")
    if usdt:
        print(f"\n💵 USDT 余额:")
        print(f"  可用: {usdt['available']:.2f}")
        print(f"  冻结: {usdt['frozen']:.2f}")
    
    # 当前模式
    print(f"\n🔧 当前模式: {'🧪 测试模式' if TEST_MODE else '⚡ 实盘交易'}")
    print("="*50)

def help():
    """帮助"""
    print("""
📖 币圈操作员命令帮助:

  market_order(inst_id, side, size)    - 市价买入/卖出
  limit_order(inst_id, side, size, price) - 限价买入/卖出
  cancel_order(inst_id, ordId)          - 撤单
  get_balance(ccy)                      - 查询余额
  get_ticker(inst_id)                   - 查询行情
  show_status()                         - 查看状态
  set_mode(test=True/False)             - 切换模式

示例:
  # 市价买入 0.01 ETH
  market_order("ETH-USDT", "buy", "0.01")
  
  # 限价卖出 0.01 ETH at $2000
  limit_order("ETH-USDT", "sell", "0.01", "2000")
""")

# ============ 便捷函数 =============
def buy(ccy, qty):
    """市价买入"""
    return market_order(f"{ccy}-USDT", "buy", str(qty))

def sell(ccy, qty):
    """市价卖出"""
    return market_order(f"{ccy}-USDT", "sell", str(qty))

# 合约最小下单币数 (按张)
MIN_SWAP_LOT = {
    "BTC": 0.001,   # 每张0.001 BTC
    "ETH": 0.001,   # 每张0.001 ETH
    "SOL": 0.01,    # 每张0.01 SOL
    "ADA": 1,       # 每张1 ADA
    "DOGE": 10,     # 每张10 DOGE
}

def buy_limit(ccy, qty, price, is_swap=False, leverage=10):
    """
    限价买入
    ccy: 币种 (如 BTC, ETH)
    qty: 数量 - 合约默认填USDT数量，现货填币数
    price: 价格
    is_swap: 是否是合约 (默认False)
    leverage: 杠杆倍数 (仅合约有效)
    """
    inst_id = f"{ccy}-USDT-SWAP" if is_swap else f"{ccy}-USDT"
    
    # 合约: qty是USDT数量，需要转换为张数(1张=最小单位)
    if is_swap:
        qty_coin = float(qty) / float(price)
        min_lot = MIN_SWAP_LOT.get(ccy.upper(), 0.001)
        # 向上取整到张数
        lots = math.ceil(qty_coin / min_lot)
        sz = str(lots)  # OKX用张数
        actual_usdt = lots * min_lot * float(price)
        print(f"  💡 合约: {qty}U → {sz}张 ({lots*min_lot} {ccy}) ≈ {actual_usdt:.0f}U")
    else:
        sz = str(qty)
    
    return limit_order(inst_id, "buy", sz, str(price), is_swap=is_swap, leverage=leverage)

def sell_limit(ccy, qty, price, is_swap=False, leverage=10):
    """
    限价卖出
    ccy: 币种 (如 BTC, ETH)
    qty: 数量 - 合约默认填USDT数量，现货填币数
    price: 价格
    is_swap: 是否是合约 (默认False)
    leverage: 杠杆倍数 (仅合约有效)
    """
    inst_id = f"{ccy}-USDT-SWAP" if is_swap else f"{ccy}-USDT"
    
    # 合约: qty是USDT数量，需要转换为张数(1张=最小单位)
    if is_swap:
        qty_coin = float(qty) / float(price)
        min_lot = MIN_SWAP_LOT.get(ccy.upper(), 0.001)
        # 向上取整到张数
        lots = math.ceil(qty_coin / min_lot)
        sz = str(lots)  # OKX用张数
        actual_usdt = lots * min_lot * float(price)
        print(f"  💡 合约: {qty}U → {sz}张 ({lots*min_lot} {ccy}) ≈ {actual_usdt:.0f}U")
    else:
        sz = str(qty)
    
    return limit_order(inst_id, "sell", sz, str(price), is_swap=is_swap, leverage=leverage)

def set_mode(test):
    """切换模式"""
    global TEST_MODE
    TEST_MODE = test
    print(f"🔧 模式已切换: {'测试' if TEST_MODE else '实盘'}")

# ============ 主程序 =============
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == "status":
            show_status()
        elif cmd == "help":
            help()
        elif cmd == "balance":
            usdt = get_balance("USDT")
            print(f"USDT: {usdt}")
        elif cmd == "test-on":
            set_mode(True)
        elif cmd == "test-off":
            set_mode(False)
        else:
            print(f"未知命令: {cmd}")
            help()
    else:
        show_status()
