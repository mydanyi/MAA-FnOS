#!/usr/bin/env bash
# 在构建机上构建 MAA-FnOS（纯套壳）镜像
#
# 用法：
#   MAA_BUILD_WORK=/绝对路径/构建目录 bash deploy/build.sh
#
# 可选项：
#   MAA_WEB_SOURCE   Web 源码目录；默认 $MAA_BUILD_WORK/src/MAA-WEB-CONTROL-master
#   MAA_IMAGE_TAG    输出镜像 tag；默认 maa-fnos:local
#
# 前置：$MAA_BUILD_WORK/maa-linux.tar.gz（MAA 官方 Linux 包）。
# Dockerfile 与 redroid-proxy 由脚本从仓库自身取，构建目录里不需要放。
set -euo pipefail

# 调用方必须传一个独立的绝对构建目录（放官方包、Web 源码、构建上下文）。
WORK="${MAA_BUILD_WORK:-}"
if [ -z "$WORK" ]; then
    echo "ERROR: 需要设置 MAA_BUILD_WORK（独立的绝对构建目录）。" >&2
    echo "       例：MAA_BUILD_WORK=/data/maa-work bash deploy/build.sh" >&2
    exit 1
fi
case "$WORK" in
    /*) ;;
    *) echo "ERROR: MAA_BUILD_WORK 必须是绝对路径：$WORK" >&2; exit 1 ;;
esac

# 仓库根 = 脚本所在目录的上一层，Dockerfile 与 redroid-proxy 都从这里取。
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Web 源码必须是「带网关 socket 支持」的那一版，否则镜像里没有 serve_socket.py，
# 容器根本不会去 listen /gw/app.sock —— 装上后应用中心一直显示异常。
# 上游 KlN-4096/MAA-WEB-CONTROL 没有这个改造，只能用自己的 fork：
#   https://github.com/mydanyi/MAA-WEB-CONTROL @ 15a38b74337e321a153e74be362921bfa5a33f6a
WEB_SRC="${MAA_WEB_SOURCE:-$WORK/src/MAA-WEB-CONTROL-master}"

# 镜像 tag 可覆盖（cmd/main 认的默认名是 maa-fnos:local）。
IMAGE_TAG="${MAA_IMAGE_TAG:-maa-fnos:local}"

echo "=== [1/4] 校验 MAA 官方包 ==="
gzip -t "$WORK/maa-linux.tar.gz" && echo "tarball OK"

echo "=== [2/4] 准备构建上下文 ==="
# 先把关：源码里没有 serve_socket.py 就说明拿错了源（多半是上游原版），
# 现在停下比打完包再发现问题省事得多。
if [ ! -f "$WEB_SRC/serve_socket.py" ]; then
    echo "ERROR: $WEB_SRC 缺少 serve_socket.py —— Web 源码不是网关版。" >&2
    echo "       请用 mydanyi/MAA-WEB-CONTROL @ 15a38b74337e321a153e74be362921bfa5a33f6a（见 docs/构建指南.md 1.2）。" >&2
    exit 1
fi

# 每次构建新开一个上下文目录，不动构建目录里已有的任何内容。
CTX="$(mktemp -d "$WORK/build-ctx.XXXXXX")"
cp -f "$WORK/maa-linux.tar.gz" "$CTX/"
# Dockerfile COPY 的是 MAA-WEB-CONTROL-master/，这里就按这个名字落进上下文，
# 不管 MAA_WEB_SOURCE 指向的目录本来叫什么。
cp -r "$WEB_SRC" "$CTX/MAA-WEB-CONTROL-master"
cp -f "$REPO_ROOT/deploy/Dockerfile" "$CTX/"
cp -r "$REPO_ROOT/redroid-proxy" "$CTX/"
ls -la "$CTX"

echo "=== [3/4] docker build ==="
cd "$CTX"
docker build -t "$IMAGE_TAG" --build-arg MAA_TARBALL=maa-linux.tar.gz .
echo "=== [4/4] BUILD OK ==="
docker images "$IMAGE_TAG" --format "{{.Repository}}:{{.Tag}} {{.Size}}"
