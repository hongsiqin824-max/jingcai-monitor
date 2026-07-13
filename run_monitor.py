#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时运行 monitor.py 的守护脚本
用法：在终端运行  python3 run_monitor.py
     程序会每5分钟自动采集一次，关闭终端窗口即停止
"""

import time
import subprocess
import sys
import os
from datetime import datetime

# 每隔多少秒执行一次（300秒 = 5分钟）
INTERVAL = 300

script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.py")

print(f"[启动] 监控程序已启动，每 {INTERVAL//60} 分钟采集一次")
print(f"[提示] 关闭此终端窗口即可停止监控")
print(f"{'='*50}")

while True:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] 开始采集...")

    # 调用 monitor.py 执行一次采集
    result = subprocess.run([sys.executable, script_path], capture_output=False)

    if result.returncode != 0:
        print(f"[警告] 本次采集异常，将在 {INTERVAL//60} 分钟后重试")

    print(f"[等待] 下次采集时间：{INTERVAL//60} 分钟后")
    time.sleep(INTERVAL)
