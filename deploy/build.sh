#!/usr/bin/env bash
# 在 V100 服务器上构建 MAA-FnOS（纯套壳）镜像
# 用法: bash /home/<user>/maa-work/deploy/build.sh
set -euo pipefail

WORK=/home/<user>/maa-work
CTX=$WORK/build-ctx

# Web 源码必须是「带网关 socket 支持」的那一版，否则镜像里没有 serve_socket.py，
# 容器根本不会去 listen /gw/app.sock —— 装上后应用中心一直显示异常。
# 上游 KlN-4096/MAA-WEB-CONTROL 没有这个改造，只能用自己的 fork：
#   https://github.com/mydanyi/MAA-WEB-CONTROL  master @ 336a795b8105076c57d9f93d54a5e35b6a1af15c
# 目录名固定为 MAA-WEB-CONTROL-master/（Dockerfile 也按这个名字 COPY）。
WEB_SRC="$WORK/src/MAA-WEB-CONTROL-master"

echo "=== [1/4] 校验 MAA 官方包 ==="
gzip -t "$WORK/maa-linux.tar.gz" && echo "tarball OK"

echo "=== [2/4] 准备构建上下文 ==="
# 先把关：源码里没有 serve_socket.py 就说明拿错了源（多半是上游 v0.2.0），
# 现在停下比打完包再发现问题省事得多。
if [ ! -f "$WEB_SRC/serve_socket.py" ]; then
    echo "ERROR: $WEB_SRC 缺少 serve_socket.py —— Web 源码不是网关版。" >&2
    echo "       请用 mydanyi/MAA-WEB-CONTROL master @ 336a795b 这一版（见 docs/构建指南.md 1.2）。" >&2
    exit 1
fi
rm -rf "$CTX"
mkdir -p "$CTX"
cp -f "$WORK/maa-linux.tar.gz" "$CTX/"
cp -r "$WEB_SRC" "$CTX/"
cp -f "$WORK/src/Dockerfile" "$CTX/"
ls -la "$CTX"

echo "=== [3/4] docker build ==="
cd "$CTX"
docker build -t maa-fnos:local --build-arg MAA_TARBALL=maa-linux.tar.gz .
echo "=== [4/4] BUILD OK ==="
docker images maa-fnos:local --format "{{.Repository}}:{{.Tag}} {{.Size}}"
