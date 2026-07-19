#!/bin/bash
# 双色球分析 HTML 自动更新脚本 v5
# 布局：左侧统计表格（近30期），右侧4个热力块（热码/温码/冷码/蓝球热码）
# 数据来源：
#   - 30 期明细: 17500.cn/chart/ssq-tjb.html
#   - 全量历史 (Phase 1+): data.17500.cn/ssq_asc.txt (3470+ 期)
# 冷热图：BeautifulSoup 精确解析 + 中奖号码按类别着色
# 尾数预测 (Phase 1)：fetcher.py + tail_predictor.py
#
# 注: 主逻辑统一在 ssq_analysis.py 中，本脚本只负责调用和日志。

set -e

HTML_FILE="/Users/teld_hsh/github/ssq/ssq_analysis.html"
LOG_FILE="/Users/teld_hsh/github/ssq/update.log"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始更新..." >> "$LOG_FILE"

# ── 1. 刷新全量历史缓存 (Phase 1: 3470 期, 用于尾数缺口预测) ──
cd "$SCRIPT_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [1/2] 刷新全量历史..." >> "$LOG_FILE"
if python3 fetcher.py >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 历史缓存已更新" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ fetcher.py 失败 (继续运行 HTML 更新)" >> "$LOG_FILE"
fi

# ── 2. 生成 HTML (主脚本在 ssq_analysis.py) ──
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [2/2] 生成 HTML..." >> "$LOG_FILE"
if python3 ssq_analysis.py >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ HTML 已更新: $HTML_FILE" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ HTML 生成失败" >> "$LOG_FILE"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 完成。" >> "$LOG_FILE"