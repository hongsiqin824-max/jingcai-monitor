#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Web 服务器
提供数据 API 和前端页面
运行方式：python3 server.py
浏览器访问：http://localhost:5000
"""

from flask import Flask, jsonify, request, send_from_directory
import csv
import os
import time
from datetime import datetime, timedelta

app = Flask(__name__, static_folder=".")

# data 目录路径（与 server.py 同级）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 元数据缓存（避免每次请求都全量扫描 CSV）
_meta_cache = None
_meta_cache_time = 0.0
_META_CACHE_TTL = 60  # 缓存有效期（秒）
_WEEKDAY_ORDER = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}


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

    times, win_pcts, draw_pcts, loss_pcts = [], [], [], []

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                times.append(row["采集时间"])
                win_pcts.append(int(row["胜_支持率"]))
                draw_pcts.append(int(row["平_支持率"]))
                loss_pcts.append(int(row["负_支持率"]))
    except Exception:
        return None

    return {
        "mid": mid,
        "times": times,
        "win": win_pcts,
        "draw": draw_pcts,
        "loss": loss_pcts,
    }


def _match_num_key(num):
    if len(num) >= 2 and num[1] in _WEEKDAY_ORDER:
        suffix = num[2:]
        return (_WEEKDAY_ORDER[num[1]], int(suffix) if suffix.isdigit() else suffix)
    return (7, num)


# ============================================================
# API 路由
# ============================================================

@app.route("/")
def index():
    """返回前端主页面"""
    return send_from_directory(".", "dashboard.html")


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


if __name__ == "__main__":
    print("=" * 50)
    print("竞彩支持率监控服务已启动")
    print("浏览器访问：http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
