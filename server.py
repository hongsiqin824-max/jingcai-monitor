#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Web 服务器
提供数据 API 和前端页面
运行方式：python3 server.py
浏览器访问：http://localhost:5000
"""

from flask import Flask, Response, jsonify, request, send_from_directory
import csv
import os
import re
import time
from datetime import date, datetime, timedelta
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

app = Flask(__name__, static_folder=".")

# data 目录路径（与 server.py 同级）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 元数据缓存（避免每次请求都全量扫描 CSV）
_meta_cache = None
_meta_cache_time = 0.0
_META_CACHE_TTL = 60  # 缓存有效期（秒）
_WEEKDAY_ORDER = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_MATCH_ID_PATTERN = re.compile(r"^\d{1,20}$")
_CHART_WIDTH = 1068
_CHART_HEIGHT = 860
_CHART_COLORS = {
    "win": "#e74c3c",
    "draw": "#f39c12",
    "loss": "#2980b9",
}


# ============================================================
# 工具函数
# ============================================================

def get_all_matches_meta():
    """
    扫描 data/ 下所有 CSV，提取每场比赛的基本信息。
    只读每个 CSV 的第一行（表头+第一条数据），速度快。
    结果缓存 60 秒，避免每次请求都全量扫描磁盘。
    返回 dict: { mid: {mid, 比赛编号, 联赛, 比赛日期, 主队, 客队, title} }
    """
    global _meta_cache, _meta_cache_time
    now = time.time()
    if _meta_cache is not None and now - _meta_cache_time < _META_CACHE_TTL:
        return _meta_cache

    meta = {}
    if not os.path.exists(DATA_DIR):
        _meta_cache = meta
        _meta_cache_time = now
        return meta

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".csv"):
            continue
        mid = filename.replace(".csv", "")
        csv_path = os.path.join(DATA_DIR, filename)
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = (
                        f"{row.get('比赛编号', '')} "
                        f"{row.get('联赛', '')} "
                        f"{row.get('比赛日期', '')} "
                        f"{row.get('主队', '')} VS {row.get('客队', '')}"
                    )
                    meta[mid] = {
                        "mid": mid,
                        "比赛编号": row.get("比赛编号", ""),
                        "联赛": row.get("联赛", ""),
                        "销售日期": row.get("销售日期", ""),
                        "比赛日期": row.get("比赛日期", ""),
                        "主队": row.get("主队", ""),
                        "客队": row.get("客队", ""),
                        "title": title,
                    }
                    break
        except Exception:
            continue

    _meta_cache = meta
    _meta_cache_time = now
    return meta


def read_chart_data(mid):
    """读取某场比赛的全部时间序列数据，返回供前端绘图的字典"""
    csv_path = os.path.join(DATA_DIR, f"{mid}.csv")
    if not os.path.exists(csv_path):
        return None

    times, win_pcts, draw_pcts, loss_pcts, total_votes = [], [], [], [], []

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                times.append(row["采集时间"])
                win_pcts.append(int(row["胜_支持率"]))
                draw_pcts.append(int(row["平_支持率"]))
                loss_pcts.append(int(row["负_支持率"]))
                win_v  = int(row.get("胜_投票数", 0) or 0)
                draw_v = int(row.get("平_投票数", 0) or 0)
                loss_v = int(row.get("负_投票数", 0) or 0)
                total_votes.append(win_v + draw_v + loss_v)
    except Exception:
        return None

    return {
        "mid": mid,
        "times": times,
        "win": win_pcts,
        "draw": draw_pcts,
        "loss": loss_pcts,
        "total_votes": total_votes,
    }


def _format_chart_time(value):
    """Convert a CSV timestamp to the same Chinese label used by dashboard.html."""
    raw = str(value or "").strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        return raw
    return f"{parsed.month}月{parsed.day}日 {parsed:%H:%M}"


def _compute_axis_ticks(raw_times, max_ticks=12):
    """Keep first/day-change ticks and evenly sample the rest, matching the dashboard."""
    formatted = [_format_chart_time(value) for value in raw_times]
    count = len(raw_times)
    if count == 0:
        return formatted, [], []

    anchors = {0}
    for index in range(1, count):
        current_day = str(raw_times[index]).split(" ", 1)[0]
        previous_day = str(raw_times[index - 1]).split(" ", 1)[0]
        if current_day != previous_day:
            anchors.add(index)

    step = max(1, count // max_ticks)
    min_gap = max(2, step // 2)
    selected = set(anchors)

    def is_too_close(index):
        return any(abs(index - existing) < min_gap for existing in selected)

    for index in range(0, count, step):
        if not is_too_close(index):
            selected.add(index)
    if not is_too_close(count - 1):
        selected.add(count - 1)

    indices = sorted(selected)
    tick_values = [formatted[index] for index in indices]
    tick_text = []
    for index in indices:
        current = str(raw_times[index])
        current_day = current.split(" ", 1)[0]
        previous_day = str(raw_times[index - 1]).split(" ", 1)[0] if index > 0 else ""
        if index == 0 or current_day != previous_day:
            tick_text.append(formatted[index])
        else:
            tick_text.append(current.split(" ", 1)[1] if " " in current else current)
    return formatted, tick_values, tick_text


def _single_y_range(values):
    """Use the dashboard's tight independent range for one support-rate series."""
    if not values:
        return [0, 100]
    return [max(0, min(values) - 1), min(100, max(values) + 1)]


def _safe_download_filename(meta, mid):
    issue_num = str(meta.get("比赛编号", "")).strip() or mid
    home = str(meta.get("主队", "")).strip() or "主队"
    away = str(meta.get("客队", "")).strip() or "客队"
    filename = f"{issue_num}_{home}VS{away}_支持率.png"
    filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", filename)
    filename = re.sub(r"\s+", "", filename).strip("._")
    return filename or f"{mid}_支持率.png"


def build_support_rate_figure(mid):
    """Build the downloadable three-panel Plotly figure for one match."""
    if not _MATCH_ID_PATTERN.fullmatch(str(mid or "")):
        raise ValueError("比赛 ID 格式无效")

    data = read_chart_data(mid)
    if data is None or not data.get("times"):
        raise FileNotFoundError("暂无该场比赛的支持率数据")
    meta = get_all_matches_meta().get(mid)
    if not meta:
        raise FileNotFoundError("暂无该场比赛的基础信息")

    formatted_times, tick_values, tick_text = _compute_axis_ticks(data["times"], 12)
    series = [
        ("win", "胜", data["win"], 1),
        ("draw", "平", data["draw"], 2),
        ("loss", "负", data["loss"], 3),
    ]
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.07,
    )

    for key, label, values, row in series:
        point_count = len(values)
        text = [""] * point_count
        positions = ["middle right"] * point_count
        if point_count:
            text[0] = f"{values[0]}%"
            positions[0] = "middle left"
            if point_count > 1:
                text[-1] = f"{values[-1]}%"
                positions[-1] = "middle right"
        figure.add_trace(
            go.Scatter(
                x=formatted_times,
                y=values,
                mode="lines+text",
                name=label,
                text=text,
                textposition=positions,
                textfont={"size": 12, "color": _CHART_COLORS[key]},
                cliponaxis=False,
                hovertemplate=f"{label}：%{{y}}<extra></extra>",
                line={"color": _CHART_COLORS[key], "width": 2},
            ),
            row=row,
            col=1,
        )

        y_range = _single_y_range(values)
        figure.update_yaxes(
            range=y_range,
            ticksuffix="%",
            tickfont={"size": 10, "color": "#666"},
            gridcolor="#eee",
            linecolor="#ddd",
            zerolinecolor="#eee",
            title={"text": f"{label} (%)", "font": {"size": 12, "color": _CHART_COLORS[key]}},
            fixedrange=True,
            row=row,
            col=1,
        )
        figure.add_hrect(
            y0=y_range[0],
            y1=y_range[1],
            fillcolor={
                "win": "rgba(231,76,60,0.02)",
                "draw": "rgba(243,156,18,0.02)",
                "loss": "rgba(41,128,185,0.02)",
            }[key],
            line_width=0,
            layer="below",
            row=row,
            col=1,
        )

        figure.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=formatted_times,
            tickmode="array",
            tickvals=tick_values,
            ticktext=tick_text,
            showticklabels=row == 3,
            tickangle=-30 if row == 3 else 0,
            tickfont={"size": 10, "color": "#666"},
            gridcolor="#eee",
            linecolor="#ddd",
            zerolinecolor="#eee",
            fixedrange=True,
            row=row,
            col=1,
        )

    home = str(meta.get("主队", "")).strip() or "主队"
    away = str(meta.get("客队", "")).strip() or "客队"
    subtitle_parts = [
        str(meta.get("比赛编号", "")).strip(),
        str(meta.get("联赛", "")).strip(),
        str(meta.get("比赛日期", "")).strip(),
    ]
    subtitle = " · ".join(part for part in subtitle_parts if part)
    title_home = escape(home)
    title_away = escape(away)
    title_subtitle = escape(subtitle)
    figure.update_layout(
        width=_CHART_WIDTH,
        height=_CHART_HEIGHT,
        margin={"t": 102, "r": 39, "b": 56, "l": 52},
        title={
            "text": (
                f"<b>{title_home} VS {title_away}</b>"
                f"<br><span style='font-size:14px;color:#666'>{title_subtitle}</span>"
            ),
            "x": 0.5,
            "xanchor": "center",
            "y": 0.975,
            "yanchor": "top",
            "font": {"family": "PingFang SC, Microsoft YaHei, Arial, sans-serif", "size": 22, "color": "#1a3a5c"},
        },
        font={"family": "PingFang SC, Microsoft YaHei, Arial, sans-serif", "color": "#333"},
        showlegend=False,
        hovermode="x",
        plot_bgcolor="#fff",
        paper_bgcolor="#fff",
    )
    return figure, meta


def render_support_rate_png(mid):
    figure, meta = build_support_rate_figure(mid)
    # Plotly 6.9 currently supplies an HTTP header option that Kaleido 1.2's
    # Chromium wrapper does not accept. It is unnecessary for local rendering.
    pio.defaults.headers = None
    image = figure.to_image(
        format="png",
        width=_CHART_WIDTH,
        height=_CHART_HEIGHT,
        scale=1,
    )
    return image, _safe_download_filename(meta, mid)


def _match_num_key(num):
    if len(num) >= 2 and num[1] in _WEEKDAY_ORDER:
        suffix = num[2:]
        if suffix.isdigit():
            return (_WEEKDAY_ORDER[num[1]], 0, int(suffix))
        return (_WEEKDAY_ORDER[num[1]], 1, suffix)
    return (7, 1, num)


def get_upcoming_matches(today=None):
    """返回今天起所有已采集到的竞彩编号日比赛。"""
    start_date = today or datetime.now(_SHANGHAI_TZ).date().isoformat()
    start_day = date.fromisoformat(start_date)
    matches = []
    for match in get_all_matches_meta().values():
        business_date = str(match.get("销售日期", "")).strip()
        try:
            business_day = date.fromisoformat(business_date)
        except ValueError:
            continue
        if business_day < start_day:
            continue
        matches.append({
            "matchId": str(match.get("mid", "")).strip(),
            "issueNum": str(match.get("比赛编号", "")).strip(),
            "businessDate": business_date,
            "matchDate": str(match.get("比赛日期", "")).strip(),
            "competitionName": str(match.get("联赛", "")).strip(),
            "homeTeam": str(match.get("主队", "")).strip(),
            "awayTeam": str(match.get("客队", "")).strip(),
        })
    matches.sort(key=lambda item: (
        item["businessDate"],
        _match_num_key(item["issueNum"]),
        item["matchId"],
    ))
    return matches


# ============================================================
# API 路由
# ============================================================

@app.route("/")
def index():
    """返回前端主页面"""
    return send_from_directory(".", "dashboard.html")


@app.route("/v2")
def index_v2():
    return send_from_directory(".", "dashboard_v2.html")


@app.route("/v3")
def index_v3():
    return send_from_directory(".", "dashboard_v3.html")


@app.route("/api/dates")
def api_dates():
    """
    返回可用日期列表。
    规则：历史上有数据的日期 + 今天/今天+1/今天+2，合并去重，升序排列。
    """
    today = datetime.now().date()
    future_dates = {str(today + timedelta(days=i)) for i in range(3)}

    # 从 CSV 元信息中收集历史日期（按销售日期分组，与网站一致）
    history_dates = set()
    for m in get_all_matches_meta().values():
        d = m.get("销售日期", "")
        if d:
            history_dates.add(d)

    all_dates = sorted(history_dates | future_dates)
    today_str = str(today)
    return jsonify({"dates": all_dates, "today": today_str})


@app.route("/api/matches")
def api_matches():
    """
    返回指定日期的比赛列表（仅元信息，不含图表数据）。
    参数: ?date=2026-07-11
    """
    date = request.args.get("date", "")
    meta = get_all_matches_meta()
    # 按销售日期过滤（与网站分期逻辑一致）
    matches = [m for m in meta.values() if m.get("销售日期") == date]
    # 按比赛编号排序（周六201 < 周六202 ...）
    matches.sort(key=lambda x: _match_num_key(x.get("比赛编号", "")))
    return jsonify({"date": date, "total": len(matches), "matches": matches})


@app.route("/api/matches/upcoming")
def api_upcoming_matches():
    """返回上海时区今天起，所有 CSV 中已有数据的竞彩比赛。"""
    today = datetime.now(_SHANGHAI_TZ).date().isoformat()
    matches = get_upcoming_matches(today)
    business_dates = sorted({item["businessDate"] for item in matches})
    return jsonify({
        "ok": True,
        "date": today,
        "businessDateStart": business_dates[0] if business_dates else today,
        "businessDateEnd": business_dates[-1] if business_dates else "",
        "total": len(matches),
        "matches": matches,
    })


@app.route("/api/chart/<mid>")
def api_chart(mid):
    """
    返回某场比赛的折线图时间序列数据。
    前端用 Plotly.js 渲染并实现静默更新。
    """
    data = read_chart_data(mid)
    if data is None:
        return jsonify({"error": "暂无数据"}), 404
    return jsonify(data)


@app.route("/api/chart/<mid>/image")
def api_chart_image(mid):
    """Generate and download a titled PNG using all collected points for one match."""
    if not _MATCH_ID_PATTERN.fullmatch(str(mid or "")):
        return jsonify({"error": "invalid_match_id", "detail": "比赛 ID 格式无效"}), 400
    try:
        image, filename = render_support_rate_png(mid)
    except FileNotFoundError as exc:
        return jsonify({"error": "support_rate_not_found", "detail": str(exc)}), 404
    except Exception as exc:
        app.logger.exception("生成支持率图片失败: mid=%s", mid)
        return jsonify({
            "error": "support_rate_render_failed",
            "detail": f"支持率图片生成失败：{exc}",
        }), 500

    ascii_filename = f"support-rate-{mid}.png"
    response = Response(image, status=200, mimetype="image/png")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


if __name__ == "__main__":
    print("=" * 50)
    print("竞彩支持率监控服务已启动")
    print("浏览器访问：http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
