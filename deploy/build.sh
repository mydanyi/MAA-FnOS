#!/usr/bin/env bash
# 在 V100 服务器上构建 MAA-Web（纯套壳）镜像
# 用法: bash /home/<user>/maa-work/src/build.sh
set -euo pipefail

WORK=/home/<user>/maa-work
CTX=$WORK/build-ctx

echo "=== [1/4] 校验 MAA 官方包 ==="
gzip -t "$WORK/maa-linux.tar.gz" && echo "tarball OK"

echo "=== [2/4] 准备构建上下文 ==="
rm -rf "$CTX"
mkdir -p "$CTX"
cp -f "$WORK/maa-linux.tar.gz" "$CTX/"
cp -r "$WORK/src/MAA-WEB-CONTROL-master" "$CTX/"
cp -f "$WORK/src/Dockerfile" "$CTX/"
ls -la "$CTX"

echo "=== [3/4] docker build ==="
cd "$CTX"
docker build -t maa-web-control:local --build-arg MAA_TARBALL=maa-linux.tar.gz .
echo "=== [4/4] BUILD OK ==="
docker images maa-web-control:local --format "{{.Repository}}:{{.Tag}} {{.Size}}"
