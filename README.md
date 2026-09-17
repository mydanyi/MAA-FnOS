# MAA-FnOS · MAA 飞牛版

把 [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights)（简称 **MAA**，明日方舟小助手）
搬进 [飞牛 fnOS](https://www.fnnas.com/)，以**原生 fpk 应用**的形式安装。

装完之后，飞牛桌面上会多一个 **MAA** 图标，点开就是完整的 MAA 网页控制台：配置任务、看实时日志、定时收菜、截图预览、一键更新核心。

> **纯套壳设计** —— 本项目**不改动上游 MAA-WEB-CONTROL 一行业务代码**。
> 飞牛这边只做三件事：把镜像导进 Docker、按生命周期起停容器、把 redroid 容器状态安全地透给容器内。

---

## 目录

- [这是什么](#这是什么)
- [架构](#架构)
- [前置条件](#前置条件)
- [安装](#安装)
- [首次使用](#首次使用)
- [目录结构](#目录结构)
- [构建](#构建)
- [配置项](#配置项)
- [已知问题](#已知问题)
- [排障](#排障)
- [致谢](#致谢)
- [许可证](#许可证)
- [免责声明](#免责声明)

---

## 这是什么

MAA 官方只有 Windows / macOS / Linux 桌面端，没有给 NAS 用的版本。
本项目做的事是：**把 MAA 官方 Linux 核心 + 一个 Web 前端塞进 Docker 镜像，再包成飞牛 fpk 应用**，
让你能从浏览器（甚至手机浏览器）使用 MAA。

跑起来的实际组成：

| 组件 | 来源 | 作用 |
|---|---|---|
| **MaaCore** | MAA 官方 Linux release | 真正干活的引擎：识图、模板匹配、任务决策 |
| **MAA-WEB-CONTROL** | 社区 Web 前端（AGPL-3.0-only） | 提供浏览器界面与 30+ 个 HTTP/WS 接口 |
| **adb + MaaTouch** | Debian/Ubuntu 包 + MAA 资源 | 连安卓端截图、注入点击 |
| **redroid 容器** | `erstt/redroid:13.0.0_ndk_ChromeOS` | 安卓运行环境（**需自行部署**） |
| **本项目的 fpk** | 就是本仓库 | 飞牛应用外壳：镜像导入 + 容器生命周期 |

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  浏览器（PC / 手机）                                          │
│    点飞牛桌面 MAA 图标 → http://<NAS_IP>:18000/               │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────────┐
│  飞牛 fnOS 应用框架                                            │
│    应用中心 → cmd/main start|stop|status                      │
│      ├─ check_docker        校验 docker 可用                   │
│      ├─ ensure_image        按「镜像指纹」决定是否重新导入      │
│      ├─ ensure_redroid_proxy 起宿主侧只读代理 :18001           │
│      └─ docker run  ──────────────────────────────┐           │
└───────────────────────────────────────────────────┼───────────┘
                                                    │
┌───────────────────────────────────────────────────▼───────────┐
│  容器 maa-web-test（镜像 maa-web-control:local, 1.15GB）        │
│    bash /app/run.sh → uvicorn app.main:app :8000               │
│    宿主 18000 → 容器 8000                                       │
│                                                                │
│    ├─ MAA-WEB-CONTROL  (FastAPI)   /app                        │
│    ├─ MaaCore v6.17.5              /opt/maa/libMaaCore.so      │
│    └─ 假 docker 脚本               /usr/local/bin/docker       │
│         └─ 转发到宿主只读代理 172.17.0.1:18001                 │
└──────────────┬──────────────────────────────┬─────────────────┘
               │ adb (TCP 5555)               │ 只读 HTTP
               │ 截屏 / MaaTouch 点击          │
┌──────────────▼──────────────┐   ┌───────────▼─────────────────┐
│  redroid 安卓容器            │   │  宿主侧 redroid_status_proxy │
│  <redroid-container>        │   │  仅支持 /inspect?name=…      │
│  └─ 明日方舟                 │   │  白名单：含 redroid 的名字    │
└─────────────────────────────┘   └─────────────────────────────┘
```

**为什么容器里要放一个"假 docker"？**
上游的「检查 redroid 容器」功能会在容器内执行 `docker inspect`。直接把 `docker.sock` 挂进容器
等于给出 root 权限，不可接受。所以改成：容器内放一个只认识**一条命令**的假 docker，
它去问宿主机上一个**只读、白名单、只支持 inspect** 的 HTTP 代理。
既满足了功能，又把权限收得最小。

---

## 前置条件

| 项 | 要求 |
|---|---|
| 飞牛 fnOS | 版本 ≥ 1.1.3100，已安装 **Docker** 应用 |
| 架构 | x86_64 |
| 安卓环境 | 一个可用的 **redroid** 容器（或任意能被 `adb connect` 的安卓设备/模拟器） |
| 磁盘 | 约 3GB（镜像 1.15GB + fpk 内离线镜像 585MB + 数据） |

> 没装 redroid？redroid 需要内核 binder 支持，飞牛社区有现成方案。
> 也可以用任意安卓虚拟机、甚至真机（开启无线 adb）替代。

---

## 安装

```bash
# 1) 把 maa-web.fpk 传到 NAS，例如 /home/<user>/
# 2) 安装（--volume 1 表示装到存储空间 1）
sudo appcenter-cli install-fpk --volume 1 /home/<user>/maa-web.fpk
```

安装过程中会自动把内置的离线镜像导入 Docker（约 30 秒）。
装完后在飞牛应用中心里点 **启动**，再点桌面上的 **MAA** 图标。

打开地址：`http://<NAS_IP>:18000/`

### 升级

```bash
sudo appcenter-cli uninstall maa-web     # 先卸载（用户数据会保留）
sudo appcenter-cli install-fpk --volume 1 /home/<user>/maa-web-1.0.3.fpk
```

> ⚠️ **升级必须递增 `fnos-app/manifest` 里的 `version`**，
> 否则 `install-fpk` 会认为"同版本已安装"而跳过文件覆盖。详见 [docs/飞牛开发笔记.md](docs/飞牛开发笔记.md)。

---

## 首次使用

1. **设置安卓连接**
   打开网页 → *设置 → 连接*，把 ADB 地址填成 redroid 的地址，例如 `<NAS_IP>:5555`。
   （redroid 容器的 5555 端口要映射到宿主机，形如 `-p 5555:5555`）

2. **接上 MaaTouch**
   触摸模式选 `MaaTouch（实验功能）`，MAA 会自动把 `MaaTouch.App` 推进安卓端并拉起，
   比默认的 `adb shell input` 更快更稳。

3. **配一个任务档案（Profile）**
   仓库里带的默认档案是示例，请按自己的账号改：关卡、基建换班、公招标签等。
   页面上的 *开始唤醒 / 自动公招 / 基建换班 / 理智作战 / 信用收支 / 领取奖励* 逐个开关即可。

4. **点运行**，然后在 *日志* 页看实时输出。

---

## 目录结构

```
MAA-FnOS/
├── README.md                       # 本文件
├── CHANGELOG.md                    # 版本变更
├── BUGS.md                         # 已知问题清单（含证据与修复方向）
├── fnos-app/                       # ★ fpk 应用源码（fnpack build 的工作目录）
│   ├── manifest                    #   应用元信息（版本/名称/图标声明/变更日志）
│   ├── ICON.PNG                    #   应用中心图标 64x64
│   ├── ICON_256.PNG                #   应用中心图标 256x256
│   ├── assemble.sh                 #   组装 fpk 的辅助脚本
│   ├── cmd/                        #   生命周期脚本
│   │   ├── main                    #     start / stop / status（核心）
│   │   ├── install_init / _callback
│   │   ├── upgrade_init / _callback
│   │   ├── uninstall_init / _callback
│   │   └── config_init / _callback
│   ├── config/
│   │   ├── privilege               #   运行身份 + 加入 docker 组
│   │   └── resource                #   共享目录声明
│   └── app/                        #   → 安装后摊平到 ${TRIM_APPDEST}
│       ├── maa-image.tar.gz        #     （不进仓库，见 .gitignore）离线镜像
│       ├── redroid_status_proxy.py #     宿主侧 redroid 只读代理
│       └── ui/
│           ├── config              #     桌面入口配置
│           └── images/             #     12 个尺寸的桌面图标
├── redroid-proxy/
│   ├── docker                      #   容器内「假 docker」脚本
│   └── redroid_status_proxy.py     #   同 fnos-app/app/ 下的那份（便于单独部署）
├── deploy/                         # 独立 Docker 部署（不走飞牛也能用）
│   ├── Dockerfile                  #   镜像构建
│   ├── build.sh                    #   一键构建
│   ├── docker-compose.yml          #   compose 方式起容器
│   ├── ctl.sh                      #   裸 docker 起停
│   ├── make_icons.py               #   生成各尺寸图标
│   └── probe_maa.py                #   验证 MaaCore Python 绑定
├── docs/
│   ├── 构建指南.md
│   ├── 排障手册.md
│   └── 飞牛开发笔记.md
└── tools/                          # 运维辅助脚本（需自备凭据，见下）
```

> **仓库里没有的东西**：`maa-image.tar.gz`（585MB）与打包好的 `maa-web.fpk`（约 613MB）。
> GitHub 单文件上限 100MB，且这类二进制不适合进 Git。请按 [docs/构建指南.md](docs/构建指南.md) 自行构建。

---

## 构建

完整步骤见 **[docs/构建指南.md](docs/构建指南.md)**，简版：

```bash
# ① 拉两个上游产物
#    MAA 官方 Linux release  → maa-linux.tar.gz
#    MAA-WEB-CONTROL 源码     → MAA-WEB-CONTROL-master/

# ② 构建镜像（重活建议丢到有 Docker 的机器上）
bash deploy/build.sh

# ③ 导出并压缩镜像
docker save maa-web-control:local | gzip -9 > maa-image.tar.gz

# ④ 组装 fpk
cp maa-image.tar.gz fnos-app/app/
cd fnos-app && fnpack build

# ⑤ 安装
sudo appcenter-cli install-fpk --volume 1 maa-web.fpk
```

---

## 配置项

### 传给容器的环境变量（在 `fnos-app/cmd/main` 里设定）

| 变量 | 值 | 说明 |
|---|---|---|
| `MAA_ADAPTER` | `official` | 用真实 MaaCore；改成 `dryrun` 则为空跑模式 |
| `MAA_CORE_DIR` | `/opt/maa` | 官方核心包根目录（含 `lib/ resource/ Python/`） |
| `MAA_WEB_HOST` | `0.0.0.0` | Web 服务监听地址 |
| `MAA_WEB_PORT` | `8000` | 容器内端口（宿主映射到 18000） |
| `TZ` | `Asia/Shanghai` | 时区，影响日志与定时任务 |
| `REDROID_PROXY_HOST` | `172.17.0.1` | 宿主侧代理地址（docker bridge 网关） |
| `REDROID_PROXY_PORT` | `18001` | 宿主侧代理端口 |

### 宿主侧可调项（`fnos-app/cmd/main` 顶部）

```bash
IMAGE="maa-web-control:local"   # 镜像名
CONTAINER="maa-web-test"        # 容器名（见 BUGS.md #5，计划改名为 maa-web）
HOST_PORT="18000"               # 宿主端口
CONTAINER_PORT="8000"           # 容器端口
```

### 数据持久化

任务档案、日志、截图都在 `${TRIM_PKGVAR}/maa-data`（即 `/vol1/@appdata/maa-web/maa-data`），
挂进容器的 `/app/data`。**卸载、升级、重装都不会丢**，要清空请手动删这个目录。

---

## 已知问题

清单在 **[BUGS.md](BUGS.md)**，含复现证据与修复方向。当前待修的主要是：

| # | 严重度 | 问题 |
|---|---|---|
| 2 | 高 | 应用/容器重启会硬切断进行中的任务链，网页任务状态错乱 |
| 3 | 中 | `/api/status.last_error` 不上报任务链错误 |
| 5 | 中 | 容器名 `maa-web-test` 是开发期命名，观感像测试环境常驻 |
| 6 | 中 | `--restart no`，容器退出后不会自愈，且 `status` 无真实健康检查 |
| 8 | 中 | 桌面入口用 `type: url`，点击后新开浏览器页签，而不是在飞牛桌面内开窗口 |

> ⚠️ **操作提醒**：应用**运行任务期间不要重启容器/应用**，否则正在跑的任务会被直接掐断（#2）。

---

## 排障

完整版见 **[docs/排障手册.md](docs/排障手册.md)**。最常用的三条：

```bash
# 应用生命周期日志（谁把容器停了、镜像导没导）
sudo cat /vol1/@appdata/maa-web/info.log

# 容器输出
sudo docker logs --tail 200 maa-web-test

# MaaCore 引擎日志（跨运行追加，可回溯历史）
sudo docker exec maa-web-test tail -n 200 /app/data/runtime/maa/debug/asst.log
```

**任务链时间线速查**（找"有开始没结束"的那一条 = 被掐断的）：

```bash
sudo docker exec maa-web-test sh -c \
  "grep -nE 'TaskChain(Start|Completed|Error)' /app/data/runtime/maa/debug/asst.log | tail -30"
```

---

## 致谢

- [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) —— MAA 官方核心，本项目的灵魂
- MAA-WEB-CONTROL —— 优秀的社区 Web 前端，本项目**未改其一行代码**
- [redroid](https://github.com/remote-android/redroid-doc) —— 容器里的安卓
- [ScrcpyNas](https://github.com/) —— 飞牛生态里的前辈，本项目在「飞牛桌面入口」与「统一网关」上参考了它的做法

---

## 许可证

⚠️ **待确认（请仓库主人定稿）**

- 本仓库中的 **fpk 外壳脚本与文档**：暂未声明许可。
- 但本项目**分发的 Docker 镜像内含 AGPL-3.0-only 的 MAA-WEB-CONTROL**，
  因此**整体的分发与再分发需遵守 AGPL-3.0**。
- MaaCore 及资源文件版权归 MAA 项目所有，遵循其自身协议。

在定稿前，请把本仓库视为「源码可见」而非「已授权」。

---

## 免责声明

本项目仅用于**个人账号的自动化辅助**，不修改游戏、不提供游戏内容、不绕过任何付费。
使用自动化工具可能违反游戏用户协议，**风险由使用者自行承担**。
请勿用于商业用途、代练、账号交易等场景。
