"""
SSQ 历史 Dashboard (Phase 3c)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLI 工具，接受期号或区间，输出该范围的分析。

用法:
    python3 dashboard.py 2026073                    # 单期
    python3 dashboard.py 2026001-2026073            # 区间
    python3 dashboard.py --last 30                  # 最近 30 期
    python3 dashboard.py 2026073 --predict          # 含 5 种预测 (用更早数据预测这一期)
    python3 dashboard.py --last 30 --json          # JSON 输出
"""

import argparse
import json
import sys
from pathlib import Path

from fetcher import load_rows
from tail_predictor import (
    predict_by_gap, analyze_frequency, markov_transition,
    predict_same_tail_pair, predict_balls, TAIL_TO_BALLS,
)


def find_period(rows, period_str):
    """查找期号 (返回索引, 或 None)"""
    for i, (p, _, _, _) in enumerate(rows):
        if p == period_str:
            return i
    return None


def render_period(rows, idx, with_predict=False, train_window=None):
    """渲染单期的详细信息。"""
    period, date, reds, blue = rows[idx]
    reds_sorted = sorted(reds)
    tails = sorted([r % 10 for r in reds])

    # 同尾对检测
    from collections import Counter
    tc = Counter(r % 10 for r in reds)
    pairs = [(t, [b for b in reds if b % 10 == t]) for t, c in tc.items() if c >= 2]
    has_pair = bool(pairs)

    lines = []
    lines.append("━" * 60)
    lines.append(f"📅 期号: {period}    日期: {date}")
    lines.append(f"🎯 开奖: 红 {' '.join('%02d' % r for r in reds_sorted)} + 蓝 {blue:02d}")
    lines.append(f"🔢 尾数: {tails}    同尾对: {'有' if has_pair else '无'}")
    if pairs:
        for t, balls in pairs:
            lines.append(f"   尾 {t} → {balls}")
    lines.append(f"📊 和值: {sum(reds)}    极距: {max(reds)-min(reds)}")

    # 1/3 区间
    zones = [0, 0, 0]  # 1-11, 12-22, 23-33
    for r in reds:
        if r <= 11: zones[0] += 1
        elif r <= 22: zones[1] += 1
        else: zones[2] += 1
    lines.append(f"📐 三区: {zones[0]}:{zones[1]}:{zones[2]}")

    if with_predict and idx > 50:
        # 用 idx 之前的数据预测这一期
        train = rows[max(0, idx - (train_window or idx)) : idx]
        lines.append("")
        lines.append("━━━ 📡 预测 (基于此期之前的数据) ━━━")

        # A. 频率
        a = analyze_frequency(window=len(train))
        a_top = [p['tail'] for p in a['top_picks']]
        a_hit = bool(set(a_top) & set(tails))
        lines.append(f"  A. 频率: Top 5 尾数 = {a_top}    {'✅ 命中' if a_hit else '❌ 未中'}")

        # B. 缺口
        b = predict_by_gap(window=len(train))
        b_top = [p['tail'] for p in b['top_picks']]
        b_hit = bool(set(b_top) & set(tails))
        lines.append(f"  B. 缺口: Top 5 尾数 = {b_top}    {'✅ 命中' if b_hit else '❌ 未中'}")

        # C. 马尔可夫 (用 train[-1] 作为 latest)
        # 因为 markov_transition 用最后一行，需要特殊处理
        # 简单近似：用 train 整体
        c = markov_transition(window=len(train))
        # 上一期 (train[-1]) 出现的尾数
        prev_tails = sorted([r % 10 for r in train[-1][2]])
        c_top_set = set()
        for p in c['predictions']:
            for x in p['next_probs'][:2]:
                c_top_set.add(x['tail'])
        c_hit = bool(c_top_set & set(tails))
        lines.append(f"  C. 马尔可夫: 从上期尾 {prev_tails} 预测    {'✅ 命中' if c_hit else '❌ 未中'}")

        # D. 同尾对
        d = predict_same_tail_pair(window=len(train))
        d_pred_pair = d['pair_rate'] > 0.5  # 历史比例 > 50% → 预测有
        d_actual_pair = has_pair
        d_correct = d_pred_pair == d_actual_pair
        lines.append(f"  D. 同尾对: 预测={'有' if d_pred_pair else '无'} ({d['pair_rate']:.0%}) | "
                     f"实际={'有' if d_actual_pair else '无'}    {'✅' if d_correct else '❌'}")

        # E. 球号
        e = predict_balls(window=len(train))
        e_top = set(e['top_picks'])
        e_hit_count = len(e_top & set(reds))
        lines.append(f"  E. 球号: Top {len(e_top)} 命中 {e_hit_count}/{len(reds)} 个")

    lines.append("━" * 60)
    return "\n".join(lines)


def render_range(rows, start_idx, end_idx, with_predict=False, train_window=None):
    """渲染区间汇总。"""
    from collections import Counter

    lines = []
    lines.append("━" * 60)
    lines.append(f"📊 区间汇总: {rows[start_idx][0]} ~ {rows[end_idx][0]} ({end_idx-start_idx+1} 期)")
    lines.append("━" * 60)

    sub = rows[start_idx : end_idx + 1]

    # 尾数频率
    tc = Counter()
    for _, _, reds, _ in sub:
        for r in reds:
            tc[r % 10] += 1
    total = sum(tc.values()) or 1
    lines.append("")
    lines.append("━━ 尾数频率 ━━")
    for t in sorted(tc.keys(), key=lambda x: -tc[x]):
        lines.append(f"  尾 {t}: {tc[t]:>4} ({tc[t]/total:.2%})")

    # 同尾对比例
    pair_count = 0
    for _, _, reds, _ in sub:
        cc = Counter(r % 10 for r in reds)
        if max(cc.values()) >= 2:
            pair_count += 1
    lines.append("")
    lines.append(f"━━ 同尾对: {pair_count}/{len(sub)} = {pair_count/len(sub):.2%} ━━")

    # 蓝球频率
    bc = Counter(b for _, _, _, b in sub)
    lines.append("")
    lines.append("━━ 蓝球 Top 5 ━━")
    for b, c in bc.most_common(5):
        lines.append(f"  蓝 {b:02d}: {c} 次")

    lines.append("")
    lines.append("━" * 60)

    if with_predict and start_idx > 50:
        # 区间汇总预测不太有意义（预测的是"下一期"）
        # 这里跳过
        pass

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SSQ 历史 Dashboard")
    parser.add_argument("period_or_range", nargs="?", help="期号 (如 2026073) 或区间 (如 2026001-2026073)")
    parser.add_argument("--last", type=int, help="最近 N 期")
    parser.add_argument("--predict", action="store_true", help="包含预测对比")
    parser.add_argument("--train-window", type=int, help="训练数据窗口大小 (None=全量)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    rows = load_rows()
    if not rows:
        print("❌ 无数据，先跑 fetcher.py")
        sys.exit(1)

    # 决定范围
    if args.last:
        end_idx = len(rows) - 1
        start_idx = max(0, end_idx - args.last + 1)
    elif args.period_or_range:
        s = args.period_or_range
        if "-" in s and not s.startswith("-"):
            start_str, end_str = s.split("-", 1)
            start_idx = find_period(rows, start_str)
            end_idx = find_period(rows, end_str)
            if start_idx is None or end_idx is None:
                print(f"❌ 找不到期号: {s}")
                sys.exit(1)
        else:
            idx = find_period(rows, s)
            if idx is None:
                print(f"❌ 找不到期号: {s}")
                sys.exit(1)
            start_idx = end_idx = idx
    else:
        # 默认：最近 5 期
        end_idx = len(rows) - 1
        start_idx = max(0, end_idx - 4)

    if args.json:
        # JSON 输出
        output = []
        for idx in range(start_idx, end_idx + 1):
            period, date, reds, blue = rows[idx]
            item = {
                "period": period, "date": date,
                "reds": sorted(reds), "blue": blue,
                "tails": sorted([r % 10 for r in reds]),
            }
            if args.predict and idx > 50:
                train = rows[max(0, idx - (args.train_window or idx)) : idx]
                item["predictions"] = {
                    "A_freq_top": [p['tail'] for p in analyze_frequency(window=len(train))['top_picks']],
                    "B_gap_top": [p['tail'] for p in predict_by_gap(window=len(train))['top_picks']],
                    "D_pair_rate": predict_same_tail_pair(window=len(train))['pair_rate'],
                    "E_ball_top": predict_balls(window=len(train))['top_picks'],
                }
            output.append(item)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if start_idx == end_idx:
            print(render_period(rows, start_idx,
                                with_predict=args.predict,
                                train_window=args.train_window))
        else:
            print(render_range(rows, start_idx, end_idx,
                               with_predict=args.predict,
                               train_window=args.train_window))
            # 如果区间小 (<=10)，逐期显示
            if end_idx - start_idx <= 10:
                print()
                for idx in range(start_idx, end_idx + 1):
                    print(render_period(rows, idx,
                                        with_predict=args.predict,
                                        train_window=args.train_window))


if __name__ == "__main__":
    main()