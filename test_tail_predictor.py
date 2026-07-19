"""
尾数预测回归测试 — Phase 2 + 3d
覆盖 5 种预测方法 (A/B/C/D/E)
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

from fetcher import load_rows
from tail_predictor import (
    calc_tail_omission, analyze_frequency, markov_transition,
    predict_same_tail_pair, predict_balls,
)


def walk_forward_eval(rows, top_n=3, warmup=200, window=None, max_trials=None):
    """对 A/B/C 三种尾数预测方法做 walk-forward 评估。"""
    n = len(rows)
    start = max(warmup, 1)
    end = n - 1
    if max_trials:
        end = min(end, start + max_trials)
    if window:
        start = max(start, window + 1)

    trials = []
    for i in range(start, end):
        train = rows[:i]
        if window:
            train = train[-window:]

        # A. 频率
        a = analyze_frequency(window=len(train))
        a_top = set(p["tail"] for p in a["top_picks"][:top_n])

        # B. 缺口
        tail_data = calc_tail_omission(train)
        b_top = set(t["tail"] for t in tail_data[:top_n])

        # C. 马尔可夫: 用 train 最后一行作为上期
        # 简化: 把 train[-1] 替换为 train[:-1]，让 train[-2] 成为"上期"
        if len(train) >= 2:
            c = markov_transition(window=len(train))
            prev_tails = c.get("latest_tails", [])
            # 对每个 prev tail 取 top 2 next tail，合并为集合
            c_top = set()
            for pred in c.get("predictions", []):
                for x in pred["next_probs"][:2]:
                    c_top.add(x["tail"])
        else:
            c_top = set()

        # 随机基线
        random.seed(i)
        random_top = set(random.sample(range(10), top_n))

        # 实际
        actual_tails = set(r % 10 for r in rows[i][2])
        actual_has_pair = max(Counter(r % 10 for r in rows[i][2]).values()) >= 2

        # D. 同尾对预测
        d = predict_same_tail_pair(window=len(train))
        d_pred_pair = d["pair_rate"] > 0.5

        # E. 球号
        e = predict_balls(window=len(train), top_n=10)
        e_top = set(e["top_picks"])

        trials.append({
            "i": i,
            "period": rows[i][0],
            "actual": sorted(actual_tails),
            "actual_has_pair": actual_has_pair,
            # A/B/C 命中数
            "A_hits": len(a_top & actual_tails),
            "B_hits": len(b_top & actual_tails),
            "C_hits": len(c_top & actual_tails),
            "random_hits": len(random_top & actual_tails),
            # D 命中 (yes/no 正确)
            "D_correct": int(d_pred_pair == actual_has_pair),
            # E 球号命中数
            "E_hits": len(e_top & set(rows[i][2])),
            "E_total_balls": 6,  # 每期 6 红球
        })

    return trials


def summarize(trials, top_n):
    n = len(trials)
    if n == 0:
        return {}

    from math import comb
    expected_random_uniform = 1 - comb(10 - top_n, min(6, 10 - top_n)) / comb(10, min(6, 10)) if top_n <= 10 else 1.0

    return {
        "trials": n,
        "top_n": top_n,
        "any_hit_rate": {
            "A_freq":   round(sum(1 for t in trials if t["A_hits"] > 0) / n, 4),
            "B_gap":    round(sum(1 for t in trials if t["B_hits"] > 0) / n, 4),
            "C_markov": round(sum(1 for t in trials if t["C_hits"] > 0) / n, 4),
            "random":   round(sum(1 for t in trials if t["random_hits"] > 0) / n, 4),
            "expected_random_uniform": round(expected_random_uniform, 4),
        },
        "avg_hit_count": {
            "A_freq":   round(sum(t["A_hits"] for t in trials) / n, 3),
            "B_gap":    round(sum(t["B_hits"] for t in trials) / n, 3),
            "C_markov": round(sum(t["C_hits"] for t in trials) / n, 3),
            "random":   round(sum(t["random_hits"] for t in trials) / n, 3),
        },
        "D_pair_accuracy": round(sum(t["D_correct"] for t in trials) / n, 4),
        "E_ball_hit_rate": round(sum(t["E_hits"] for t in trials) / (n * trials[0]["E_total_balls"]), 4),
    }


def print_report(summaries, configs):
    print("=" * 72)
    print("📊 5 种方法回归测试报告 (3470 期 walk-forward)")
    print("=" * 72)
    print()

    for cfg, s in zip(configs, summaries):
        if not s:
            continue
        print(f"⚙️  top_n={cfg['top_n']}, window={cfg.get('window') or '全量'}, warmup={cfg['warmup']}")
        print(f"   测试期数: {s['trials']}")
        print()
        print(f"   {'方法':<14} {'至少命中1个比例':<18} {'平均命中数':<10}")
        print(f"   {'-'*50}")
        for m in ["A_freq", "B_gap", "C_markov", "random", "expected_random_uniform"]:
            r = s["any_hit_rate"].get(m, "—")
            avg = s["avg_hit_count"].get(m, "—")
            avg_str = f"{avg:.3f}" if isinstance(avg, (int, float)) else avg
            print(f"   {m:<14} {r:<18} {avg_str}")
        print()
        print(f"   D. 同尾对预测准确率: {s['D_pair_accuracy']:.2%}")
        print(f"   E. 球号命中率 (top 10 中 6 个红球命中比例): {s['E_ball_hit_rate']:.2%}")
        print()
        print("-" * 72)
        print()

    print("⚠️  注意:")
    print("  - 命中率接近均匀期望 ≈ 该方法无预测能力")
    print("  - 球号命中率理论上限 ≈ 10/33 × 6 ≈ 18.2%")
    print("  - 同尾对是 yes/no 问题，理论准确率上限 ≈ 80%+ (因历史比例 75-76%)")


def main():
    args = sys.argv[1:]
    top_n = 3
    window = None
    warmup = 200
    quick = "--quick" in args

    if "--top" in args:
        top_n = int(args[args.index("--top") + 1])
    if "--window" in args:
        window = int(args[args.index("--window") + 1])
    if "--warmup" in args:
        warmup = int(args[args.index("--warmup") + 1])

    print("⏳ 加载历史数据...")
    rows = load_rows()
    print(f"✅ 加载 {len(rows)} 期")

    max_trials = 500 if quick else None
    if quick:
        print(f"⚡ 快速模式: 仅测试 500 期\n")

    configs = [{"top_n": top_n, "window": window, "warmup": warmup}]
    if not quick:
        configs.append({"top_n": 5, "window": window, "warmup": warmup})
        configs.append({"top_n": 1, "window": window, "warmup": warmup})

    summaries = []
    for cfg in configs:
        print(f"⏳ 测试 top_n={cfg['top_n']}, window={cfg.get('window') or '全量'}...")
        trials = walk_forward_eval(rows, top_n=cfg["top_n"], warmup=cfg["warmup"],
                                   window=cfg["window"], max_trials=max_trials)
        summaries.append(summarize(trials, cfg["top_n"]))

    print()
    print_report(summaries, configs)

    if "--json" in args:
        out = Path(__file__).parent / "data" / "test_results.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump({"summaries": summaries, "configs": configs}, f,
                      ensure_ascii=False, indent=2)
        print(f"\n💾 已保存: {out}")


if __name__ == "__main__":
    main()