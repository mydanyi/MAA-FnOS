# MAA-FnOS

我一直在用 [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights)（MaaAssistantArknights，明日方舟小助手）帮我挂日常。
它只有 Windows / macOS / Linux 的桌面版，而我的机器常年开着的是那台飞牛 NAS，
每次都得远程桌面连过去点一下，麻烦得很。

所以就动手把 MAA 搬到了飞牛上，做成一个可以直接装的应用。装完之后桌面上会多一个 **MAA** 图标，
点开是完整的网页控制台：配任务、看实时日志、定时收菜，手机浏览器打开也能用。

---

## 它是由什么组成的

MAA 本身是桌面程序，没法直接塞进 NAS。我的做法是把这几样东西装进一个 Docker 镜像，再包成飞牛的 fpk 应用：

| 部分 | 来源 | 干什么的 |
|---|---|---|
| MaaCore | MAA 官方 Linux 版 | 真正干活的引擎，认图、判断、决策 |
| MAA-WEB-CONTROL | 社区的 Web 前端 | 浏览器界面和接口 |
| adb + MaaTouch | 系统包 + MAA 资源 | 连安卓端截图、模拟点击 |
| redroid | [ERSTT/redroid](https://github.com/ERSTT/redroid) 的 `erstt/redroid:13.0.0_ndk_ChromeOS` | 跑游戏的安卓环境（要自己先准备好） |
| fpk 外壳 | 这个仓库 | 把镜像导进 Docker，管容器的启停 |

## 架构

```
浏览器（电脑 / 手机）
  点飞牛桌面的 MAA 图标 → http://<NAS_IP>:18000/
        │
        ▼
飞牛 fnOS 应用框架
  cmd/main start|stop|status
    ├─ 检查 docker
    ├─ 需要的话导入镜像
    ├─ 拉起 redroid 状态代理（宿主侧 :18001）
    └─ docker run
        │
        ▼
容器 maa-web（镜像 maa-web-control:local，1.15GB）
  bash /app/run.sh → uvicorn :8000    宿主 18000 → 容器 8000
    ├─ MAA-WEB-CONTROL (FastAPI)      /app
    ├─ MaaCore v6.17.5                /opt/maa/libMaaCore.so
    └─ 一个假的 docker 命令           /usr/local/bin/docker
        │
        ├── adb (5555) ──► redroid 容器 ──► 明日方舟
        │
        └── 只读 HTTP ──► 宿主侧 redroid 状态代理
```

容器里那个「假的 docker」是这么来的：MAA 的网页端有个「检查 redroid 容器」的功能，
它会在容器里执行 `docker inspect`。要让它真的能用，最直接的办法是把 `docker.sock` 挂进容器——
那等于把宿主的 root 权限交出去，我不想这么干。所以改成放一个只认识这一条命令的假脚本，
它去问宿主机上一个只读的、带白名单的 HTTP 代理。功能有了，权限还是收着的。

## 前置条件

- 飞牛 fnOS，版本 1.1.3100 以上，装好 Docker
- x86_64 架构的机器
- 一个能用的安卓环境。我用的是 redroid 容器，镜像是 `erstt/redroid:13.0.0_ndk_ChromeOS`，
  怎么起见下面的[安卓环境](#安卓环境redroid)；任何能被 `adb connect` 连上的安卓设备或模拟器也都可以
- 大概 3GB 硬盘（镜像 1.15GB + 安装包 585MB + 运行数据）

## 安装

到 [Releases](https://github.com/mydanyi/MAA-FnOS/releases) 下载 `maa-web.fpk`（包里自带离线镜像，不用自己构建），传到 NAS，然后：

```bash
sudo appcenter-cli install-fpk --volume 1 /home/<user>/maa-web.fpk
```

安装的时候会自动把内置的镜像导进 Docker，半分钟左右。
装完在应用中心点启动，再点桌面上的 MAA 图标就能打开了。

地址是 `http://<NAS_IP>:18000/`。

### 升级

```bash
sudo appcenter-cli uninstall maa-web
sudo appcenter-cli install-fpk --volume 1 /home/<user>/maa-web-新版本.fpk
```

改包的时候记得把 `fnos-app/manifest` 里的 `version` 往上加一位。
飞牛发现版本号没变会跳过文件覆盖，你会以为更新没生效，其实是根本没装上去。

任务档案、日志、截图都存在 `/vol1/@appdata/maa-web/maa-data`，
卸载和重装都不会动它，想清空就自己删这个目录。

## 用起来

1. **连安卓端**
   网页里进 *设置 → 连接*，ADB 地址填 redroid 的地址，比如 `<NAS_IP>:5555`。
   容器的 5555 端口记得映射到宿主上。

2. **触摸方式选 MaaTouch**
   MAA 会自己把 `MaaTouch.App` 推进安卓端并拉起来，比默认的 `adb shell input` 快也更稳。

3. **调任务档案**
   仓库里带的档案只是示例，关卡、基建换班、公招标签这些得按自己账号改。
   页面上 开始唤醒 / 自动公招 / 基建换班 / 理智作战 / 信用收支 / 领取奖励 这些开关按需打开就行。

4. **点运行**，然后去日志页看它干活。

## 自己构建

完整步骤在 [docs/构建指南.md](docs/构建指南.md)，简单说就四步：

```bash
# 1. 准备两个上游产物
#    MAA 官方 Linux release → maa-linux.tar.gz
#    MAA-WEB-CONTROL 源码   → MAA-WEB-CONTROL-master/

# 2. 构建镜像（建议丢到别的有 Docker 的机器上做）
bash deploy/build.sh

# 3. 导出并压缩
docker save maa-web-control:local | gzip -9 > maa-image.tar.gz

# 4. 打包安装
cp maa-image.tar.gz fnos-app/app/
cd fnos-app && fnpack build
sudo appcenter-cli install-fpk --volume 1 maa-web.fpk
```

官方 MAA 包要求 glibc ≥ 2.38，基础镜像得用 Ubuntu 24.04 或更新的。

## 不用飞牛：直接跑 Docker

不装 fpk 也行。`deploy/` 里就是独立部署那一套，单容器，一个 compose 起：

| 文件 | 干什么的 |
|---|---|
| `deploy/Dockerfile` | 镜像定义：Ubuntu 24.04 + MAA 官方 Linux 包 + MAA-WEB-CONTROL（原样） |
| `deploy/docker-compose.yml` | 单服务 compose，端口 `18000:8000`，数据挂在卷 `maa-data` |
| `deploy/ctl.sh` | 不想用 compose 就用它，等价的 `docker run` 写法 |
| `deploy/build.sh` | 只负责构建镜像（里面的目录变量要改成自己的） |

compose 里的 `build:` 指的就是同一个 Dockerfile，所以不用先手工 build 一遍。

跟 fpk 的区别：fpk 走飞牛应用框架，能在应用中心安装启停、有桌面图标，数据在
`/vol1/@appdata/maa-web/maa-data`；compose 就是个普通容器，数据在 Docker 卷里，
应用中心看不到它。

### 起法

Dockerfile 要的构建上下文里有三样上游产物，所以不能在本仓库里直接 `up`，
得先按 [docs/构建指南.md](docs/构建指南.md) 把上下文拼出来：

```bash
mkdir -p ~/maa-build && cd ~/maa-build
cp -r /path/to/MAA-FnOS/deploy .          # Dockerfile 和 compose 都在里面
cp -r /path/to/MAA-FnOS/redroid-proxy .   # Dockerfile 要 COPY 它
cp /path/to/maa-linux.tar.gz .
cp -r /path/to/MAA-WEB-CONTROL-master .

docker compose up -d --build
```

起来的地址一样是 `http://<宿主机IP>:18000/`。

还有一步：容器里那个「检查 redroid 容器」要能用，得在**宿主**上跑状态代理
（`redroid-proxy/redroid_status_proxy.py`，监听 `172.17.0.1:18001`）。
fpk 那边是 `cmd/main` 顺手拉起来的，compose 这条路得自己起。

## 安卓环境：redroid

MAA 得有个安卓端才能干活，我用的是容器化的安卓：

| 项 | 值 |
|---|---|
| 镜像 | `erstt/redroid:13.0.0_ndk_ChromeOS` |
| 上游 | [ERSTT/redroid](https://github.com/ERSTT/redroid)（Docker Hub 上叫 [`erstt/redroid`](https://hub.docker.com/r/erstt/redroid)） |
| 是什么 | redroid（Android 13）+ NDK Translation 0.2.3 转译层，基于 ChromeOS skyrim R134 |
| 大小 | 2.07GB |

**为什么不用官方 redroid**：明日方舟的新引擎把 x86 的 so 去掉了，纯 x86 的安卓镜像跑不起来。
ERSTT 这套是给 redroid 补了 Houdini / NDK 转译的，x86_64 机器上也能跑 ARM 应用；
上游对这个 tag 的标注是「Verified stable on Intel / AMD platforms」。

我这边是一个 compose 起单容器：

```yaml
services:
  redroid:
    image: erstt/redroid:13.0.0_ndk_ChromeOS
    container_name: redroid-cos13
    tty: true
    stdin_open: true
    privileged: true
    devices:
      - /dev/dri
      - /dev/binder
    networks:
      - main
    ports:
      - 5555:5555
    volumes:
      - /path/to/redroid-cos13/data:/data
    command:
      - androidboot.redroid_gpu_mode=host
      - androidboot.use_memfd=1
networks:
  main:
    driver: bridge
    name: main
```

几个点：

- `privileged: true` 是必须的，redroid 要用
- `/dev/binder` 是安卓的必需项，`/dev/dri` 是给 GPU 加速用的。我这台飞牛上
  `/dev/binder` 已经指向 `/dev/binderfs/binder`，`/dev/dri` 里有 `renderD128`，都是现成的
- `androidboot.redroid_gpu_mode=host` 走 GPU 加速；机器上没有可用 GPU 就改成 `guest`（软件渲染）
- `5555` 就是 MAA 里要填的 ADB 端口，所以填 `<NAS_IP>:5555`
- 容器名带不带前缀都没关系，MAA 只是拿这个名字去查状态（状态代理按名字里有没有 `redroid` 认）

> 上游还提了一条针对方舟的建议：只保留 `arm64-v8a`、去掉 `armeabi-v7a` 和 `armeabi` 会更稳
> （否则方舟有可能落到 32 位 ARM 转译上）。做法是在 `command:` 里补三行：
> `ro.product.cpu.abilist=x86_64,x86,arm64-v8a`、
> `ro.product.cpu.abilist32=x86`、
> `ro.product.cpu.abilist64=x86_64,arm64-v8a`。
> 我这份没加，因为我这边跑着没出问题；你要是遇到方舟花屏或者起不来，可以试试。

## 目录

```
MAA-FnOS/
├── fnos-app/            fpk 应用的源码，fnpack build 就在这个目录里跑
│   ├── manifest         应用信息
│   ├── cmd/             start / stop / status 和安装升级卸载钩子
│   ├── config/          运行身份、共享目录声明
│   └── app/             安装后这部分会摊到 /vol1/@appcenter/maa-web
│       └── ui/          桌面图标和入口配置
├── redroid-proxy/       容器内的假 docker + 宿主的只读代理
├── deploy/              不走飞牛时的独立 Docker 部署方式
└── docs/                构建指南
```

## 配置

跑起来之后容器的环境变量在 `fnos-app/cmd/main` 里设：

| 变量 | 值 | 说明 |
|---|---|---|
| `MAA_ADAPTER` | `official` | 用真的 MaaCore，换成 `dryrun` 就是空跑 |
| `MAA_CORE_DIR` | `/opt/maa` | 官方核心包的位置 |
| `MAA_WEB_HOST` | `0.0.0.0` | Web 服务监听地址 |
| `MAA_WEB_PORT` | `8000` | 容器内端口，宿主映射到 18000 |
| `TZ` | `Asia/Shanghai` | 时区，会影响日志和定时任务 |
| `REDROID_PROXY_HOST` | `172.17.0.1` | 宿主侧代理 |
| `REDROID_PROXY_PORT` | `18001` | 宿主侧代理端口 |

端口、容器名、镜像名都在这个文件的开头几行，想改直接改。

## 反馈与交流

用着有问题、有想法，或者只是想找人聊聊天，都可以来群里找我。

- QQ 粉丝群：**487945399**
- QQ 养老群：**477426414**

## 致谢

引擎、界面、安卓环境都是现成的，我只是把它们拼到一起。

- [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) —— MAA 官方核心
- [MAA-WEB-CONTROL](https://github.com/KlN-4096/MAA-WEB-CONTROL) —— 网页控制台，界面和接口都来自这里
- [redroid](https://github.com/remote-android/redroid-doc) —— 容器里的安卓
- [ERSTT/redroid](https://github.com/ERSTT/redroid) —— 我用的那个 redroid 镜像
  （`erstt/redroid:13.0.0_ndk_ChromeOS`，带了 ARM / NDK 转译，官方镜像跑不了方舟）

## 许可证

[AGPL-3.0](LICENSE)，跟上游 [MAA-WEB-CONTROL](https://github.com/KlN-4096/MAA-WEB-CONTROL) 保持一致。
MaaCore 和游戏资源文件的版权归 MAA 项目所有，遵守它们各自的协议。

## 免责声明

这是我给自己用的小工具，只做个人账号的自动化辅助，不改游戏、不提供游戏内容。
用自动化工具可能违反游戏的用户协议，风险请自己评估。
别拿去做商业用途、代练或者账号交易。
