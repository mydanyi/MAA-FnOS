# MAA (maa-web) fpk —— Bug 记录

> 记录人：小喵　｜　首次记录：2026-09-18 04:11 (GMT+8)
> 宿主：飞牛 fnOS `<NAS_IP>`　｜　应用版本：1.0.2
> 容器：`maa-web-test`（镜像 `maa-web-control:local`）
> 证据来源：`${TRIM_PKGVAR}/{info.log,install.log,uninstall.log}`、容器 stdout、容器内 `/app/data/runtime/maa/debug/asst.log`

---

## ~~BUG-001　`Fight` 任务链在 CE-6 关卡导航失败~~ 【已撤销 — 2026-09-18 04:15】

> **状态：撤销（非 bug）**。主人判定这不是程序缺陷，先取消，回头再看。
> 原分析与证据保留在下方仅供回溯，**不计入待修列表**。

**（原记录，保留备查）**

**严重度**：高 —— 直接影响日常理智作战，且失败后 run 仍继续，用户不易察觉。

**现象**：`daily-shoucai` profile 跑到 `Fight`（理智作战）时任务链报错。

**证据（asst.log 任务链时间线）**：
```
04:00:54  TaskChainStart  Fight (taskid=10)
04:00:55  StageBegin → 匹配 StageResource.png  score 0.931821  → 点击
04:01:06  CE-6@SwipeToTheLeft            → 滑动
04:01:08  匹配 StageCE.png  score 0.861026 → 点击
04:01:09..04:01:22  CE6@Stage  连续重试 20 次（cur_retry 0→20）全部未命中
04:01:23  SubTaskError(ProcessTask) + SubTaskError(StageNavigationTask)
04:01:23  TaskChainError  Fight
```

**辅助证据**：
- 失败瞬间原始截图 `debug/interface/2026.09.18-04.01.23.577_raw.png`（已取回本地 `diag/fight_error_0401.jpg`）。
  截图显示：**游戏停留在「资源收集」6 张卡片的分类总览页，并未进入 CE 的关卡列表**。
  其中「资源保障」(CE) 卡片为彩色可进入状态，标注「周一三五六开放」；「粉碎防御」「货物运送」显示「不可进入」。
  当天为**周五**，CE 开放 → **排除"关卡未开放"**。
- 日志内 2 条 `[WRN] correct_rect roi is empty, use whole image` → ROI 为空退化为全图匹配，命中率下降。

**已排除**：关卡未开放（周五 CE 开放）、ADB 不通（同期 `screencap` 稳定 112~151ms、adb 返回 0）、资源缺失（`/opt/maa/resource` 完整）。

**待确认**：该账号 CE-6 是否已解锁（若未通关 CE-5，列表内不存在 CE-6 属配置问题而非代码问题）。

**候选修因（按可能性排序）**：
1. 点击分类卡后页面跳转未发生（切换动画吃掉点击）→ 需在 StageNavigationTask 前加等待/重试跳转判定
2. `correct_rect` ROI 为空导致模板匹配逻辑退化
3. CE-6 未解锁，配置层应改用可用 stage 或开启 `use_alternate_stage` 回退

---

## BUG-002　应用/容器重启会硬切断进行中的任务链，前端状态错乱（确认存在）

**严重度**：高 —— 就是用户报的「运行着运行着它就没了 + 网页能开但任务状态全是错的」。

**证据**：
```
03:08:01.901  TaskChainStart  Infrast (taskid=3)   ← 之后再无 Completed
03:08:27      截图 2026.09.18-03.08.27.838_raw.png
03:08:27      info.log: "Stopping container maa-web-test"
```
`asst.log` 为跨运行 append 模式（首行是 22:38:50 的 `MaaCore Process Start` 横幅），可完整回溯。

**根因**：本次是调试期间为验证 1.0.2 镜像指纹逻辑做的受控重启，**属操作失误**。
机制层面：应用 stop 时运行中的 MaaCore 被直接杀掉，没有任何收尾/落盘；重启后前端持有的旧 `run_id` 失效，任务状态映射全部错位。

**修法方向**：
- 调试/运维规范：停应用前先查 `/api/status` 的 `state`，运行中则先优雅停任务
- 代码层：`cmd/main` 的 `stop` 前调用应用的停止接口；前端在 run_id 变更时清空并重建任务状态，而不是继续映射旧 id

---

## BUG-003　`/api/status.last_error` 不上报任务链错误（确认存在）

**严重度**：中 —— 让前端"看起来一切正常"，掩盖失败。

**证据**：04:01:23 `Fight` 已 `TaskChainError`，但 04:03 查询 `/api/status` 返回
```json
{"state":"Running","current_profile":"daily-shoucai","current_task":"award","total_tasks":6,"appended_tasks":6,"last_error":null}
```
`last_error` 仍为 `null`。

**修法方向**：`TaskChainError` 回调时写入 `last_error`（含 taskchain 名与时间），并广播到 `/api/events`。

---

## BUG-004　`/api/redroid/status` 默认容器名与实际不匹配（确认存在）

**严重度**：低 —— 仅影响"检查 redroid 容器"这一 UI 功能。

**证据**：
- `/api/redroid/status` → `{"available":false,"container":"redroid","message":"容器 redroid 不存在"}`
- 实际容器名：`<redroid-container>`
- 代理直连验证：`/inspect?name=<redroid-container>` → `{"ok":true,"status":"running","running":true}`（**白名单无问题**，正则为 `re.compile(r"redroid", re.I)`，含 redroid 即放行）

**根因**：应用侧默认容器名 hardcode 为 `redroid`。

**修法方向**：容器名做成可配置项，或支持从环境变量 `MAA_REDROID_CONTAINER` 注入默认值。

---

## BUG-005　容器名 `maa-web-test` 为开发期命名泄漏到线上（确认存在）

**严重度**：中 —— 影响交付信任，用户会误认为机器上被偷放了测试环境。

**证据**：`cmd/main` 第 7 行 `CONTAINER="maa-web-test"`；容器挂载 `${TRIM_PKGVAR}/maa-data`、
`RestartPolicy=no`、创建时间 `2026-09-18 03:10:21` 与 `info.log` 的 `Starting container` 同秒
→ 可确认该容器确由 fpk 的 `cmd/main` 创建，非额外部署。

**修法方向**：改名为 `maa-web`；**必须同时加一次性迁移**（新名字的 `stop_process` 不会清理旧名字容器，
需在首次 `start` / `install_callback` 里 `docker rm -f maa-web-test`）。

---

## BUG-006　`--restart no` 导致容器退出后不自愈（确认存在）

**严重度**：中 —— 用户会看到"应用显示运行中但什么都不工作"。

**证据**：`cmd/main` 第 186 行 `--restart no`；`docker inspect` → `RestartPolicy.Name = no`、`RestartCount = 0`。
`status` 分支只判断 `docker ps` 与 `PID_FILE`，无真实健康检查。

**修法方向**：改用 `--restart unless-stopped`，或在 `status` 里加 HTTP 探活（非 200 即返回非 0）。

---

## BUG-007　容器内 adb 僵尸进程未回收（确认存在）

**严重度**：低 —— 资源泄漏信号，长期运行可能积累。

**证据**：`docker exec maa-web-test ps -eo pid,ppid,etime,stat,cmd`
```
 78  1  43:31  0 [adb] <defunct>
167  1  10:50  0 [sh]  <defunct>
168  1  10:50  0 [adb] <defunct>
```
父进程均为 PID 1（uvicorn），说明应用未 `wait()` 回收子进程。

**修法方向**：`subprocess.Popen` 后统一 `wait()`/`communicate()`；或为 uvicorn 启用 `--init`（tini）做 PID 1 回收。

---

## BUG-008　桌面入口用 `type: url`，点击后在浏览器新开页签，未在飞牛桌面内打开（确认存在，待修）

**严重度**：中 —— 交互体验问题，与同类应用（ScrcpyNas）不一致。主人明确指出"这就不对"。

**证据（fnOS 应用中心数据库 `appcenter.app_service`，实测对比）**：

| 应用 | type | url | gateway_socket | gateway_prefix |
|---|---|---|---|---|
| `scrcpyNas.Application` | **iframe** | `://${host}/app/scrcpyNas` | `/var/apps/scrcpyNas/target/app.sock` | `/app/scrcpyNas` |
| `maa-web.Application` | **url** | `http://${host}:18000/` | （空） | （空） |

全库 `type='iframe'` 的入口共 5 条：`xunlei`、`trim.text-editor`、`trim.sync_server`、`baidu.netdisk`、`scrcpyNas`。

**机制**（官方文档 + 实测）：
- `type: "url"` → 新浏览器标签页打开；`type: "iframe"` → 在飞牛桌面内嵌窗口打开。
- iframe 走飞牛**统一网关**：nginx `location /app/` → `unix:/var/run/trim_http_cgi.socket`（见 `/usr/trim/nginx/conf/conf.d/trim_http_cgi.conf`），
  由网关按应用声明的 `gatewayPrefix` / `gatewaySocket` 转发到应用自己的 Unix Socket。
- 网关会把 `FNNAS_GATEWAY_SOCKET` / `FNNAS_GATEWAY_PREFIX` 传给应用；应用侧 socket 实际路径 = `${TRIM_APPDEST}/<name>.sock`
  （`/var/apps/<app>/target` 是指向 `/vol1/@appcenter/<app>` 的软链）。

**关键障碍（决定方案难度）**：MAA-WEB-CONTROL **完全不支持 URL 前缀**：
- `index.html` 里 55+ 处资源引用全是绝对路径（`/styles/*`、`/core/*`、`/tasks/*`、`/views/*`、`/newlogo.ico`）
- WebSocket 硬编码 `` WebSocket(`${protocol}//${location.host}/api/events`) ``
- `app/main.py` 用 `app.mount("/", NoCacheStaticFiles(...))`，无 `root_path`，代码内无 `X-Forwarded-Prefix` 支持

→ 若走 `gatewayPrefix: /app/maa-web`，浏览器会去 `http://{host}/styles/base.css` 取资源，必然 404，
  除非做「入站剥前缀 + 出站补前缀」的重写代理。

**候选方案（按改动量从小到大）**：
- **方案 A（最小，先试）**：`ui/config` 改 `"type": "iframe"`，保留 `protocol: http` / `port: 18000` / `url: "/"`。
  iframe 的 src 会成为 `http://{host}:18000/`，**绝对路径天然正确，无需任何重写**。
  风险：需实测 fnOS 是否允许 iframe 直接指端口（scrcpyNas 走的是网关而非端口）；若用户走 HTTPS 访问飞牛，http iframe 会被浏览器拦。
- **方案 B（对标 ScrcpyNas，改动大）**：写宿主侧「Unix Socket → `127.0.0.1:18000`」重写代理
  （入站剥 `/app/maa-web`、出站给 HTML/CSS/JS 里的绝对路径补前缀、注入 shim 兜住 `fetch`/`XHR`/`WebSocket`、转发 WS Upgrade），
  再配 `type: iframe` + `gatewaySocket: maa-web.sock` + `gatewayPrefix: /app/maa-web`。
- **方案 C**：fork MAA-WEB-CONTROL，把前端绝对路径改成相对路径 + 注入 `<base href>`，从上游解决；维护成本高。
- **方案 D**：保持现状（新开页签），仅在文档里说明。

**待办**：等主人选方案。方案 A 需一次 1.0.3 打包 + 安装实测（约 600MB 上传）。

---

## 附：环境残留清理项（非代码 bug，需主人确认后执行）

| 项目 | 位置 | 说明 |
|---|---|---|
| 悬空镜像 `a4eb6d20979e` | docker | 2.07GB，我多次重建镜像的中间产物 |
| 野代理进程 | `python3 /home/<user>/redroid_status_proxy.py`（PID 229604, 03:10:31 起） | 我调试时手起的副本，占着 18001，导致应用自带副本被 `ensure_redroid_proxy` 探活跳过 |
| 调试文件 | `/home/<user>/` | `docker`、`redroid_status_proxy.py`、`start_proxy.sh`、`maa-fpk/`、`maa-backup/`、`maafnos-skeleton/`、`maa-fpk-src.tar.gz`、`fnpack-build{,2,3}.log` |
| 早期垃圾 | `/home/<user>/` | `;`、`=`、`\`、`\\`、`cp`、`test`、`{{.Destination}}`、`583bf681…` 等空目录/空文件 —— **非本次产生，未动** |

> ⚠️ 清理原则：逐项列出 → 等主人确认 → 分批执行 → 每批验证。主人既有资产（其他容器/目录）一律不动。
