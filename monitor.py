#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞彩网足球胜平负支持率监控脚本
功能：定时调用官方 JSON API → 保存数据到 CSV → 生成折线图 HTML
"""

import requests
import csv
import os
from datetime import datetime

# ============================================================
# 配置区：可以根据需要修改这里的参数
# ============================================================

# 数据保存目录（脚本同级目录下的 data 文件夹）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 官方 JSON API 地址（从页面 JS 源码中提取）
API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getVoteV1.qry"

# 请求头：模拟浏览器，避免被识别为爬虫
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 每页条数（固定 10，与官网一致）
PAGE_SIZE = 10

# CSV 文件表头
CSV_HEADER = [
    "采集时间",
    "比赛编号",      # 如 周六201
    "联赛",
    "销售日期",      # businessDate：彩票销售日期，即网站上该期的日期（用于分组）
    "比赛日期",      # matchDate：比赛实际开球日期
    "主队",
    "客队",
    "mid",           # 比赛唯一 ID（matchId）
    "胜_投票数",
    "胜_支持率",      # 如 12（不含%号，方便计算）
    "平_投票数",
    "平_支持率",
    "负_投票数",
    "负_支持率",
    "比赛状态",       # Selling=销售中, End=已结束
]


# ============================================================
# 第一步：确保 data/ 目录存在
# ============================================================

def ensure_dirs():
    """如果目录不存在则自动创建"""
    os.makedirs(DATA_DIR, exist_ok=True)


# ============================================================
# 第二步：调用 API，获取所有分页的比赛数据
# ============================================================

def fetch_all_matches():
    """
    分页调用 API，返回所有比赛的数据列表。

    API 说明：
      - URL: https://webapi.sporttery.cn/gateway/uniform/football/getVoteV1.qry
      - 参数: poolCode=HAD（胜平负）, pageSize=10, pageNo=页码
      - 返回 JSON，errorCode=0 表示成功
      - 关键字段：value.matches.list（当页比赛列表），value.matches.pages（总页数）

    返回：list，每个元素是一场比赛的原始 dict
    """
    all_matches = []
    page = 1

    while True:
        params = {
            "poolCode": "HAD",   # HAD = 胜平负
            "pageSize": PAGE_SIZE,
            "pageNo": page,
        }

        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[错误] 请求第 {page} 页失败：{e}")
            break
        except ValueError:
            print(f"[错误] 第 {page} 页响应不是有效的 JSON")
            break

        # 检查业务状态码（API 返回的是字符串 "0"，用 str 比较）
        if str(data.get("errorCode")) != "0":
            print(f"[错误] API 返回错误码：{data.get('errorCode')}，消息：{data.get('errorMessage')}")
            break

        matches_data = data["value"]["matches"]
        page_list = matches_data.get("list", [])
        total_pages = int(matches_data.get("pages", 1))

        all_matches.extend(page_list)
        print(f"[信息] 第 {page}/{total_pages} 页，获取 {len(page_list)} 场比赛")

        # 已是最后一页，退出
        if page >= total_pages:
            break
        page += 1

    return all_matches


# ============================================================
# 第三步：解析每场比赛的原始字段，整理成我们需要的格式
# ============================================================

def parse_match(raw):
    """
    将 API 返回的原始比赛字典转换为我们的存储格式。

    API 返回的关键字段（已验证）：
      matchId        - 比赛唯一 ID，如 2040475
      matchNum       - 编号，如 "周六201"
      matchDate      - 比赛日期，如 "2026-07-11"
      homeTeamAllName- 主队名称
      awayTeamAllName- 客队名称
      leagueAllName  - 联赛名称
      win            - 胜的投票数（整数）
      draw           - 平的投票数（整数）
      lose           - 负的投票数（整数）
      hsupportRate   - 胜的支持率，如 "12%"
      dsupportRate   - 平的支持率，如 "17%"
      asupportRate   - 负的支持率，如 "71%"
      poolStatus     - 比赛状态，"Selling" 表示销售中

    返回：整理后的字典
    """
    # 去掉百分号，转为整数，方便后续画图（如 "12%" → 12）
    def pct_to_int(s):
        try:
            return int(str(s).replace("%", "").strip())
        except (ValueError, AttributeError):
            return 0

    return {
        "mid": str(raw.get("matchId", "")),
        "比赛编号": raw.get("matchNum", ""),
        "联赛": raw.get("leagueAllName", ""),
        "销售日期": raw.get("businessDate", ""),   # 网站按这个日期分组（期号日期）
        "比赛日期": raw.get("matchDate", ""),       # 实际开球日期
        "主队": raw.get("homeTeamAllName", ""),
        "客队": raw.get("awayTeamAllName", ""),
        "胜_投票数": int(raw.get("win", 0)),
        "胜_支持率": pct_to_int(raw.get("hsupportRate", "0%")),
        "平_投票数": int(raw.get("draw", 0)),
        "平_支持率": pct_to_int(raw.get("dsupportRate", "0%")),
        "负_投票数": int(raw.get("lose", 0)),
        "负_支持率": pct_to_int(raw.get("asupportRate", "0%")),
        "比赛状态": raw.get("poolStatus", ""),
    }


# ============================================================
# 第四步：将数据追加写入 CSV 文件
# ============================================================

def save_to_csv(matches, timestamp):
    """
    每场比赛写入独立的 CSV 文件，文件名为比赛 mid。
    例如：data/2040475.csv

    每次运行脚本时追加一行，CSV 会随时间累积，形成时间序列数据。
    这份时间序列就是后续折线图的数据来源。

    参数：
      matches   - 本次解析后的比赛列表（parse_match 的结果）
      timestamp - 本次采集时间字符串，如 "2026-07-11 09:30"
    """
    for m in matches:
        mid = m["mid"]
        csv_path = os.path.join(DATA_DIR, f"{mid}.csv")
        file_exists = os.path.exists(csv_path)

        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            # utf-8-sig：写入 BOM 头，Windows 的 Excel 打开中文不乱码
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)

            if not file_exists:
                writer.writeheader()  # 文件首次创建时写表头

            writer.writerow({
                "采集时间":  timestamp,
                "比赛编号":  m["比赛编号"],
                "联赛":      m["联赛"],
                "销售日期":  m["销售日期"],
                "比赛日期":  m["比赛日期"],
                "主队":      m["主队"],
                "客队":      m["客队"],
                "mid":       mid,
                "胜_投票数": m["胜_投票数"],
                "胜_支持率": m["胜_支持率"],
                "平_投票数": m["平_投票数"],
                "平_支持率": m["平_支持率"],
                "负_投票数": m["负_投票数"],
                "负_支持率": m["负_支持率"],
                "比赛状态":  m["比赛状态"],
            })


# ============================================================
# 主函数：整合所有步骤，每次 cron 调用时执行一次
# ============================================================

def main():
    """
    每次被 cron 调用时的完整流程：
    1. 确保目录存在
    2. 调用 API 获取所有比赛数据
    3. 解析数据
    4. 追加写入 CSV
    """
    ensure_dirs()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"[开始] 采集时间：{now}")
    print(f"{'='*50}")

    # 抓取原始数据
    raw_matches = fetch_all_matches()

    if not raw_matches:
        print("[警告] 未获取到任何比赛数据，请检查网络连接")
        return

    # 解析
    matches = [parse_match(m) for m in raw_matches]
    print(f"[汇总] 本次共采集 {len(matches)} 场比赛")

    # 存 CSV
    save_to_csv(matches, now)
    print(f"[完成] 数据已保存到 {DATA_DIR}/")


if __name__ == "__main__":
    main()
