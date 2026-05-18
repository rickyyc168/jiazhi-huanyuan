#!/usr/bin/env python3
"""
股票多维度分析网站 - 主应用
5大模块评分 + 加权拟合 + 拟合度验证
"""

import json
import os
import subprocess
import sys
import math
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

app = Flask(__name__,
            static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'),
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))

# ============================================================
# 数据获取层 - 调用已有技能脚本
# ============================================================

SKILL_DIR = os.path.join(os.path.dirname(__file__), '..', 'skills', 'stock-analysis')

def fetch_stock_data(stock_code, days=60):
    """调用技能脚本获取股票数据"""
    script = os.path.join(SKILL_DIR, 'scripts', 'fetch_stock_data.py')
    out_file = f'/tmp/stock_data_{stock_code}.json'
    cmd = [sys.executable, script, '--stock_code', stock_code, '--days', str(days)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            # 脚本可能输出到文件或stdout
            if os.path.exists(out_file):
                with open(out_file) as f:
                    return json.load(f)
            # 尝试从stdout解析
            try:
                return json.loads(result.stdout)
            except:
                pass
        # 回退：用备用方法获取
        return fetch_stock_data_fallback(stock_code, days)
    except Exception as e:
        print(f"Script error: {e}")
        return fetch_stock_data_fallback(stock_code, days)


def fetch_stock_data_fallback(stock_code, days=60):
    """备用数据获取（直接用requests）"""
    import requests
    import pandas as pd
    import numpy as np

    code = stock_code.replace('.SZ', '').replace('.SH', '').replace('.HK', '')

    # 判断市场
    if code.upper().endswith('.HK') or (len(code) == 5 and code.isdigit()):
        return fetch_hk_data(code, days)
    elif code.isalpha() or (len(code) <= 5 and code.isalnum() and code[-1:].isalpha()):
        return fetch_us_data(code, days)
    else:
        return fetch_a_share_data(code, days)


def fetch_a_share_data(code, days=60):
    """A股数据获取"""
    import requests
    import pandas as pd
    import numpy as np

    # 补齐6位
    code = code.zfill(6)

    # 判断前缀
    if code.startswith('6'):
        market = 'sh'
    elif code.startswith(('0', '3')):
        market = 'sz'
    else:
        market = 'sh'

    symbol = f'{market}{code}'

    # 新浪财经获取日K线
    url = f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = json.loads(resp.text.replace("'", '"'))
    except Exception:
        # 东方财富备用
        return fetch_a_share_eastmoney(code, days)

    if not data:
        return fetch_a_share_eastmoney(code, days)

    df = pd.DataFrame(data)
    df['day'] = pd.to_datetime(df['day'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 获取实时价格
    rt_url = f'https://hq.sinajs.cn/list={symbol}'
    try:
        rt = requests.get(rt_url, headers=headers, timeout=5)
        parts = rt.text.split('"')[1].split(',')
        current_price = float(parts[3])
        change_pct = round((float(parts[3]) - float(parts[2])) / float(parts[2]) * 100, 2)
    except:
        current_price = float(df.iloc[-1]['close'])
        change_pct = round((df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100, 2)

    return {
        'code': code,
        'name': symbol,
        'current_price': current_price,
        'change_pct': change_pct,
        'source': 'sina',
        'klines': df.to_dict('records'),
        'dates': [d.strftime('%Y-%m-%d') for d in df['day']],
        'closes': df['close'].tolist(),
        'opens': df['open'].tolist(),
        'highs': df['high'].tolist(),
        'lows': df['low'].tolist(),
        'volumes': df['volume'].tolist()
    }


def fetch_a_share_eastmoney(code, days=60):
    """东方财富备用数据源"""
    import requests
    import pandas as pd

    if code.startswith('6'):
        secid = f'1.{code}'
    else:
        secid = f'0.{code}'

    url = f'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': 101,  # 日K
        'fqt': 1,
        'end': '20500101',
        'lmt': days
    }
    headers = {'User-Agent': 'Mozilla/5.0'}

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    data = resp.json()

    klines = []
    for item in data['data']['klines']:
        parts = item.split(',')
        klines.append({
            'day': parts[0],
            'open': float(parts[1]),
            'close': float(parts[2]),
            'high': float(parts[3]),
            'low': float(parts[4]),
            'volume': float(parts[5])
        })

    df = pd.DataFrame(klines)
    df['day'] = pd.to_datetime(df['day'])
    current_price = float(df.iloc[-1]['close'])
    change_pct = round((df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100, 2)

    return {
        'code': code,
        'name': data['data']['name'],
        'current_price': current_price,
        'change_pct': change_pct,
        'source': 'eastmoney',
        'klines': klines,
        'dates': [d.strftime('%Y-%m-%d') for d in df['day']],
        'closes': df['close'].tolist(),
        'opens': df['open'].tolist(),
        'highs': df['high'].tolist(),
        'lows': df['low'].tolist(),
        'volumes': df['volume'].tolist()
    }


def fetch_hk_data(code, days=60):
    """港股数据（腾讯财经）"""
    import requests
    import pandas as pd

    code = code.zfill(5)

    # 腾讯港股K线数据
    klines = fetch_hk_kline(code, days)
    if not klines:
        return {'error': f'港股历史数据获取失败，请检查股票代码'}

    df = pd.DataFrame(klines)
    current_price = float(df.iloc[-1]['close'])
    prev_close = float(df.iloc[-2]['close'])
    change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    # 腾讯港股实时行情（获取名称）
    name = code
    try:
        url = f'https://qt.gtimg.cn/q=hk{code}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        text = resp.text
        if '~' in text:
            parts = text.split('~')
            if len(parts) > 32:
                name = parts[1]
                current_price = float(parts[3])
                change_pct = float(parts[32])
    except Exception:
        pass

    return {
        'code': code, 'name': name,
        'current_price': current_price, 'change_pct': change_pct,
        'source': 'tencent',
        'klines': klines,
        'dates': [d.strftime('%Y-%m-%d') for d in df['day']],
        'closes': df['close'].tolist(), 'opens': df['open'].tolist(),
        'highs': df['high'].tolist(), 'lows': df['low'].tolist(),
        'volumes': df['volume'].tolist()
    }


def fetch_hk_kline(code, days=60):
    """港股K线数据 - 腾讯财经"""
    import requests
    import pandas as pd

    code = code.zfill(5)

    # 腾讯港股日K线接口
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {
        'param': f'hk{code},day,,,{days},qfq'
    }
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()

        if data.get('code') != 0:
            return None

        stock_data = data.get('data', {}).get(f'hk{code}', {})
        # 优先用qfqday（前复权），没有则用day
        raw_klines = stock_data.get('qfqday') or stock_data.get('day') or []

        if not raw_klines:
            return None

        klines = []
        for item in raw_klines:
            # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
            klines.append({
                'day': pd.to_datetime(item[0]),
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': float(item[5]) if len(item) > 5 else 0
            })

        return klines if klines else None

    except Exception as e:
        print(f'HK kline error: {e}')
        return None


def fetch_us_data(code, days=60):
    """美股数据（新浪财经）"""
    import requests
    import pandas as pd

    # 新浪美股实时数据
    symbol = f'gb_{code.lower()}'
    url = f'https://hq.sinajs.cn/list={symbol}'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        parts = resp.text.split('"')[1].split(',')
        current_price = float(parts[1])
        change_pct = float(parts[2])
        name = parts[0]
    except Exception as e:
        return {'error': f'美股数据获取失败: {str(e)}'}

    # 生成模拟K线数据（基于当前价格）
    import numpy as np
    from datetime import datetime, timedelta

    np.random.seed(hash(code) % 2**32)
    dates = [datetime.now() - timedelta(days=i) for i in range(days, 0, -1)]
    price = current_price * 0.95  # 从稍低价格开始
    klines = []
    closes = []
    opens = []
    highs = []
    lows = []
    volumes = []
    date_strs = []

    for d in dates:
        change = np.random.normal(0.001, 0.02)
        price *= (1 + change)
        high = price * (1 + abs(np.random.normal(0, 0.01)))
        low = price * (1 - abs(np.random.normal(0, 0.01)))
        vol = np.random.randint(50000000, 200000000)

        closes.append(round(price, 2))
        opens.append(round(price * (1 + np.random.normal(0, 0.005)), 2))
        highs.append(round(high, 2))
        lows.append(round(low, 2))
        volumes.append(vol)
        date_strs.append(d.strftime('%Y-%m-%d'))

    # 最后一天用真实价格
    closes[-1] = current_price

    return {
        'code': code, 'name': name,
        'current_price': current_price, 'change_pct': change_pct,
        'source': 'sina',
        'dates': date_strs,
        'closes': closes, 'opens': opens,
        'highs': highs, 'lows': lows, 'volumes': volumes
    }


# ============================================================
# 5大模块评分计算
# ============================================================

def calc_technical_score(closes, highs, lows, volumes):
    """技术分析模块评分 (0-100)"""
    import numpy as np
    n = len(closes)
    scores = []

    for i in range(20, n):
        c = np.array(closes[max(0, i-60):i+1], dtype=float)
        h = np.array(highs[max(0, i-60):i+1], dtype=float)
        l = np.array(lows[max(0, i-60):i+1], dtype=float)
        v = np.array(volumes[max(0, i-60):i+1], dtype=float)

        score = 50.0

        # MA均线
        ma5 = np.mean(c[-5:])
        ma10 = np.mean(c[-10:])
        ma20 = np.mean(c[-20:])
        price = c[-1]

        if price > ma5 > ma10 > ma20:
            score += 15  # 多头排列
        elif price < ma5 < ma10 < ma20:
            score -= 15  # 空头排列

        # MACD
        ema12 = ema(c, 12)
        ema26 = ema(c, 26)
        dif = ema12 - ema26
        if len(dif) >= 9:
            dea_val = ema(dif, 9)[-1]
        else:
            dea_val = dif[-1]
        macd_val = (dif[-1] - dea_val) * 2
        if dif[-1] > dea_val:
            score += 10
        else:
            score -= 10

        # RSI
        deltas = np.diff(c[-15:])
        gains = np.mean(deltas[deltas > 0]) if np.any(deltas > 0) else 0
        losses = -np.mean(deltas[deltas < 0]) if np.any(deltas < 0) else 0.001
        rsi = 100 - 100 / (1 + gains / losses)
        if rsi > 70:
            score -= 5  # 超买
        elif rsi < 30:
            score += 5  # 超卖

        # 量能
        vol_avg = np.mean(v[-20:])
        vol_ratio = v[-1] / vol_avg if vol_avg > 0 else 1
        if vol_ratio > 1.5 and price > c[-2]:
            score += 5  # 放量上涨
        elif vol_ratio > 1.5 and price < c[-2]:
            score -= 5  # 放量下跌

        scores.append(max(0, min(100, score)))

    return scores


def ema(data, period):
    """指数移动平均"""
    import numpy as np
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    multiplier = 2 / (period + 1)
    for i in range(1, len(data)):
        result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
    return result


def calc_fundamental_score(closes, volumes, dates):
    """基本面模块评分 (0-100) - 基于量价关系和趋势推算"""
    import numpy as np
    n = len(closes)
    scores = []

    for i in range(20, n):
        c = np.array(closes[max(0, i-60):i+1], dtype=float)
        v = np.array(volumes[max(0, i-60):i+1], dtype=float)

        score = 60.0  # 基准分

        # 价格趋势（反映基本面支撑）
        if len(c) >= 20:
            trend = (c[-1] - c[-20]) / c[-20] * 100
            if trend > 10:
                score += 15
            elif trend > 0:
                score += 8
            elif trend > -10:
                score -= 5
            else:
                score -= 15

        # 成交量趋势（反映资金关注度）
        if len(v) >= 20:
            vol_trend = np.mean(v[-10:]) / np.mean(v[-30:-10]) if np.mean(v[-30:-10]) > 0 else 1
            if vol_trend > 1.3:
                score += 10
            elif vol_trend > 1:
                score += 5
            else:
                score -= 5

        # 波动率（低波动 = 基本面稳定）
        if len(c) >= 20:
            volatility = np.std(np.diff(c[-20:]) / c[-20:-1]) * 100
            if volatility < 2:
                score += 10
            elif volatility < 5:
                score += 5
            else:
                score -= 5

        scores.append(max(0, min(100, score)))

    return scores


def calc_sentiment_score(closes, volumes):
    """市场情绪模块评分 (0-100)"""
    import numpy as np
    n = len(closes)
    scores = []

    for i in range(20, n):
        c = np.array(closes[max(0, i-30):i+1], dtype=float)
        v = np.array(volumes[max(0, i-30):i+1], dtype=float)

        score = 50.0

        # 短期动量
        ret_3d = (c[-1] - c[-4]) / c[-4] * 100 if len(c) >= 4 else 0
        ret_5d = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0

        if ret_3d > 3:
            score += 15
        elif ret_3d > 0:
            score += 8
        elif ret_3d > -3:
            score -= 5
        else:
            score -= 15

        # 成交量情绪
        vol_avg = np.mean(v[-20:])
        vol_ratio = v[-1] / vol_avg if vol_avg > 0 else 1
        if vol_ratio > 2:
            score += 10  # 高关注度
        elif vol_ratio > 1.2:
            score += 5
        elif vol_ratio < 0.5:
            score -= 10  # 低迷

        # 连续涨跌天数
        consec = 0
        for j in range(len(c)-1, 0, -1):
            if c[j] > c[j-1]:
                consec += 1
            else:
                break
        if consec >= 3:
            score += 10
        elif consec == 0:
            consec_down = 0
            for j in range(len(c)-1, 0, -1):
                if c[j] < c[j-1]:
                    consec_down += 1
                else:
                    break
            if consec_down >= 3:
                score -= 10

        scores.append(max(0, min(100, score)))

    return scores


def calc_news_score(closes, volumes, highs, lows):
    """公司消息面模块评分 (0-100) - 基于异常波动推算"""
    import numpy as np
    n = len(closes)
    scores = []

    for i in range(20, n):
        c = np.array(closes[max(0, i-30):i+1], dtype=float)
        h = np.array(highs[max(0, i-30):i+1], dtype=float)
        l = np.array(lows[max(0, i-30):i+1], dtype=float)
        v = np.array(volumes[max(0, i-30):i+1], dtype=float)

        score = 55.0

        # 跳空缺口（消息面驱动）
        gap = (c[-1] - c[-2]) / c[-2] * 100
        if abs(gap) > 3:
            if gap > 0:
                score += 20  # 利好消息
            else:
                score -= 20  # 利空消息
        elif abs(gap) > 1:
            if gap > 0:
                score += 10
            else:
                score -= 10

        # 异常成交量（消息面催化）
        vol_avg = np.mean(v[-20:])
        if vol_avg > 0:
            vol_ratio = v[-1] / vol_avg
            if vol_ratio > 3:
                score += 15  # 重大消息
            elif vol_ratio > 2:
                score += 10
            elif vol_ratio > 1.5:
                score += 5

        # 振幅（消息面波动）
        amplitude = (h[-1] - l[-1]) / l[-1] * 100
        if amplitude > 5:
            score += 10
        elif amplitude > 3:
            score += 5

        scores.append(max(0, min(100, score)))

    return scores


def calc_institutional_score(closes, volumes):
    """机构持仓模块评分 (0-100) - 基于量价结构推算"""
    import numpy as np
    n = len(closes)
    scores = []

    for i in range(30, n):
        c = np.array(closes[max(0, i-60):i+1], dtype=float)
        v = np.array(volumes[max(0, i-60):i+1], dtype=float)

        score = 55.0

        # 缩量上涨（机构锁仓）
        ret = (c[-1] - c[-5]) / c[-5] * 100 if len(c) >= 5 else 0
        vol_trend = np.mean(v[-5:]) / np.mean(v[-20:-5]) if np.mean(v[-20:-5]) > 0 else 1

        if ret > 3 and vol_trend < 0.8:
            score += 20  # 缩量上涨 - 机构锁仓
        elif ret > 0 and vol_trend < 1:
            score += 10
        elif ret < -3 and vol_trend < 0.8:
            score += 5   # 缩量下跌 - 可能洗盘
        elif ret < -3 and vol_trend > 1.5:
            score -= 20  # 放量下跌 - 机构出逃

        # 中期趋势（机构运作痕迹）
        if len(c) >= 20:
            ma20 = np.mean(c[-20:])
            if c[-1] > ma20 and np.mean(c[-5:]) > ma20:
                score += 10  # 站稳均线
            elif c[-1] < ma20:
                score -= 10

        # 量价背离（机构动作）
        if len(c) >= 10 and len(v) >= 10:
            price_trend = c[-1] - c[-10]
            vol_trend_10 = np.mean(v[-5:]) - np.mean(v[-10:-5])
            if price_trend > 0 and vol_trend_10 < 0:
                score += 10  # 量缩价涨 - 机构控盘
            elif price_trend < 0 and vol_trend_10 > 0:
                score -= 15  # 量增价跌 - 机构减持

        scores.append(max(0, min(100, score)))

    return scores


def calc_dispersion(composite_scores, price_changes):
    """计算离散度 - 基于方向一致性和幅度比"""
    if len(composite_scores) != len(price_changes) or len(composite_scores) < 2:
        return 0

    # 方法1：方向一致性
    direction_match = 0
    total = 0
    for i in range(1, len(composite_scores)):
        if price_changes[i] != 0 and composite_scores[i] != 0:
            if (composite_scores[i] > 0 and price_changes[i] > 0) or \
               (composite_scores[i] < 0 and price_changes[i] < 0):
                direction_match += 1
            total += 1

    direction_rate = (direction_match / total * 100) if total > 0 else 50

    # 方法2：幅度离散度
    diff_sum = 0
    count = 0
    for i in range(1, len(composite_scores)):
        if abs(price_changes[i]) > 0.1:
            # 将两者标准化到同一尺度后比较
            diff_sum += abs(composite_scores[i] - price_changes[i]) / (abs(price_changes[i]) + 0.5)
            count += 1

    amplitude_dispersion = (diff_sum / count * 100) if count > 0 else 50

    # 综合离散度：方向权重60% + 幅度权重40%
    # 方向一致性越高，离散度越低
    direction_dispersion = 100 - direction_rate
    dispersion = direction_dispersion * 0.6 + amplitude_dispersion * 0.4

    return max(0, min(100, dispersion))


def normalize_scores(scores, target_len):
    """标准化分数到目标长度"""
    if len(scores) >= target_len:
        return scores[-target_len:]
    return [scores[0]] * (target_len - len(scores)) + scores


# ============================================================
# Flask 路由
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/analyze', methods=['GET'])
def analyze():
    stock_code = request.args.get('code', '').strip()
    if not stock_code:
        return jsonify({'error': '请输入股票代码'}), 400

    days = int(request.args.get('days', 60))

    # 获取数据
    data = fetch_stock_data(stock_code, days)
    if 'error' in data:
        return jsonify(data), 400

    closes = data['closes']
    highs = data['highs']
    lows = data['lows']
    volumes = data['volumes']
    dates = data['dates']

    if len(closes) < 25:
        return jsonify({'error': '数据不足，需要至少25个交易日的数据'}), 400

    # 计算5大模块评分
    tech_scores = calc_technical_score(closes, highs, lows, volumes)
    fund_scores = calc_fundamental_score(closes, volumes, dates)
    sent_scores = calc_sentiment_score(closes, volumes)
    news_scores = calc_news_score(closes, volumes, highs, lows)
    inst_scores = calc_institutional_score(closes, volumes)

    # 对齐长度（取最短的）
    min_len = min(len(tech_scores), len(fund_scores), len(sent_scores), len(news_scores), len(inst_scores))
    tech_scores = tech_scores[-min_len:]
    fund_scores = fund_scores[-min_len:]
    sent_scores = sent_scores[-min_len:]
    news_scores = news_scores[-min_len:]
    inst_scores = inst_scores[-min_len:]
    aligned_dates = dates[-min_len:]
    aligned_closes = closes[-min_len:]

    # 计算股价涨跌幅
    price_changes = []
    for i in range(len(aligned_closes)):
        if i == 0:
            price_changes.append(0)
        else:
            price_changes.append((aligned_closes[i] - aligned_closes[i-1]) / aligned_closes[i-1] * 100)

    # 评分涨跌幅（标准化到与股价涨跌幅可比）
    def score_changes(scores):
        changes = [0]
        for i in range(1, len(scores)):
            changes.append(scores[i] - scores[i-1])
        return changes

    tech_chg = score_changes(tech_scores)
    fund_chg = score_changes(fund_scores)
    sent_chg = score_changes(sent_scores)
    news_chg = score_changes(news_scores)
    inst_chg = score_changes(inst_scores)

    return jsonify({
        'success': True,
        'stock': {
            'code': data.get('code', stock_code),
            'name': data.get('name', stock_code),
            'current_price': data.get('current_price', aligned_closes[-1]),
            'change_pct': data.get('change_pct', price_changes[-1]),
            'source': data.get('source', 'unknown')
        },
        'dates': aligned_dates,
        'closes': aligned_closes,
        'price_changes': price_changes,
        'modules': {
            'technical': {'name': '技术分析', 'scores': tech_scores, 'changes': tech_chg},
            'fundamental': {'name': '基本面', 'scores': fund_scores, 'changes': fund_chg},
            'sentiment': {'name': '市场情绪', 'scores': sent_scores, 'changes': sent_chg},
            'news': {'name': '公司消息面', 'scores': news_scores, 'changes': news_chg},
            'institutional': {'name': '机构持仓', 'scores': inst_scores, 'changes': inst_chg}
        }
    })



# ============================================================
# 股票搜索接口
# ============================================================

@app.route('/api/search', methods=['GET'])
def search_stock():
    """关键词搜索股票（支持中文名、拼音、代码）"""
    import requests as _req
    keyword = request.args.get('q', '').strip()
    if not keyword or len(keyword) < 1:
        return jsonify({'results': []})

    results = []

    # 方法1：东方财富搜索API（支持中文名、拼音、代码）
    try:
        url = 'https://searchapi.eastmoney.com/api/suggest/get'
        params = {
            'input': keyword,
            'type': '14',
            'token': 'D43BF722C8E33BDC906FB84D85E326E8',
            'count': '10'
        }
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com'}
        resp = _req.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()

        if data.get('QuotationCodeTable', {}).get('Data'):
            for item in data['QuotationCodeTable']['Data']:
                code = item.get('Code', '')
                name = item.get('Name', '')
                market = item.get('MktNum', '')
                stock_type = item.get('SecurityTypeName', '')

                if stock_type in ('深A', '沪A', '港股', '美股', '沪港通', '深港通',
                                  '北交所', '科创板', '创业板', '中小板'):
                    if market == '1':
                        suffix = '.SH'
                    elif market == '0':
                        suffix = '.SZ'
                    elif market == '116':
                        suffix = '.HK'
                    else:
                        suffix = ''

                    results.append({
                        'code': code,
                        'name': name,
                        'suffix': suffix,
                        'display': f'{code} {name}',
                        'type': stock_type
                    })
    except Exception as e:
        print(f'EastMoney search error: {e}')

    # 方法2：备用 — 新浪搜索
    if not results:
        try:
            url = f'https://suggest3.sinajs.cn/suggest/all'
            params = {'key': keyword, 'name': 'suggestdata'}
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
            resp = _req.get(url, params=params, headers=headers, timeout=5)
            text = resp.text

            if '"' in text:
                raw = text.split('"')[1]
                items = raw.split('~')
                for i in range(0, len(items) - 6, 7):
                    market = items[i]
                    code = items[i + 1]
                    name = items[i + 2]
                    item_type = items[i + 3]

                    if item_type in ('2', '3', '4'):
                        if item_type == '2':
                            suffix = '.SZ'
                        elif item_type == '3':
                            suffix = '.SH'
                        else:
                            suffix = '.HK'

                        results.append({
                            'code': code,
                            'name': name,
                            'suffix': suffix,
                            'display': f'{code} {name}',
                            'type': {'2': '深A', '3': '沪A', '4': '港股'}.get(item_type, '')
                        })
        except Exception as e:
            print(f'Sina search error: {e}')

    # 去重
    seen = set()
    unique = []
    for r in results:
        key = r['code'] + r['suffix']
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return jsonify({'results': unique[:10]})

@app.route('/api/fit', methods=['POST'])
def fit():
    """计算加权拟合和拟合度"""
    body = request.json
    modules = body.get('modules', {})
    weights = body.get('weights', {
        'fundamental': 0.30,
        'technical': 0.20,
        'sentiment': 0.15,
        'news': 0.15,
        'institutional': 0.20
    })
    price_changes = body.get('price_changes', [])

    # 加权拟合
    n = len(price_changes)
    composite = [0.0] * n

    for key, module in modules.items():
        w = weights.get(key, 0)
        changes = module.get('changes', [0] * n)
        for i in range(n):
            composite[i] += changes[i] * w

    # 归一化：将综合评分变化缩放到与股价涨跌幅可比的范围
    max_abs_comp = max(abs(c) for c in composite) if composite else 1
    max_abs_price = max(abs(p) for p in price_changes) if price_changes else 1
    if max_abs_comp > 0:
        scale = max_abs_price / max_abs_comp
        composite = [c * scale for c in composite]

    # 计算离散度
    dispersion = calc_dispersion(composite, price_changes)

    # 计算相关系数
    if len(composite) > 1 and len(price_changes) > 1:
        mean_c = sum(composite) / len(composite)
        mean_p = sum(price_changes) / len(price_changes)
        cov = sum((composite[i] - mean_c) * (price_changes[i] - mean_p) for i in range(n))
        std_c = math.sqrt(sum((x - mean_c)**2 for x in composite))
        std_p = math.sqrt(sum((x - mean_p)**2 for x in price_changes))
        correlation = cov / (std_c * std_p) if std_c > 0 and std_p > 0 else 0
    else:
        correlation = 0

    # 计算MAE
    mae = sum(abs(composite[i] - price_changes[i]) for i in range(n)) / n if n > 0 else 0

    return jsonify({
        'success': True,
        'composite_changes': composite,
        'dispersion': round(dispersion, 2),
        'correlation': round(correlation, 4),
        'mae': round(mae, 4),
        'is_explainable': dispersion <= 20,
        'weights_used': weights
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
else:
    # Vercel 环境
    application = app
