#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MAA on 飞牛 —— 自动升级小助手（宿主侧常驻）

背景
----
飞牛的「手动安装 fpk」对**已安装**的应用只解包、不安装：
包被解到 `/vol1/appcenter-downloads/<appname>-<版本>-tpk/`，然后命令直接返回成功。
于是每次升级，用户都得先卸载、再装一遍。

这个脚本常驻在宿主机上（由 cmd/main 拉起，和 redroid 状态代理同一个模式），
盯着那个 downloads 目录：一旦发现比当前已装版本更高的包，就用
`appcenter-cli install-local -d <目录> -v <卷号>` 把它装上 ——
这条命令本身就是「先卸后装」，而用户数据在 `/vol1/@appdata/<appname>/`，
卸载不会碰，所以配置、任务档案、日志都在。

用户要做的只有一件事：应用中心 → 手动安装 → 上传新的 fpk。

设计上的几个硬约束
------------------
1. **只升不降**：目标版本必须严格高于已装版本，避免把用户按回旧版。
2. **有次数上限**：同一个包最多尝试 3 次。装不上就放弃并在日志里说清楚，
   绝不无限重试 —— 否则会一直打断正在跑的任务。
3. **发起升级用独立会话**：install-local 会先卸载应用，本进程可能随之被杀，
   所以升级命令必须以新会话启动、自己跑完。
4. **应用真的没了就退出**：用户卸载应用后，本进程不能把应用"装回来"。
   但升级过程中的短暂消失不算 —— 那时会有 install-local 在跑，等它。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

# 与 cmd/main 里的 WATCHER_VERSION 保持一致：对不上说明磁盘上是新脚本、
# 内存里还是旧进程，cmd/main 会把旧进程换掉。
WATCHER_VERSION = "1.0"

APPNAME = "maa-fnos"
DOWNLOADS_ROOT = "/vol1/appcenter-downloads"
INSTALLED_MANIFEST = f"/var/apps/{APPNAME}/manifest"
VAR_DIR = os.environ.get("MAA_WATCHER_VAR", f"/vol1/@appdata/{APPNAME}")
STATE_FILE = os.path.join(VAR_DIR, "upgrade-watcher.state.json")
LOG_FILE = os.path.join(VAR_DIR, "upgrade-watcher.log")
VERSION_FILE = os.path.join(VAR_DIR, "upgrade-watcher.version")
INSTALL_LOG = os.path.join(VAR_DIR, "upgrade-install.log")

POLL_SECONDS = 30
MAX_ATTEMPTS = 3


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}"
    try:
        os.makedirs(VAR_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def write_version_file() -> None:
    try:
        os.makedirs(VAR_DIR, exist_ok=True)
        with open(VERSION_FILE, "w", encoding="utf-8") as fh:
            fh.write(WATCHER_VERSION + "\n")
    except OSError:
        pass


def read_manifest_version(path: str) -> str | None:
    """读 manifest 里的 version，形如 `version               = 1.0.8`。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                match = re.match(r"\s*version\s*=\s*(\S+)", line)
                if match:
                    return match.group(1).strip()
    except OSError:
        return None
    return None


def version_key(text: str | None) -> tuple[int, ...]:
    """把版本号变成可比较的数字元组：1.0.10 > 1.0.9（字符串比会反过来）。"""
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts[:4]) if parts else (0,)


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("handled"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"handled": {}}


def save_state(state: dict) -> None:
    try:
        os.makedirs(VAR_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def installed_version() -> str | None:
    return read_manifest_version(INSTALLED_MANIFEST)


def pending_install_running() -> bool:
    """有没有正在跑的 install-local（升级过程中应用会短暂"不存在"）。"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "appcenter-cli install-local"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def find_candidates() -> list[dict]:
    """扫 downloads 目录，返回所有 maa-fnos 的解包目录（带版本与卷号）。"""
    volume_match = re.match(r"/vol(\d+)/", DOWNLOADS_ROOT)
    volume = volume_match.group(1) if volume_match else "1"
    found: list[dict] = []
    try:
        names = sorted(os.listdir(DOWNLOADS_ROOT))
    except OSError:
        return found
    for name in names:
        if not (name.startswith(f"{APPNAME}-") and name.endswith("-tpk")):
            continue
        directory = os.path.join(DOWNLOADS_ROOT, name)
        version = read_manifest_version(os.path.join(directory, "manifest"))
        if not version:
            continue
        found.append({"name": name, "dir": directory, "version": version, "volume": volume})
    return found


def start_install(candidate: dict) -> None:
    """以独立会话启动 install-local：它会先卸载应用，本进程可能被杀，
    但这条命令必须能自己跑完。"""
    cmd = [
        "appcenter-cli", "install-local",
        "-d", candidate["dir"],
        "-v", str(candidate["volume"]),
        "-a", "yes",
    ]
    log(f"installing {candidate['name']} (version {candidate['version']}): {' '.join(cmd)}")
    try:
        os.makedirs(VAR_DIR, exist_ok=True)
        sink = open(INSTALL_LOG, "ab")
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,   # 新会话：脱离本进程，扛住卸载阶段
            cwd="/tmp",
        )
    except OSError as exc:
        log(f"failed to start install-local: {exc!r}")


def cycle() -> None:
    current = installed_version()
    if current is None:
        if pending_install_running():
            # 升级正在跑（install-local 内部卸载了这个应用），等它。
            return
        log("application is not installed; watcher exits.")
        sys.exit(0)

    state = load_state()
    handled = state["handled"]
    current_key = version_key(current)

    for candidate in find_candidates():
        if version_key(candidate["version"]) <= current_key:
            continue
        record = handled.get(candidate["name"]) or {}
        if record.get("version") == candidate["version"] and record.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        if pending_install_running():
            log(f"another install is already running; skip {candidate['name']} this round.")
            return
        handled[candidate["name"]] = {
            "version": candidate["version"],
            "attempts": int(record.get("attempts", 0)) + 1,
            "ts": int(time.time()),
        }
        save_state(state)          # 先记账再动手，避免重复触发
        start_install(candidate)
        return


def main() -> None:
    write_version_file()
    log(f"upgrade watcher started (version {WATCHER_VERSION}).")
    time.sleep(POLL_SECONDS)       # 让应用先起来，别跟启动流程抢
    while True:
        try:
            cycle()
        except SystemExit:
            raise
        except Exception as exc:   # noqa: BLE001 —— 常驻进程不能被单次异常打死
            log(f"unexpected error in cycle: {exc!r}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
