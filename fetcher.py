"""
SSQ 历史数据抓取与缓存。

参考: ~/Documents/tencent/ssq_system/src/api/lotto_download.py
数据源: http://data.17500.cn/ssq_asc.txt (3469 期，2003-至今)
格式:   period date r1 r2 r3 r4 r5 r6 blue [extra...]

用法:
    python3 fetcher.py            # 抓取并写缓存
    python3 fetcher.py --check    # 只检查缓存是否存在
    python3 fetcher.py --fetch    # 强制重新抓取
"""

import csv
import os
import sys
import time
from pathlib import Path

try:
    import urllib.request
except ImportError:
    print("ERROR: 需要 Python 3 stdlib 的 urllib")
    sys.exit(1)

# ── 路径与常量 ─────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
CSV_PATH = DATA_DIR / "ssq_history.csv"
META_PATH = DATA_DIR / "last_update.txt"
URL = "http://data.17500.cn/ssq_asc.txt"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TIMEOUT = 15
MAX_RETRIES = 3


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_raw() -> str:
    """从 17500 抓取原始文本。失败抛异常。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            print(f"  ⚠️ 第 {attempt}/{MAX_RETRIES} 次抓取失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2)
    raise RuntimeError(f"抓取失败 (尝试 {MAX_RETRIES} 次): {last_err}")


def parse_to_rows(raw: str):
    """
    解析 ssq_asc.txt 文本为 (period, date, red[6], blue) 元组列表。
    跳过空行和格式不对的行。
    """
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        period = parts[0]
        date = parts[1]
        try:
            reds = [int(x) for x in parts[2:8]]
            blue = int(parts[8])
        except ValueError:
            continue
        if len(reds) != 6 or not (1 <= blue <= 16):
            continue
        if not all(1 <= r <= 33 for r in reds):
            continue
        rows.append((period, date, reds, blue))
    return rows


def write_csv(rows):
    """写 CSV (period,date,r1,r2,r3,r4,r5,r6,blue)"""
    _ensure_data_dir()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["period", "date", "r1", "r2", "r3", "r4", "r5", "r6", "blue"])
        for period, date, reds, blue in rows:
            w.writerow([period, date, *reds, blue])


def write_meta(rows):
    """写元信息 (最后更新时间和期数范围)。"""
    if not rows:
        return
    first, last = rows[0], rows[-1]
    text = (
        f"last_update: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"period_count: {len(rows)}\n"
        f"first_period: {first[0]} ({first[1]})\n"
        f"last_period: {last[0]} ({last[1]})\n"
        f"source: {URL}\n"
    )
    META_PATH.write_text(text, encoding="utf-8")


def refresh(force: bool = False) -> int:
    """抓取并写缓存。返回写入的期数。"""
    _ensure_data_dir()
    if not force and CSV_PATH.exists():
        age_hours = (time.time() - CSV_PATH.stat().st_mtime) / 3600
        if age_hours < 12:
            print(f"  缓存 < 12h ({age_hours:.1f}h)，跳过抓取")
            return sum(1 for _ in CSV_PATH.open()) - 1
    print(f"  抓取 {URL} ...")
    raw = fetch_raw()
    rows = parse_to_rows(raw)
    if not rows:
        raise RuntimeError("解析后无数据，请检查 URL 或格式")
    write_csv(rows)
    write_meta(rows)
    print(f"  ✅ 写入 {len(rows)} 期到 {CSV_PATH}")
    return len(rows)


def load_rows():
    """从 CSV 读取全部历史。返回 [(period, date, reds[6], blue)]"""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"缓存不存在: {CSV_PATH}\n先跑: python3 fetcher.py")
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reds = [int(row[f"r{i}"]) for i in range(1, 7)]
            blue = int(row["blue"])
            rows.append((row["period"], row["date"], reds, blue))
    return rows


# ── CLI 入口 ─────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if "--check" in args:
        if CSV_PATH.exists():
            n = sum(1 for _ in CSV_PATH.open()) - 1
            print(f"✅ 缓存存在: {CSV_PATH} ({n} 期)")
            if META_PATH.exists():
                print("--- 元信息 ---")
                print(META_PATH.read_text(encoding="utf-8"))
        else:
            print(f"❌ 缓存不存在: {CSV_PATH}")
            print(f"   跑 `python3 {Path(__file__).name}` 来生成")
        return 0
    force = "--fetch" in args
    n = refresh(force=force)
    print(f"📊 共 {n} 期可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())