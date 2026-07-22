#!/bin/bash
# 双色球分析 HTML 自动更新脚本 v6
# 布局：左侧统计表格（近30期），右侧4个热力块（热码/温码/冷码/蓝球热码）
# 数据来源：
#   - 30 期明细: 17500.cn/chart/ssq-tjb.html
#   - 全量历史 (Phase 1+): data.17500.cn/ssq_asc.txt (3470+ 期)
# 冷热图：BeautifulSoup 精确解析 + 中奖号码按类别着色
# 尾数预测 (Phase 1)：fetcher.py + tail_predictor.py
#
# v6 新增（自动 GitHub 推送）：
#   - HTML 生成后自动 cp 到 index.html（GitHub Pages 入口）
#   - 自动 git add / commit / push 到 origin/main
#   - SSH 推送，无需交互
#   - 若 index.html 实际无变化（数据未更新）跳过 commit，避免空提交
#
# 主逻辑统一在 ssq_analysis.py 中，本脚本只负责调用、日志、发布。

set -e

HTML_FILE="/Users/teld_hsh/github/ssq/ssq_analysis.html"
INDEX_FILE="/Users/teld_hsh/github/ssq/index.html"
LOG_FILE="/Users/teld_hsh/github/ssq/update.log"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GIT_REMOTE="origin"
GIT_BRANCH="main"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "========== 开始更新 =========="

# ── 1. 刷新全量历史缓存 (Phase 1: 3470 期, 用于尾数缺口预测) ──
cd "$SCRIPT_DIR"
log "[1/3] 刷新全量历史..."
if python3 fetcher.py >> "$LOG_FILE" 2>&1; then
    log "✅ 历史缓存已更新"
else
    log "⚠️ fetcher.py 失败 (继续运行 HTML 更新)"
fi

# ── 2. 生成 HTML (主脚本在 ssq_analysis.py) ──
log "[2/3] 生成 HTML..."
if python3 ssq_analysis.py >> "$LOG_FILE" 2>&1; then
    log "✅ HTML 已生成: $HTML_FILE"
else
    log "❌ HTML 生成失败，终止 (不推送)"
    exit 1
fi

# ── 3. 同步到 GitHub ──
log "[3/3] 同步到 GitHub..."

# 3.1 把最新 HTML 复制为 index.html（GitHub Pages 入口）
cp "$HTML_FILE" "$INDEX_FILE"
log "✅ cp $HTML_FILE -> $INDEX_FILE"

# 3.2 git add (只追踪脚本已知的关键文件)
cd "$SCRIPT_DIR"
git add ssq_analysis.html index.html data/ 2>>"$LOG_FILE" || log "⚠️ git add 部分失败"

# 3.3 检查是否有变化
if git diff --cached --quiet; then
    log "ℹ️ 无变化（数据未更新），跳过 commit/push"
    log "========== 完成 (无推送) =========="
    exit 0
fi

# 3.4 commit
COMMIT_MSG="auto: SSQ 更新 $(date '+%Y-%m-%d %H:%M:%S')"
if git commit -m "$COMMIT_MSG" >> "$LOG_FILE" 2>&1; then
    log "✅ git commit: $COMMIT_MSG"
else
    log "❌ git commit 失败"
    exit 1
fi

# 3.5 push (SSH 推送，cron 环境需提前配好 ssh-agent / key)
if git push "$GIT_REMOTE" "$GIT_BRANCH" >> "$LOG_FILE" 2>&1; then
    log "✅ git push $GIT_REMOTE/$GIT_BRANCH"
else
    log "❌ git push 失败 (commit 已留在本地)"
    exit 1
fi

log "========== 完成 ✅ =========="