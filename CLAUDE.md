# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 运行方式

```bash
# 启动 Web 服务（浏览器访问 http://localhost:5000）
python3 server.py

# 手动触发一次数据采集
python3 monitor.py

# 定时采集（建议每 5 分钟一次，加入 crontab）
# */5 * * * * cd /path/to/new1 && python3 monitor.py >> monitor.log 2>&1
```

依赖：`flask`、`requests`（均需 pip 安装）。

## 架构概览

数据流向：`monitor.py`（cron 定时）→ `data/{mid}.csv`（追加行）→ `server.py`（Flask API）→ `dashboard_v3.html`（Plotly.js 前端）

### monitor.py
分页调用 `webapi.sporttery.cn` 的 HAD（胜平负）接口，将每场比赛的支持率快照追加到 `data/{matchId}.csv`。每次运行写一行，CSV 随时间累积为时间序列。

### server.py
Flask 服务，端口 5000，三个路由对应三个版本的前端：
- `GET /` → `dashboard.html`
- `GET /v2` → `dashboard_v2.html`
- `GET /v3` → `dashboard_v3.html`（当前主版本）

三个 API：
- `GET /api/dates` — 返回有数据的历史日期 + 今天及未来两天，合并去重后升序返回
- `GET /api/matches?date=YYYY-MM-DD` — 按 `销售日期`（businessDate，即期号日期）过滤比赛列表，仅返回元信息；比赛按编号中的星期字符排序（如"周六201"中取 `[1]` 位）
- `GET /api/chart/{mid}` — 返回指定比赛的完整时间序列（times/win/draw/loss/total_votes）

服务端有 60 秒元数据缓存（`_meta_cache`），只读每个 CSV 的第一行，避免每次请求全量扫描 `data/`。

### dashboard_v3.html
纯静态单页，依赖 `server.py` 提供的 API。关键逻辑：
- 每 5 分钟静默刷新（`REFRESH_INTERVAL = 300`），底部进度条可视化剩余时间
- 每页展示 4 张卡片（`PAGE_SIZE = 4`），分页导航
- 双击卡片打开全屏 Modal，显示大图（带坐标轴标题和工具栏）
- Y 轴范围合并缓存（`chartRangeCache`），同一场比赛在卡片和 Modal 间保持纵轴一致

## 数据格式

`data/{mid}.csv` 的关键字段：

| 字段 | 说明 |
|------|------|
| `销售日期` | 彩票期号日期（用于网站日期分组，非比赛日） |
| `比赛日期` | 实际开球日期 |
| `胜_支持率` | 整数，如 `78`（不含 `%`） |
| `mid` | matchId，与文件名一致 |
| `比赛状态` | `Selling` = 销售中，`End` = 已结束 |
