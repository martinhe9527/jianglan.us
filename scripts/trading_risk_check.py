#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace')
DATA_FILE = ROOT / 'scripts' / 'trading-plan-data.json'
ENV_FILE = ROOT / '.env.tushare'
VENV_SITE = next((ROOT / '.venv-market' / 'lib').glob('python*/site-packages'), None)
if VENV_SITE and VENV_SITE.exists():
    sys.path.insert(0, str(VENV_SITE))


def load_env_file(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


def load_holdings():
    data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    return data.get('holdings', [])


def to_ts_code(code: str):
    return f"{code}.SZ" if code.startswith(('0', '3')) else f"{code}.SH"


def fetch_daily_with_tushare(ts_code: str):
    load_env_file(ENV_FILE)
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise RuntimeError('缺少 TUSHARE_TOKEN')

    import tushare as ts  # type: ignore

    pro = ts.pro_api(token)
    df = pro.stk_factor(ts_code=ts_code, start_date='20250101')
    if df is None or df.empty:
        raise RuntimeError(f'{ts_code} 未返回 stk_factor 数据')

    df = df.sort_values('trade_date', ascending=False).reset_index(drop=True)
    latest = df.iloc[0]
    close_price = float(latest['close'])
    return {
        'symbol': ts_code,
        'date': str(latest['trade_date']),
        'close': close_price,
        'pct': float(latest['pct_change']) if 'pct_change' in latest else 0.0,
        'macd': float(latest['macd']) if 'macd' in latest else 0.0,
        'kdj_j': float(latest['kdj_j']) if 'kdj_j' in latest else 0.0,
        'rsi_6': float(latest['rsi_6']) if 'rsi_6' in latest else 0.0,
    }


def classify(cost: float, data: dict):
    close_price = data['close']
    diff_pct = ((close_price - cost) / cost) * 100
    weak_macd = data['macd'] < 0
    weak_rsi = data['rsi_6'] < 35
    weak_kdj = data['kdj_j'] < 10

    if diff_pct <= -5 or (weak_macd and weak_rsi and weak_kdj):
        return '明显转弱', (
            f"收盘 {close_price:.2f}，较成本低 {abs(diff_pct):.2f}%；"
            f"MACD为负、RSI偏弱、KDJ J值低，先收缩仓位。"
        )
    if diff_pct <= -2 or weak_macd or weak_rsi:
        return '接近止损', (
            f"收盘 {close_price:.2f}，较成本低 {abs(diff_pct):.2f}%；"
            f"短线已偏弱，明天优先盯风控线。"
        )
    return '继续观察', (
        f"收盘 {close_price:.2f}，较成本 {'+' if diff_pct >= 0 else ''}{diff_pct:.2f}%；"
        f"短线暂未出现明显失控，继续观察。"
    )


def evaluate_holdings(holdings: list[dict], sleep_seconds: float = 31.0):
    output = []
    for index, item in enumerate(holdings):
        if index > 0:
            time.sleep(sleep_seconds)
        ts_code = to_ts_code(item['code'])
        data = fetch_daily_with_tushare(ts_code)
        action, reason = classify(float(item['cost']), data)
        output.append({
            'code': item['code'],
            'name': item['name'],
            'cost': item['cost'],
            'date': data['date'],
            'close': data['close'],
            'macd': round(data['macd'], 4),
            'kdj_j': round(data['kdj_j'], 2),
            'rsi_6': round(data['rsi_6'], 2),
            'action': action,
            'reason': reason,
        })
    return output


def main():
    holdings = load_holdings()
    output = evaluate_holdings(holdings)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
