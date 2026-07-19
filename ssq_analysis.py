#!/usr/bin/env python3
# 双色球分析 HTML 自动更新脚本
# 修复：移除 v="ball" 错误过滤，保留5个标记行
# 新增：点击冷热图表格单元格高亮（统一红色 #e94560）

import urllib.request
import re
from datetime import datetime

try:
    from bs4 import BeautifulSoup
    USE_BS4 = True
except ImportError:
    USE_BS4 = False
    print("WARNING: BeautifulSoup not available, using regex fallback")

COLOR_HOT  = '#e94560'
COLOR_WARM = '#2196f3'
COLOR_COLD = '#ff9800'
COLOR_BALL = '#888888'

# ── 抓取开奖数据 ─────────────────────────────────────────
url = 'https://www.17500.cn/chart/ssq-tjb.html'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})
with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode('utf-8')

html_clean = html.replace('\r\n', '').replace('\n', '')
trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_clean, re.DOTALL)
tds_pat = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
a_pat = re.compile(r'<a[^>]*>(.*?)</a>', re.DOTALL)

records = []
for tr in trs:
    tds = tds_pat.findall(tr)
    if len(tds) >= 3:
        pm = a_pat.search(tds[0])
        if pm and pm.group(1).isdigit() and len(pm.group(1)) == 7:
            red_raw = re.sub(r'<[^>]+>', '', tds[1]).strip()
            blue_raw = re.sub(r'<[^>]+>', '', tds[2]).strip()
            records.append({
                'period': pm.group(1),
                'red': [b for b in red_raw.split() if b],
                'blue': blue_raw
            })

records.reverse()
records = records[:30]

# ── 冷热图表格 ───────────────────────────────────────────
lengre_url = 'https://www.17500.cn/chart/ssq-lengre.html'
lengre_req = urllib.request.Request(lengre_url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})
with urllib.request.urlopen(lengre_req, timeout=15) as resp:
    lengre_html = resp.read().decode('utf-8')

period_winning = {}
for rec in records:
    try:
        period_winning[rec['period']] = {
            'red': set(int(b) for b in rec['red']),
            'blue': int(rec['blue'])
        }
    except:
        pass

lengre_table = ''

if USE_BS4:
    soup = BeautifulSoup(lengre_html, 'html.parser')
    table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        if len(rows) >= 3:
            header0 = str(rows[0])
            header1 = str(rows[1])
            # 正确的 table 结构：<thead>包裹表头，<tbody>包裹数据
            thead_html = '<thead>' + header0 + header1 + '</thead>'
            tbody_html = '<tbody>'
            data_count = 0
            for row in rows[2:]:
                # 修复：不过滤 v="ball" 行（保留5个标记行）
                cells = row.find_all(['td', 'th'])
                if len(cells) < 36:
                    continue
                period_text = cells[0].get_text(strip=True)
                is_marker = (period_text == '标记行')

                # 标记行：直接保留原样，不过击中奖着色
                if is_marker:
                    # 原始 cells[0]=<td colspan=2>标记行</td> 占据2列，
                    # 所以 cells[1] 实际是第一个红球（列3位置），
                    # 需要插入空 td 占位奖号列（列2位置）
                    row_html = '<tr>'
                    row_html += '<td style="color:#e94560;font-weight:bold;">' + period_text + '</td>'
                    row_html += '<td></td>'  # 占位：奖号列（columns[1]）
                    # cells[1] 是第一个红球（因为 colspan=2 跳过了1列），
                    # 取纯文本即可（不保留 td 结构，避免双层嵌套）
                    row_html += '<td>' + cells[1].get_text(strip=True) + '</td>'
                    # cells[2:] 已是完整 <td> 元素，直接拼接
                    for c in cells[2:]:
                        row_html += str(c)
                    row_html += '</tr>'
                    tbody_html += row_html
                    continue

                # 数据行：检查完整性和中奖着色
                if not re.match(r'^\d{7}$', period_text):
                    continue
                # 从 cells[1] 文本解析中奖号码（如 "11 15 17 22 25 30+07"）
                try:
                    cell1_text = cells[1].get_text(strip=True)
                    parts = cell1_text.split('+')
                    winning_red = set(int(b) for b in parts[0].split())
                    winning_blue = int(parts[1].strip()) if len(parts) > 1 else 0
                except:
                    continue

                def get_ball_color(ball_num, zone):
                    if zone == 'blue':
                        is_win = (ball_num == winning_blue)
                        return COLOR_HOT if is_win else COLOR_BALL
                    else:
                        is_win = (ball_num in winning_red)
                        if not is_win:
                            return COLOR_BALL
                        if zone == 'hot':   return COLOR_HOT
                        if zone == 'warm':  return COLOR_WARM
                        if zone == 'cold':  return COLOR_COLD
                        return COLOR_BALL

                def colorize_cell(cell, zone, winning_set):
                    """对格子内容着色：文本是数字时着色"""
                    txt = cell.get_text(strip=True)
                    if not txt:
                        return txt
                    try:
                        ball_num = int(txt)
                        is_win = (ball_num in winning_set)
                        if not is_win:
                            return txt
                        if zone == 'hot':   color = COLOR_HOT
                        elif zone == 'warm':  color = COLOR_WARM
                        elif zone == 'cold':  color = COLOR_COLD
                        else:               color = COLOR_HOT  # blue win
                        return '<span style="color:%s;font-weight:bold;font-size:12px;">%s</span>' % (color, txt)
                    except:
                        return txt

                row_html = '<tr>'
                row_html += '<td style="color:#e94560;font-weight:bold;">' + period_text + '</td>'
                row_html += '<td>' + cells[1].get_text(strip=True) + '</td>'
                for c in cells[2:13]:
                    row_html += '<td>' + colorize_cell(c, 'hot', winning_red) + '</td>'
                for c in cells[13:24]:
                    row_html += '<td>' + colorize_cell(c, 'warm', winning_red) + '</td>'
                for c in cells[24:35]:
                    row_html += '<td>' + colorize_cell(c, 'cold', winning_red) + '</td>'
                row_html += '<td>' + cells[35].get_text(strip=True) + '</td>'
                for c in cells[36:44]:
                    row_html += '<td>' + colorize_cell(c, 'blue', {winning_blue}) + '</td>'
                for c in cells[44:52]:
                    row_html += '<td>' + colorize_cell(c, 'blue', {winning_blue}) + '</td>'
                row_html += '</tr>'
                tbody_html += row_html
                data_count += 1

            tbody_html += '</tbody>'
            # 修复：lengre_table 只需要 thead + tbody，不包含外层 <table> 标签
            # 外层 <table class="lengre-table"> 由模板提供
            lengre_table = thead_html + tbody_html
            print("DEBUG: BS4 extracted", data_count, "data rows + 5 marker rows")
else:
    table_match = re.search(r'(<table.*?</table>)', lengre_html, re.DOTALL)
    if table_match:
        lengre_table = table_match.group(1)
        lengre_table = re.sub(r'^<table[^>]*>', '', lengre_table)
        lengre_table = re.sub(r'</table>\s*$', '', lengre_table)

latest = records[0]
year, seq = latest['period'][:4], latest['period'][4:]

# ─── 基础统计 ─────────────────────────────────────────────
red_count  = {i: 0 for i in range(1, 34)}
blue_count = {i: 0 for i in range(1, 17)}
miss_counter  = {i: 0 for i in range(1, 34)}
miss_counter_b = {i: 0 for i in range(1, 17)}
red_miss   = {i: 0 for i in range(1, 34)}
blue_miss  = {i: 0 for i in range(1, 17)}

for rec in records:
    for b in rec['red']:
        try: red_count[int(b)] += 1
        except: pass
    try: blue_count[int(rec['blue'])] += 1
    except: pass

for rec in records:
    for b in range(1, 34): miss_counter[b] += 1
    for b in range(1, 17): miss_counter_b[b] += 1
    for b in rec['red']:
        try: red_miss[int(b)] = miss_counter[int(b)]
        except: pass
    try: blue_miss[int(rec['blue'])] = miss_counter_b[int(rec['blue'])]
    except: pass

# ─── 连号/同尾计算 ────────────────────────────────────────
def calc_stats(rec):
    balls = sorted(int(b) for b in rec['red'])
    total = sum(balls)
    q = [0, 0, 0]
    for b in balls:
        if b <= 11: q[0] += 1
        elif b <= 22: q[1] += 1
        else: q[2] += 1
    sanqu = "%d:%d:%d" % (q[0], q[1], q[2])
    diffs = sorted(set(balls[j]-balls[i] for i in range(len(balls)) for j in range(i+1, len(balls))))
    ac = len(diffs)
    jiju = balls[-1] - balls[0]
    chains = []
    i = 0
    while i < len(balls):
        j = i
        while j+1 < len(balls) and balls[j+1] == balls[j]+1: j += 1
        if j - i + 1 >= 2:
            chains.append("%d-%d" % (balls[i], balls[j]))
        i = j + 1
    lian_type = "%d个%d连" % (len(chains), len(chains[0].split('-')) if chains else 0) if chains else "无"
    lian_val  = "; ".join(chains) if chains else "-"
    tails = {}
    for b in balls:
        t = b % 10
        tails[t] = tails.get(t, [])
        tails[t].append(b)
    same_tail = [(t, vs) for t, vs in tails.items() if len(vs) >= 2]
    tail_type = "%d对同尾" % len(same_tail) if same_tail else "无"
    tail_val  = "; ".join("%d-%d" % (vs[0], vs[-1]) for _, vs in same_tail) if same_tail else "-"
    return {'total': total, 'sanqu': sanqu, 'ac': ac, 'jiju': jiju,
            'lian_type': lian_type, 'lian_val': lian_val,
            'tail_type': tail_type, 'tail_val': tail_val}

# ─── 热温冷码分组 ────────────────────────────────────────
hot_sorted = sorted(red_count.items(), key=lambda x: -x[1])
hot_sorted_b = sorted(blue_count.items(), key=lambda x: -x[1])
avg_r = sum(red_count.values()) / 33.0 if red_count else 0
hot_balls  = [b for b, c in hot_sorted if c >= avg_r * 1.5][:11]
warm_balls = [b for b, c in hot_sorted if avg_r * 0.8 <= c < avg_r * 1.5][:11]
cold_balls = [b for b, c in sorted(red_count.items(), key=lambda x: x[1]) if c <= avg_r * 0.4][:11]

def unique_balls(ball_list, all_balls_dict):
    seen = set()
    result = []
    for b in ball_list:
        if b not in seen:
            seen.add(b)
            result.append((b, all_balls_dict.get(b, 0)))
    return result

def render_ball_list(items, is_blue=False, max_show=33):
    html_parts = []
    for b, c in items[:max_show]:
        size = max(10, min(20, 8 + c * 3)) if not is_blue else max(10, min(18, 8 + c * 3))
        color = '#e94560' if not is_blue else '#4a90d9'
        w = h = int(size * 2)
        html_parts.append(
            '<span style="display:inline-block;width:%dpx;height:%dpx;'
            'background:%s;color:#fff;border-radius:50%%;text-align:center;'
            'line-height:%dpx;font-size:%dpx;font-weight:bold;margin:2px;">%d</span>'
            % (w, h, color, w, size, b)
        )
    return ''.join(html_parts)

hot_html  = render_ball_list(unique_balls(hot_balls,  dict(red_count)), False)
warm_html = render_ball_list(unique_balls(warm_balls, dict(red_count)), False)
cold_html = render_ball_list(unique_balls(cold_balls, dict(red_count)), False)
hots_b_html = render_ball_list([(b, c) for b, c in hot_sorted_b], True)

# ─── 尾数预测（Phase 1+3: 5 种方法 A/B/C/D/E）──────────────────
try:
    from tail_predictor import (
        predict_by_gap, analyze_frequency, markov_transition,
        predict_same_tail_pair, predict_balls
    )

    # ── B. 缺口 (Phase 1) ──
    _b = predict_by_gap()
    _tail_cells_html = ''
    for _t in _b['tails']:
        _gap = _t['gap']
        if _gap >= 5:   _cls = 'gap-high'
        elif _gap >= 2: _cls = 'gap-mid'
        else:           _cls = 'gap-low'
        _balls_html = ' '.join(
            ('<b>%02d</b>(%d)' % (b['ball'], b['gap'])) if i < 2 else '%02d(%d)' % (b['ball'], b['gap'])
            for i, b in enumerate(_t['ball_gaps'])
        )
        _latest_mark = ' ✓' if _t['present_in_latest'] else ''
        _tail_cells_html += (
            '<div class="tail-cell %s">'
            '<div class="tail-num">%d%s</div>'
            '<div class="gap-num">缺口 %d 期</div>'
            '<div class="ball-list">%s</div>'
            '</div>'
        ) % (_cls, _t['tail'], _latest_mark, _gap, _balls_html)
    _b_picks = ' &nbsp;|&nbsp; '.join(
        '<b>尾 %d</b>(缺 %d) → %s' % (p['tail'], p['tail_gap'],
            ', '.join('%02d' % b for b in p['candidate_balls']))
        for p in _b['top_picks']
    )

    # ── A. 频率 ──
    _a = analyze_frequency()
    _max_a_count = max(t['count'] for t in _a['tails']) or 1
    _a_rows = ''
    for _t in _a['tails']:
        _bar_w = int(_t['count'] / _max_a_count * 80)
        _a_rows += (
            '<tr><td style="text-align:right;font-weight:bold;color:#d32f2f;">尾 %d</td>'
            '<td style="text-align:right;">%d</td>'
            '<td style="text-align:right;color:#555;">%.2f%%</td>'
            '<td><span class="freq-bar" style="width:%dpx;"></span></td></tr>'
        ) % (_t['tail'], _t['count'], _t['pct']*100, _bar_w)

    # ── C. 马尔可夫 ──
    _c = markov_transition()
    # 找出每个 current tail 的 top 1 next tail 用于热力显示
    _c_matrix_html = '<tr><th>上期尾</th>' + ''.join('<th>%d</th>' % n for n in range(10)) + '</tr>'
    for _c_curr in range(10):
        _row_cells = '<th>尾 %d</th>' % _c_curr
        for _c_next in range(10):
            _v = _c['matrix'].get(_c_curr, {}).get(_c_next, 0)
            _row_cells += '<td>%s%.2f</td>' % ('<b>' if _v >= 0.13 else '', _v)
        _c_matrix_html += '<tr>' + _row_cells + '</tr>'
    _c_pred_html = ''
    for _p in _c['predictions']:
        _probs = ' '.join('尾%d=%.2f' % (x['tail'], x['prob']) for x in _p['next_probs'])
        _c_pred_html += '<div style="font-size:0.75rem;margin:2px 0;"><b>尾 %d</b> → %s</div>' % (_p['from_tail'], _probs)

    # ── D. 同尾对 ──
    _d = predict_same_tail_pair()
    _d_rows = ''
    for _t in _d['pair_tail_freq'][:5]:
        _d_rows += (
            '<tr><td style="font-weight:bold;color:#d32f2f;">尾 %d</td>'
            '<td style="text-align:right;">%d 次</td>'
            '<td style="text-align:right;color:#555;">%.1f%%</td></tr>'
        ) % (_t['tail'], _t['pair_count'], _t['pct_of_pairs']*100)

    # ── E. 球号 ──
    _e = predict_balls()
    _e_balls_html = ''
    for _b_item in _e['ranked_balls']:
        _e_balls_html += (
            '<div class="ball-pick" title="得分 %.2f  缺口 %d  频次 %d">'
            '%02d<span class="sub">%d</span></div>'
        ) % (_b_item['score'], _b_item['gap'], _b_item['freq'],
             _b_item['ball'], _b_item['gap'])

    tail_pred_panel = (
        '<div class="tail-prediction-section">'
        '<div class="tail-pred-header">'
        '<span>🎯 尾数预测 (5 种方法 — 基于 %d 期全量历史)</span>'
        '<span class="meta">截至 %s 期 (%s)</span>'
        '</div>'
        '<div class="tail-pred-body">'

        # B. 缺口
        '<div class="tail-method-block">'
        '<div class="tail-method-title">📍 B. 尾数缺口</div>'
        '<div class="tail-pred-grid">%s</div>'
        '<div class="tail-picks">🏆 Top 5 候选: %s</div>'
        '</div>'

        # A. 频率
        '<div class="tail-method-block">'
        '<div class="tail-method-title">📊 A. 尾数频率 (历史出现次数)</div>'
        '<table style="width:100%%;border-collapse:collapse;font-size:0.78rem;">'
        '<thead><tr style="background:#f0f0f0;"><th>尾数</th><th>次数</th><th>占比</th><th>分布</th></tr></thead>'
        '<tbody>%s</tbody></table>'
        '</div>'

        # C. 马尔可夫
        '<div class="tail-method-block">'
        '<div class="tail-method-title">🔀 C. 马尔可夫转移 (上一期尾 → 下一期尾)</div>'
        '<div style="overflow-x:auto;"><table class="markov-table">%s</table></div>'
        '<div style="margin-top:6px;"><b>针对最新期 %s 出现的尾数:</b>%s</div>'
        '</div>'

        # D. 同尾对
        '<div class="tail-method-block">'
        '<div class="tail-method-title">👯 D. 同尾对预测</div>'
        '<div style="font-size:0.78rem;margin-bottom:6px;">'
        '历史同尾对比例: <b style="color:#d32f2f;">%.1f%%</b> | '
        '上期是否有同尾: <b>%s</b>'
        '</div>'
        '<div style="font-size:0.78rem;margin-bottom:4px;"><b>最常出现同尾对的尾数 (top 5):</b></div>'
        '<table style="width:auto;border-collapse:collapse;font-size:0.78rem;">'
        '<thead><tr style="background:#f0f0f0;"><th>尾数</th><th>次数</th><th>占同尾期比例</th></tr></thead>'
        '<tbody>%s</tbody></table>'
        '<div class="tail-picks" style="margin-top:6px;">🎯 预测下一期同尾对最可能涉及的尾: <b>%s</b></div>'
        '</div>'

        # E. 球号
        '<div class="tail-method-block">'
        '<div class="tail-method-title">🎱 E. 具体球号推荐 (综合缺口+频率+冷门)</div>'
        '<div class="ball-pick-row">%s</div>'
        '<div style="font-size:0.7rem;color:#888;margin-top:6px;">'
        '鼠标悬停看分数构成 (gap/freq)。下标=缺口期数。'
        '</div>'
        '</div>'

        '<div style="font-size:0.7rem;color:#888;margin-top:10px;padding-top:8px;border-top:1px solid #ddd;">'
        '⚠️ 5 种方法均为结构化统计展示。Phase 2 回测显示：所有方法的长期命中率受概率上限约束。'
        '本面板作为多信号辅助决策的一部分，请勿视为中奖保证。'
        '</div></div></div>'
    ) % (
        _b['total_periods'], _b['as_of_period'], _b['as_of_date'],
        _tail_cells_html, _b_picks,
        _a_rows,
        _c_matrix_html, _c['as_of_period'], _c_pred_html,
        _d['pair_rate']*100, '是' if _d['last_has_pair'] else '否',
        _d_rows, ', '.join('尾%d' % t for t in _d['top_pair_tails']),
        _e_balls_html,
    )
except Exception as _e:
    import traceback
    tail_pred_panel = (
        '<div class="tail-prediction-section"><div class="tail-pred-header">'
        '<span>🎯 尾数预测 (未运行)</span></div>'
        '<div class="tail-pred-body" style="color:#888;font-size:0.78rem;">'
        '需要先运行 <code>python3 fetcher.py</code> 生成历史缓存。'
        '<br>错误: %s'
        '</div></div>'
    ) % (str(_e) + '<br>' + traceback.format_exc().replace('\n', '<br>'))

# ─── 最新一期 ────────────────────────────────────────────
def ball_span(num, t='red'):
    c = '#e94560' if t == 'red' else '#4a90d9'
    return ('<span style="background:%s;color:#fff;border-radius:50%%;'
            'width:26px;height:26px;display:inline-flex;align-items:center;'
            'justify-content:center;font-weight:bold;font-size:0.8rem;margin:1px;">%d</span>'
            % (c, num))

red_html  = ''.join(ball_span(int(b), 'red')  for b in latest['red'])
blue_html = ball_span(int(latest['blue']), 'blue')

# ─── 左侧表格 ────────────────────────────────────────────
table_rows = ''
for rec in records:
    y, s = rec['period'][:4], rec['period'][4:]
    sd = calc_stats(rec)
    reds_str = ' '.join(
        '<span style="background:#e94560;color:#fff;border-radius:50%%;'
        'width:20px;height:20px;display:inline-flex;align-items:center;'
        'justify-content:center;font-size:0.7rem;margin:1px;">%s</span>' % b
        for b in rec['red']
    )
    blue_str = ('<span style="background:#4a90d9;color:#fff;border-radius:50%%;'
                'width:20px;height:20px;display:inline-flex;align-items:center;'
                'justify-content:center;font-size:0.7rem;margin:1px;">%s</span>' % rec['blue'])
    table_rows += '<tr><td style="color:#e94560;white-space:nowrap;font-weight:bold;">%s-%s</td>' % (y, s)
    table_rows += '<td style="white-space:nowrap;">%s%s</td>' % (reds_str, blue_str)
    table_rows += '<td style="text-align:center;color:#e94560;font-weight:bold;">%d</td>' % sd['total']
    table_rows += '<td style="text-align:center;color:#555;">%s</td>' % sd['sanqu']
    table_rows += '<td style="text-align:center;color:#555;">%d</td>' % sd['ac']
    table_rows += '<td style="text-align:center;color:#555;">%d</td>' % sd['jiju']
    table_rows += '<td style="text-align:center;color:#888;font-size:0.78rem;">%s</td>' % sd['lian_type']
    table_rows += '<td style="text-align:center;color:#888;font-size:0.78rem;">%s</td>' % sd['lian_val']
    table_rows += '<td style="text-align:center;color:#888;font-size:0.78rem;">%s</td>' % sd['tail_type']
    table_rows += '<td style="text-align:center;color:#888;font-size:0.78rem;">%s</td></tr>' % sd['tail_val']

# ─── 完整 HTML ────────────────────────────────────────────
# JS 代码（纯字符串，不用 f-string 避免 {} 冲突）
TOGGLE_JS = """
function toggleCell(td) {
    if (td.classList.contains('selected-cell')) {
        td.classList.remove('selected-cell');
        td.style.background = '';
        td.style.color = '';
    } else {
        td.classList.add('selected-cell');
        td.style.background = '#e94560';
        td.style.color = '#fff';
    }
}
document.querySelectorAll('.lengre-table td').forEach(function(td) {
    td.style.cursor = 'pointer';
    td.title = '点击选中/取消';
    td.addEventListener('click', function() { toggleCell(this); });
});
"""

DRAW_JS = """
const drawState = {};
let activeBlock = 'hot';
function getCanvas(id) { return document.getElementById('draw-' + id); }
function getCtx(id) { return getCanvas(id).getContext('2d'); }
function initDraw(id) {
  const canvas = getCanvas(id);
  if (!canvas) return;
  const ctx = getCtx(id);
  let isDrawing = false, lastX = 0, lastY = 0;
  const syncSize = function() {
    const wrap = document.getElementById('wrap-' + id) || canvas.parentElement;
    if (wrap) { canvas.width = wrap.offsetWidth; canvas.height = wrap.offsetHeight; }
  };
  setTimeout(syncSize, 100);
  window.addEventListener('resize', syncSize);
  function saveState() {
    if (!drawState[id]) drawState[id] = [];
    drawState[id].push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    if (drawState[id].length > 30) drawState[id].shift();
  }
  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  }
  canvas.addEventListener('mousedown', function(e) {
    if (activeBlock !== id) return;
    isDrawing = true;
    var p = getPos(e); lastX = p.x; lastY = p.y;
    saveState();
  });
  canvas.addEventListener('mousemove', function(e) {
    if (!isDrawing || activeBlock !== id) return;
    var p = getPos(e);
    ctx.beginPath(); ctx.moveTo(lastX, lastY); ctx.lineTo(p.x, p.y);
    ctx.strokeStyle = document.getElementById('color-' + id).value;
    ctx.lineWidth = parseInt(document.getElementById('size-' + id).value);
    ctx.lineCap = 'round';
    ctx.stroke();
    lastX = p.x; lastY = p.y;
  });
  canvas.addEventListener('mouseup', function() { isDrawing = false; });
  canvas.addEventListener('mouseleave', function() { isDrawing = false; });
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && activeBlock === id) {
      if (drawState[id] && drawState[id].length > 0)
        ctx.putImageData(drawState[id].pop(), 0, 0);
    }
  });
}
function switchBlock(id) { activeBlock = id; }
function clearDraw(id) {
  const canvas = getCanvas(id);
  if (!canvas) return;
  const ctx = getCtx(id);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawState[id] = [];
}
initDraw('hot');
initDraw('warm');
initDraw('cold');
initDraw('hotb');
initDraw('lengre');
function syncLengreSize() {
  const c = document.getElementById('draw-lengre');
  const w = document.getElementById('wrap-lengre');
  if (c && w) { c.width = w.offsetWidth; c.height = w.offsetHeight; }
}
window.addEventListener('resize', syncLengreSize);
setTimeout(syncLengreSize, 200);
"""

CSS_EXTRA = """
  .selected-cell {
    background: #e94560 !important;
    color: #fff !important;
    border-radius: 4px;
  }
"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SSQ 分析 - 双色球</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #ffffff; color: #222; padding: 16px; }
h1 { font-size: 1.2rem; color: #e94560; margin-bottom: 12px; }
h3 { font-size: 0.85rem; color: #e94560; margin-bottom: 8px; }
.latest-card { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.latest-card .period { color: #e94560; font-size: 1.1rem; font-weight: bold; margin-bottom: 8px; }
.latest-card .balls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.latest-card .label { color: #666; font-size: 0.85rem; }
.main-grid { display: grid; grid-template-columns: 1fr 340px; gap: 14px; margin-bottom: 14px; }
.stat-table-wrap { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
.stat-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.stat-table th { background: #e94560; color: #fff; padding: 8px 10px; text-align: center; white-space: nowrap; font-size: 0.78rem; }
.stat-table td { padding: 7px 10px; text-align: center; border-bottom: 1px solid #ddd; color: #333; }
.stat-table tr:last-child td { border-bottom: none; }
.stat-table tr:hover td { background: #f0f0f0; }
.heat-sidebar { display: flex; flex-direction: column; gap: 10px; }
.heat-block { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; position: relative; }
.heat-block canvas.draw-canvas { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; cursor: crosshair; z-index: 5; }
.heat-label { font-size: 0.8rem; color: #e94560; margin-bottom: 8px; font-weight: bold; }
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
.chart-frame { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
.chart-frame h3 { font-size: 0.85rem; padding: 8px 12px; background: #e94560; color: #fff; }
.chart-toolbar { padding: 6px 10px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; border-top: 1px solid #ddd; }
.chart-toolbar button { padding: 3px 8px; border: 1px solid #ccc; border-radius: 4px; background: #fff; color: #333; cursor: pointer; font-size: 0.72rem; }
.chart-toolbar button:hover { background: #e94560; color: #fff; border-color: #e94560; }
.chart-toolbar input[type="color"] { width: 24px; height: 24px; border: 1px solid #ccc; cursor: pointer; }
.chart-toolbar input[type="range"] { width: 60px; }
iframe { width: 100%; height: 480px; border: none; }
.sources { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
.sources ul { list-style: none; }
.sources li { margin-bottom: 4px; }
.sources a { color: #e94560; text-decoration: none; font-size: 0.8rem; }
.sources a:hover { text-decoration: underline; }
.updated { color: #888; font-size: 0.75rem; text-align: right; margin-top: 10px; }
.lengre-section { background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 14px; overflow: hidden; }
.lengre-header { padding: 8px 12px; background: #e94560; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.lengre-header span { color: #fff; font-size: 0.85rem; font-weight: bold; }
.lengre-header input[type="range"] { width: 55px; }
.lengre-header button { padding: 3px 8px; border: 1px solid rgba(255,255,255,0.6); border-radius: 4px; background: rgba(255,255,255,0.15); color: #fff; cursor: pointer; font-size: 0.72rem; }

/* 尾数预测面板 */
.tail-prediction-section { background: #f0f7ff; border: 1px solid #b3d4fc; border-radius: 8px; margin-bottom: 14px; overflow: hidden; }
.tail-pred-header { padding: 8px 12px; background: #1976d2; color: #fff; font-size: 0.85rem; font-weight: bold; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.tail-pred-header .meta { font-size: 0.72rem; opacity: 0.85; font-weight: normal; }
.tail-pred-body { padding: 12px; }
.tail-pred-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.tail-cell { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 8px 6px; text-align: center; font-size: 0.78rem; }
.tail-cell.gap-high { background: #ffe0e0; border-color: #e57373; }
.tail-cell.gap-mid { background: #fff8e0; border-color: #ffb74d; }
.tail-cell.gap-low { background: #e8f5e9; border-color: #81c784; }
.tail-cell .tail-num { font-size: 1.4rem; font-weight: bold; color: #d32f2f; line-height: 1; }
.tail-cell .gap-num { font-size: 0.85rem; color: #555; margin: 4px 0; }
.tail-cell .ball-list { font-size: 0.72rem; color: #444; line-height: 1.4; }
.tail-cell .ball-list b { color: #d32f2f; }
.tail-picks { background: #fffbe6; border: 1px dashed #ffa000; border-radius: 6px; padding: 8px 10px; margin-top: 10px; font-size: 0.8rem; }
.tail-picks b { color: #d32f2f; }

/* Phase 3 新增面板 */
.tail-method-block { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #b3d4fc; }
.tail-method-title { font-size: 0.82rem; font-weight: bold; color: #1976d2; margin-bottom: 6px; }
.freq-bar { display: inline-block; height: 8px; background: #e94560; border-radius: 2px; vertical-align: middle; margin-left: 4px; }
.markov-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.markov-table th, .markov-table td { padding: 4px 6px; text-align: center; border: 1px solid #ddd; }
.markov-table th { background: #e3f2fd; color: #1976d2; }
.markov-table td.hot { background: #fff3e0; font-weight: bold; }
.ball-pick-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ball-pick { background: #fff; border: 2px solid #e94560; color: #d32f2f; border-radius: 50%; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.85rem; }
.ball-pick .sub { font-size: 0.55rem; color: #888; display: block; line-height: 0.9; }
.lengre-header button:hover { background: rgba(255,255,255,0.3); }
.wrap-lengre { position: relative; width: 100%; min-width: 900px; max-height: 600px; overflow: auto; }
.lengre-table { border-collapse: collapse; width: 100%; font-size: 0.72rem; white-space: nowrap; }
.lengre-table th { background: #e94560; color: #fff; padding: 5px 6px; position: sticky; top: 0; z-index: 5; }
.lengre-table td { padding: 4px 5px; text-align: center; border: 1px solid #ddd; color: #888; }
.lengre-table tr:hover td { background: #f0f0f0; }
.lengre-table td:first-child { color: #e94560; font-weight: bold; }
.lengre-legend { display: flex; gap: 16px; padding: 6px 12px; background: #f0f0f0; border-top: 1px solid #ddd; font-size: 0.72rem; color: #666; }
.lengre-legend span { display: flex; align-items: center; gap: 4px; }
.lengre-legend .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
""" + CSS_EXTRA + """
</style>
</head>
<body>

<h1>📊 双色球 (SSQ) 分析</h1>

<div class="latest-card">
  <div class="period">最新: """ + year + """-""" + seq + """ 期</div>
  <div class="balls">
    <span class="label">红球:</span>
    """ + red_html + """
    <span class="label" style="margin-left:8px;">蓝球:</span>
    """ + blue_html + """
  </div>
</div>

<div class="main-grid">
  <div class="stat-table-wrap">
    <h3 style="padding:8px 12px;background:#e94560;color:#fff;">📋 近30期详细统计</h3>
    <table class="stat-table">
      <thead>
        <tr>
          <th>期号</th><th>开奖号码</th><th>和值</th><th>三区</th>
          <th>AC</th><th>极距</th><th>连号类型</th><th>连号</th><th>同尾类型</th><th>同尾</th>
        </tr>
      </thead>
      <tbody>
        """ + table_rows + """
      </tbody>
    </table>
  </div>

  <div class="heat-sidebar">
    <div class="heat-block">
      <div class="heat-label">🔥 热码（近30期出现多）</div>
      <div>""" + hot_html + """</div>
      <canvas id="draw-hot" class="draw-canvas"></canvas>
      <div class="chart-toolbar">
        <button onclick="switchBlock('hot')" id="btn-hot">标注此块</button>
        <input type="color" id="color-hot" value="#e94560">
        <input type="range" id="size-hot" min="1" max="20" value="3">
        <button onclick="clearDraw('hot')">清空</button>
      </div>
    </div>
    <div class="heat-block">
      <div class="heat-label">🌡️ 温码（近30期出现中等）</div>
      <div>""" + warm_html + """</div>
      <canvas id="draw-warm" class="draw-canvas"></canvas>
      <div class="chart-toolbar">
        <button onclick="switchBlock('warm')" id="btn-warm">标注此块</button>
        <input type="color" id="color-warm" value="#2196f3">
        <input type="range" id="size-warm" min="1" max="20" value="3">
        <button onclick="clearDraw('warm')">清空</button>
      </div>
    </div>
    <div class="heat-block">
      <div class="heat-label">❄️ 冷码（近30期出现少）</div>
      <div>""" + cold_html + """</div>
      <canvas id="draw-cold" class="draw-canvas"></canvas>
      <div class="chart-toolbar">
        <button onclick="switchBlock('cold')" id="btn-cold">标注此块</button>
        <input type="color" id="color-cold" value="#ff9800">
        <input type="range" id="size-cold" min="1" max="20" value="3">
        <button onclick="clearDraw('cold')">清空</button>
      </div>
    </div>
    <div class="heat-block">
      <div class="heat-label">💙 蓝球热码 Top8</div>
      <div>""" + hots_b_html + """</div>
      <canvas id="draw-hotb" class="draw-canvas"></canvas>
      <div class="chart-toolbar">
        <button onclick="switchBlock('hotb')" id="btn-hotb">标注此块</button>
        <input type="color" id="color-hotb" value="#4a90d9">
        <input type="range" id="size-hotb" min="1" max="20" value="3">
        <button onclick="clearDraw('hotb')">清空</button>
      </div>
    </div>
  </div>
</div>

""" + tail_pred_panel + """

<div class="lengre-section">
  <div class="lengre-header">
    <span>🔥 双色球冷热图（近30期）</span>
    <span style="font-size:0.72rem;opacity:0.8;">（点击任意格子可高亮）</span>
    <div style="display:flex;gap:6px;align-items:center;">
      <input type="color" id="color-lengre" value="#e94560">
      <input type="range" id="size-lengre" min="1" max="20" value="3">
      <button onclick="clearDraw('lengre')">清空标注</button>
    </div>
  </div>
  <div id="wrap-lengre" class="wrap-lengre">
    <table class="lengre-table">""" + lengre_table + """</table>
    <canvas id="draw-lengre" style="position:absolute;top:0;left:0;width:100%;height:100%;cursor:crosshair;z-index:10;"></canvas>
  </div>
  <div class="lengre-legend">
    <span><span class="dot" style="background:#e94560;"></span>热码区中奖</span>
    <span><span class="dot" style="background:#2196f3;"></span>温码区中奖</span>
    <span><span class="dot" style="background:#ff9800;"></span>冷码区中奖</span>
    <span><span class="dot" style="background:#888;"></span>未中奖</span>
  </div>
</div>

<div class="charts-grid">
  <div class="chart-frame">
    <h3>📈 历史遗漏排序图（带开奖号）</h3>
    <iframe src="https://www.17500.cn/chart/ssq-sort-omit-0.html" loading="lazy"></iframe>
  </div>
  <div class="chart-frame">
    <h3>📈 双色球遗漏排序图 - 当期</h3>
    <iframe src="https://www.17500.cn/chart/ssq-sort-omit-1.html" loading="lazy"></iframe>
  </div>
</div>

<div class="sources">
  <h3>🔗 数据来源</h3>
  <ul>
    <li><a href="https://www.17500.cn/chart/ssq-tjb.html" target="_blank">双色球统计表原始页</a></li>
    <li><a href="https://www.17500.cn/chart/ssq-lengre.html" target="_blank">冷热图原始页</a></li>
    <li><a href="https://www.17500.cn/chart/ssq-sort-omit-0.html" target="_blank">历史遗漏排序图</a></li>
    <li><a href="https://www.17500.cn/chart/ssq-sort-omit-1.html" target="_blank">遗漏排序图-当期</a></li>
  </ul>
</div>

<div class="updated">最后更新: """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """</div>

<script>
""" + TOGGLE_JS + DRAW_JS + """
</script>
</body>
</html>"""

with open('/Users/teld_hsh/github/ssq/ssq_analysis.html', 'w', encoding='utf-8') as f:
    f.write(HTML)

print("SUCCESS: 更新到 " + year + "-" + seq + " 期，30条记录")
