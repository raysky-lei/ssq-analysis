"""
尾数预测 — Phase 1 + Phase 3
提供 5 种预测方法 (A/B/C/D/E):
  A. 尾数频率      analyze_frequency()
  B. 尾数缺口      predict_by_gap()  [Phase 1]
  C. 马尔可夫转移  markov_transition()
  D. 同尾对预测    predict_same_tail_pair()
  E. 具体球号预测  predict_balls()

⚠️ 重要声明:
    双色球每期是独立随机事件。任何预测方法的长期命中率均受概率上限约束。
    本工具的预测结果仅用于结构化展示和辅助决策，**不是中奖保证**。

参考: ~/Documents/tencent/ssq_system/ 的 omit/tail 计算思路
      以及 ssq_system 项目里"所有策略长期都亏损"的实验结论。
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from fetcher import load_rows

# 红球尾数 0-9 对应的所有球号 (1-33)
TAIL_TO_BALLS = {
    t: sorted(b for b in range(1, 34) if b % 10 == t) for t in range(10)
}


# ════════════════════════════════════════════════════════════
# 公共工具
# ════════════════════════════════════════════════════════════
def _to_tails(reds):
    """红球列表 → 尾数集合"""
    return set(r % 10 for r in reds)


def _slice(rows, window):
    """按窗口截取数据"""
    if window and len(rows) > window:
        return rows[-window:]
    return rows


# ════════════════════════════════════════════════════════════
# B. 尾数缺口 (Phase 1)
# ════════════════════════════════════════════════════════════
def calc_tail_omission(rows):
    """计算每个尾数当前的缺口期数。"""
    rows_rev = list(reversed(rows))
    tail_last_seen = {}
    latest_reds = set(rows_rev[0][2]) if rows_rev else set()

    for idx, (period, date, reds, blue) in enumerate(rows_rev):
        tails_in_draw = {r % 10 for r in reds}
        for t in range(10):
            if t not in tail_last_seen and t in tails_in_draw:
                tail_last_seen[t] = (idx, period, date)

    result = []
    for t in range(10):
        if t in tail_last_seen:
            idx, period, date = tail_last_seen[t]
            gap = idx
        else:
            gap = len(rows_rev)
            period, date = None, None
        result.append({
            "tail": t,
            "gap": gap,
            "last_period": period,
            "last_date": date,
            "present_in_latest": t in latest_reds,
            "balls_in_tail": TAIL_TO_BALLS[t],
        })

    result.sort(key=lambda x: -x["gap"])
    return result


def calc_ball_omission_in_tail(tail_data, rows_rev):
    """对单个尾数，计算其下每个球号的缺口。"""
    tail = tail_data["tail"]
    balls = TAIL_TO_BALLS[tail]
    ball_last_seen = {}
    for idx, (period, date, reds, blue) in enumerate(rows_rev):
        for b in balls:
            if b not in ball_last_seen and b in reds:
                ball_last_seen[b] = (idx, period)
    result = []
    for b in balls:
        if b in ball_last_seen:
            idx, period = ball_last_seen[b]
            gap = idx
        else:
            gap = len(rows_rev)
            period = None
        result.append({"ball": b, "gap": gap, "last_period": period})
    result.sort(key=lambda x: -x["gap"])
    return result


def predict_by_gap(window=None, top_n=5):
    """B. 尾数缺口预测。返回 dict 含 tails (含 ball_gaps) + top_picks。"""
    rows = _slice(load_rows(), window)
    rows_rev = list(reversed(rows))
    tail_data = calc_tail_omission(rows)

    for t in tail_data:
        t["ball_gaps"] = calc_ball_omission_in_tail(t, rows_rev)

    top_picks = []
    for t in tail_data[:top_n]:
        top_balls = t["ball_gaps"][:2]
        top_picks.append({
            "tail": t["tail"],
            "tail_gap": t["gap"],
            "candidate_balls": [b["ball"] for b in top_balls],
            "ball_gaps": [(b["ball"], b["gap"]) for b in top_balls],
        })

    return {
        "method": "B.缺口",
        "as_of_period": rows[-1][0],
        "as_of_date": rows[-1][1],
        "total_periods": len(rows),
        "window": window,
        "tails": tail_data,
        "top_picks": top_picks,
    }


# ════════════════════════════════════════════════════════════
# A. 尾数频率 (Phase 3)
# ════════════════════════════════════════════════════════════
def analyze_frequency(window=None, top_n=5):
    """
    A. 尾数频率分析。
    统计每个尾数在最近 N 期的出现次数 (含重复), 输出 top_n。
    """
    rows = _slice(load_rows(), window)
    tail_counts = Counter()
    for _, _, reds, _ in rows:
        for r in reds:
            tail_counts[r % 10] += 1
    total = sum(tail_counts.values()) or 1

    result = []
    for t in range(10):
        c = tail_counts.get(t, 0)
        result.append({
            "tail": t,
            "count": c,
            "pct": round(c / total, 4),
        })
    result.sort(key=lambda x: -x["count"])

    top_picks = [
        {"tail": t["tail"], "count": t["count"], "pct": t["pct"]}
        for t in result[:top_n]
    ]

    return {
        "method": "A.频率",
        "as_of_period": rows[-1][0],
        "as_of_date": rows[-1][1],
        "total_periods": len(rows),
        "window": window,
        "tails": result,
        "top_picks": top_picks,
    }


# ════════════════════════════════════════════════════════════
# C. 马尔可夫转移 (Phase 3)
# ════════════════════════════════════════════════════════════
def markov_transition(window=None, top_n=5):
    """
    C. 一阶马尔可夫：P(下一期尾=t | 本期尾=t')。
    上一期出现的所有尾数都作为 'current'，下一期出现的作为 'next'。
    """
    rows = _slice(load_rows(), window)
    transitions = defaultdict(Counter)  # current_tail -> Counter(next_tail)

    for i in range(len(rows) - 1):
        curr_tails = _to_tails(rows[i][2])
        next_tails = _to_tails(rows[i + 1][2])
        for c in curr_tails:
            for n in next_tails:
                transitions[c][n] += 1

    # 归一化
    matrix = {}
    for c in range(10):
        total = sum(transitions[c].values())
        if total == 0:
            matrix[c] = {n: 0.0 for n in range(10)}
            continue
        matrix[c] = {
            n: round(transitions[c].get(n, 0) / total, 4)
            for n in range(10)
        }

    # 基于最新一期，给出预测
    latest_tails = _to_tails(rows[-1][2])
    predictions = []
    for c in sorted(latest_tails):
        # 从 c 的转移中取 top_n
        sorted_next = sorted(matrix[c].items(), key=lambda x: -x[1])[:top_n]
        predictions.append({
            "from_tail": c,
            "next_probs": [{"tail": n, "prob": p} for n, p in sorted_next],
        })

    return {
        "method": "C.马尔可夫",
        "as_of_period": rows[-1][0],
        "as_of_date": rows[-1][1],
        "total_periods": len(rows),
        "window": window,
        "matrix": matrix,
        "latest_tails": sorted(latest_tails),
        "predictions": predictions,
    }


# ════════════════════════════════════════════════════════════
# D. 同尾对预测 (Phase 3)
# ════════════════════════════════════════════════════════════
def predict_same_tail_pair(window=None):
    """
    D. 同尾对预测。
    1) 是否出现 ≥1 对同尾 (yes/no)
    2) 若出现, 最可能是哪个尾的同尾对 (基于历史频率)
    """
    rows = _slice(load_rows(), window)

    has_pair_count = 0
    pair_tails = Counter()  # 同尾对涉及的尾数
    for _, _, reds, _ in rows:
        tails = [r % 10 for r in reds]
        tc = Counter(tails)
        max_count = max(tc.values())
        if max_count >= 2:
            has_pair_count += 1
            for t, c in tc.items():
                if c >= 2:
                    pair_tails[t] += 1
    total = len(rows) or 1

    pair_rate = round(has_pair_count / total, 4)

    # 哪些尾数最常组成同尾对
    pair_tail_freq = []
    for t in range(10):
        c = pair_tails.get(t, 0)
        pair_tail_freq.append({
            "tail": t,
            "pair_count": c,
            "pct_of_pairs": round(c / max(has_pair_count, 1), 4),
        })
    pair_tail_freq.sort(key=lambda x: -x["pair_count"])

    # 上期/上上期是否同尾 → 下期预测
    # 简化: 用最近一期的同尾状态
    last_has_pair = max(Counter(r % 10 for r in rows[-1][2]).values()) >= 2 if rows else False

    return {
        "method": "D.同尾对",
        "as_of_period": rows[-1][0] if rows else None,
        "as_of_date": rows[-1][1] if rows else None,
        "total_periods": len(rows),
        "window": window,
        "pair_rate": pair_rate,  # 历史同尾对比例
        "pair_tail_freq": pair_tail_freq,  # 各尾数作为同尾对成员的频率
        "last_has_pair": last_has_pair,
        "top_pair_tails": [x["tail"] for x in pair_tail_freq[:3]],
    }


# ════════════════════════════════════════════════════════════
# E. 具体球号预测 (Phase 3)
# ════════════════════════════════════════════════════════════
def predict_balls(window=None, top_n=10):
    """
    E. 具体球号预测。
    综合: 缺口 (40%) + 频率 (40%) + 反向频率 (20%)
    输出 top_n 个具体球号。
    """
    rows = _slice(load_rows(), window)
    n_total = len(rows)

    # 每个球的缺口 (距上次出现的期数)
    ball_gaps = {}
    ball_last = {}
    for idx, (period, date, reds, blue) in enumerate(reversed(rows)):
        for b in reds:
            if b not in ball_last:
                ball_last[b] = idx
    for b in range(1, 34):
        ball_gaps[b] = ball_last.get(b, n_total)

    # 每个球的频率
    ball_freq = Counter()
    for _, _, reds, _ in rows:
        for r in reds:
            ball_freq[r] += 1
    max_freq = max(ball_freq.values()) if ball_freq else 1

    # 反向频率 (频率越低，加分) — 冷门球
    ball_cold = {}
    for b in range(1, 34):
        ball_cold[b] = (max_freq - ball_freq.get(b, 0)) / max_freq

    # 综合得分 (越大越推荐)
    scores = {}
    for b in range(1, 34):
        gap_score = ball_gaps[b] / n_total
        freq_score = ball_freq.get(b, 0) / max_freq
        cold_score = ball_cold[b]
        # 加权: 缺口 40% + 频率 40% + 冷门 20%
        scores[b] = round(gap_score * 0.4 + freq_score * 0.4 + cold_score * 0.2, 4)

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_n]

    return {
        "method": "E.球号",
        "as_of_period": rows[-1][0] if rows else None,
        "as_of_date": rows[-1][1] if rows else None,
        "total_periods": len(rows),
        "window": window,
        "ranked_balls": [{"ball": b, "score": s,
                          "gap": ball_gaps[b],
                          "freq": ball_freq.get(b, 0)} for b, s in ranked],
        "top_picks": [b for b, _ in ranked],
    }


# ════════════════════════════════════════════════════════════
# 综合 (一次性跑全部)
# ════════════════════════════════════════════════════════════
def predict_all(window=None):
    """一次性跑所有 5 种方法。返回 dict。"""
    return {
        "A": analyze_frequency(window=window),
        "B": predict_by_gap(window=window),
        "C": markov_transition(window=window),
        "D": predict_same_tail_pair(window=window),
        "E": predict_balls(window=window),
    }


# ════════════════════════════════════════════════════════════
# 格式化输出 (CLI)
# ════════════════════════════════════════════════════════════
def fmt_tail_table(pred):
    """生成可读的尾数缺口表（中文）。"""
    lines = []
    lines.append(f"📅 数据截至: {pred['as_of_period']} ({pred['as_of_date']})")
    lines.append(f"📊 总期数:   {pred['total_periods']}"
                 + (f" (窗口: 最近 {pred['window']} 期)" if pred.get('window') else ""))
    lines.append("")
    lines.append(f"{'尾数':<4} {'缺口':<6} {'最近出现':<14} {'候选球号 (按缺口降序)':<30}")
    lines.append("-" * 60)
    for t in pred["tails"]:
        tail_str = f"{t['tail']}"
        gap_str = f"{t['gap']}期"
        last_str = f"{t['last_period']}" if t.get('last_period') else "—"
        ball_str = " ".join(
            f"{b['ball']:02d}({b['gap']})" for b in t.get("ball_gaps", [])
        )
        lines.append(f"{tail_str:<4} {gap_str:<6} {last_str:<14} {ball_str:<30}")
    return "\n".join(lines)


def fmt_all(predictions):
    """格式化所有 5 种方法的输出。"""
    out = []
    out.append("=" * 70)
    out.append("📊 尾数预测 (5 种方法)")
    out.append("=" * 70)
    out.append("")

    # A. 频率
    a = predictions["A"]
    out.append("━━━ A. 尾数频率 ━━━")
    out.append(f"{'尾数':<4} {'次数':<6} {'占比':<8}")
    for t in a["tails"]:
        out.append(f"  {t['tail']:<3} {t['count']:<6} {t['pct']:.2%}")
    top_a = ' '.join('尾%d(%d)' % (p['tail'], p['count']) for p in a['top_picks'])
    out.append("🏆 Top 5: " + top_a)
    out.append("")

    # B. 缺口
    b = predictions["B"]
    out.append("━━━ B. 尾数缺口 (Phase 1) ━━━")
    out.append(fmt_tail_table(b))
    out.append("")

    # C. 马尔可夫
    c = predictions["C"]
    out.append("━━━ C. 马尔可夫转移 ━━━")
    out.append(f"最新期出现的尾数: {c['latest_tails']}")
    for pred in c["predictions"]:
        probs = " | ".join(f"尾{p['tail']}={p['prob']:.2f}" for p in pred["next_probs"])
        out.append(f"  上期尾 {pred['from_tail']} → 下期: {probs}")
    out.append("")

    # D. 同尾对
    d = predictions["D"]
    out.append("━━━ D. 同尾对 ━━━")
    out.append(f"历史同尾对比例: {d['pair_rate']:.2%}")
    out.append(f"上期是否有同尾: {'是' if d['last_has_pair'] else '否'}")
    out.append(f"最常出现同尾对的尾数: {d['top_pair_tails']}")
    out.append("")

    # E. 球号
    e = predictions["E"]
    out.append("━━━ E. 具体球号 (综合缺口+频率+冷门) ━━━")
    balls_str = " ".join(f"{b['ball']:02d}(分{b['score']:.2f},缺{b['gap']})" for b in e['ranked_balls'])
    out.append(f"Top {len(e['ranked_balls'])}: {balls_str}")
    out.append("")

    out.append("⚠️  所有方法均为结构化统计展示，请勿视为中奖保证。")
    return "\n".join(out)


# ════════════════════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════════════════════
def main():
    args = sys.argv[1:]
    window = None
    method = "all"  # 默认跑全部

    if "--window" in args:
        i = args.index("--window")
        if i + 1 < len(args):
            window = int(args[i + 1])
    if "--method" in args:
        i = args.index("--method")
        if i + 1 < len(args):
            method = args[i + 1].upper()  # A/B/C/D/E/all

    if method == "all":
        result = predict_all(window=window)
        if "--json" in args:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(fmt_all(result))
    elif method == "B":
        result = predict_by_gap(window=window)
        if "--json" in args:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(fmt_tail_table(result))
    elif method in ("A", "C", "D", "E"):
        fn = {"A": analyze_frequency, "C": markov_transition,
              "D": predict_same_tail_pair, "E": predict_balls}[method]
        result = fn(window=window)
        if "--json" in args:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()