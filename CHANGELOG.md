# 变更日志

本项目版本号对应 `fnos-app/manifest` 里的 `version`。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [1.0.2] — 2026-09-18

### 修复
- **升级时旧镜像阻挡新镜像**（重要）
  `cmd/main` 的 `ensure_image()` 原先只判断「同名镜像是否存在」。
  由于 `docker load` 不会自动顶掉同名同 tag 的旧镜像，升级后旧镜像仍在，
  导致**新镜像永远不会被导入**，容器一直跑老版本。
  改为**镜像指纹比对**：把已导入镜像的 `docker image inspect --format '{{.Id}}'`
  写入 `${TRIM_APPDEST}/maa-image.id`，启动时比对；不一致就先 `docker rmi -f` 再重新导入。

### 变更
- `manifest` 版本号 1.0.1 → 1.0.2

---

## [1.0.1] — 2026-09-18

### 新增
- **redroid 状态查询代理**，修复「检查 redroid 容器」报「未找到 docker 命令」的问题：
  - 宿主侧：`redroid_status_proxy.py` 监听 `172.17.0.1:18001`，只读、白名单、仅支持 `/inspect?name=<容器>`
  - 容器侧：`/usr/local/bin/docker` 假脚本，只接受一条 `docker inspect --format …` 命令
  - **不挂载 `docker.sock`**，遵循最小权限原则
- 桌面图标补全至 12 个尺寸（16/24/32/48/64/72/96/128/144/256/512 + `icon_{0}.png`）

### 变更
- `manifest` 版本号 1.0.0 → 1.0.1

---

## [1.0.0] — 2026-09-17

### 新增
- 首个版本。把 MAA 官方 Linux 核心 + Web 前端打包成飞牛 fpk 应用：
  - 纯套壳：不改上游一行业务代码
  - 内置离线镜像（gzip 压缩的 `docker save` 产物），安装时自动导入，**无需联网**
  - `cmd/main` 完整生命周期：`start` / `stop` / `status`
  - 数据持久化到 `${TRIM_PKGVAR}/maa-data`，卸载重装不丢
