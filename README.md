# Music Player FlowSystem

CORD 门店屏幕本机一体化系统。

第一版由同一台 macOS 或 Windows 电脑运行：

- `/display`：门店屏全屏 HTML（横屏）；
- `/admin`：独立的配置 HTML；
- 本地服务：曲目信息、显示状态、配置和调度；
- SQLite 与本地素材：离线可用。

macOS 与 Windows 真实数据源均已实机跑通。显示与配置能力正在按 [docs/DISPLAY_REQUIREMENTS.md](docs/DISPLAY_REQUIREMENTS.md)（权威需求）重构，开发批次见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。本文件中显示相关描述如与需求文档冲突，**以需求文档为准**。

## 启动

需要 Python 3.9 或更高版本，不需要安装第三方依赖。

```bash
python3 run.py
```

启动后打开：

- 显示端：<http://127.0.0.1:8765/display>
- 配置端：<http://127.0.0.1:8765/admin>
- 健康检查：<http://127.0.0.1:8765/health>

macOS 可以双击 `start-macos.command`，Windows 可以双击 `start.bat`。两个入口都会自动选择本机真实数据源。

macOS 首次启用 QQ音乐、网易云等系统级播放器前，运行一次：

```bash
./scripts/setup-macos-mediaremote.sh
```

该脚本把固定版本的读取工具安装在项目自己的 `.tools/`，不会写入 `/usr/local`。如果工具不存在或失效，服务仍会自动退回 Apple Music/Spotify 的 AppleScript 数据源。

开发机需要保持 mock 数据时运行：

```bash
python3 run.py --open
```

手动指定数据源：

```bash
python3 run.py --source mock
python3 run.py --source macos
python3 run.py --source windows
python3 run.py --source auto
```

## 双平台结构

display、admin、API、状态协议、调度器和 SQLite 数据库由两端共用；平台差异只放在 `app/sources/` 和部署脚本中。

| 平台 | 第一版真实数据源 | 当前范围 |
|---|---|---|
| macOS | 系统 MediaRemote，AppleScript 降级 | QQ音乐、网易云及其他出现在控制中心的播放器；Apple Music/Spotify 另有直接降级路径 |
| Windows | 现有 `get_music_powershell.py`，通过 SMTC | 标题、音乐人、专辑、播放状态、封面和 SMTC 时间线；时间线需 Windows 实机验收 |
| 两端 | mock | 设计、调度和异常场景测试 |

macOS 第一次走 AppleScript 降级读取 Apple Music 或 Spotify 时，系统可能要求允许终端或运行程序控制对应播放器。拒绝后系统会保留显示页面，并在 admin 显示数据源错误。

## 左侧视觉配置

在 `/admin` 的“左侧视觉素材”中可以统一选择：

- 跟随当前歌曲的专辑封面；
- 上传或填写一张自定义图片；
- 上传或填写一段静音循环视频。

本机上传的素材存放在 `media/`，单个文件上限为 250 MB；图片支持 PNG/JPG/WebP/GIF/SVG，视频支持 MP4/WebM/MOV/M4V。当前选择保存在 `data/runtime-config.json`，服务重启后继续生效。左侧素材的比例白名单与缩放规则以 [docs/DISPLAY_REQUIREMENTS.md](docs/DISPLAY_REQUIREMENTS.md) 为准（不再限定正方形裁切）。该配置属于共用前端，与 macOS MediaRemote 或 Windows SMTC 数据源无关。

## 显示场景

`/display` 的显示场景与布局规格以 [docs/DISPLAY_REQUIREMENTS.md](docs/DISPLAY_REQUIREMENTS.md) 为准，当前规划为四场景：

- 正在播放（now_playing）：左侧视觉 + 右侧曲目信息；命中登记音乐人时右侧追加 Artist in Town 增量信息，命中期间常挂；左侧支持专辑封面/自定义图/视频，够长的曲子可在中段临时插播素材；
- 门店推荐（promotion）：近全屏单图；
- 门店活动（store_event）：近全屏单图，与门店推荐并行、曲末随机混播；
- 门店宣传（ambient）：常驻全屏图/视频，后台手动切入切出。

全屏场景按素材与屏幕比例智能选择 cover/contain，contain 留白由前端取色补边（相近色/对比色两套方案，详见需求文档）。

> 说明：上述为规划中的目标形态，具体实现进度见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。

## 音乐人演出表和自动匹配

`/admin` 的“音乐人演出表”可以新增、编辑、启用 / 停用、预览和删除演出。数据保存在本机 `data/cord-screen.db`，macOS 与 Windows 共用同一结构。

每条记录包含音乐人标准名、别名、演出日期和展示日期、时间、场地、城市、生效区间、优先级及内部来源备注。系统读取当前曲目的 `artist` 后：

- 忽略大小写、全角 / 半角差异和常见标点；
- 将 `&`、`feat.`、`/`、`×` 等合作署名拆开匹配；
- 只选择已启用且在生效区间内的记录；
- 同时命中多条时，先看优先级，再选择日期较近的记录；
- 命中时显示 Artist in Town，未命中或停止播放时显示普通播放界面；
- 未填写停止提示日期时，演出日期当天结束后自动失效。

手动预览不会改变演出表，结束后点击“恢复自动运行”即可回到实际运行状态。

## 豆子 / 活动内容库

`/admin` 的“豆子／活动内容库”允许同时维护任意多条记录。每条记录可独立设置内容类型、后台名称、展示文案、可选图片、启用状态、生效日期、优先级和单次展示秒数，数据同样保存在 `data/cord-screen.db`。

图片可以直接从本机上传，也可以填写 `/media/…` 或 `https://…` 地址。门店推荐（promotion）与门店活动（store_event）为并行两类内容，均以近全屏单图形式展示，缩放与背景填充规则以 [docs/DISPLAY_REQUIREMENTS.md](docs/DISPLAY_REQUIREMENTS.md) 为准。旧版 `runtime-config.json` 中的单条豆子 / 活动内容会在首次启动新版时迁移为内容库的第一条记录；迁移只执行一次，之后删除记录不会被旧配置重新生成。

内容可逐条新增、编辑、启用 / 停用、预览和删除。旧版 `runtime-config.json` 中的单条豆子 / 活动内容会在首次启动新版时迁移为内容库的第一条记录；迁移只执行一次，之后删除记录不会被旧配置重新生成。

“预览”会立即把指定记录送到显示端；自动运行时，调度器会在歌曲自然结束后，从已启用且处于生效区间内的记录中按优先级顺序轮换，并采用每条记录自己的展示秒数。

## 曲间自动插播

后台“曲间插播规则”可配置是否启用、自动插播最小间隔，以及每小时非音乐画面的占比上限。触发与保护规则如下：

- 上一首接近结尾，随后停止或切换到下一首，才判定为自然结束；
- 暂停和歌曲中段手动切歌不会触发；
- 插播期间继续接收最新曲目信息，但不提前中断画面；
- 到达该内容的展示秒数后，自动返回当时最新的曲目或 Artist in Town；
- 播放器不提供当前位置时，如果系统已完整观察到接近一首歌的总时长，可使用保守估算；既无位置也无总时长时不会猜测曲终。

后台“模拟自然结束”按钮可直接测试完整流程，不需要等待当前歌曲真实播放完。

## 已完成的阶段范围

- 同一服务提供 display/admin 两个独立 HTML 入口；
- 默认使用 mock 曲目状态；双平台真实数据适配层已经建立；
- admin 修改曲目或播放状态后，通过 SSE 实时推送到 display；
- 服务无外网也可以运行；
- 已完成 macOS Apple Music、QQ音乐真实抓取验收；Windows SMTC 已实机跑通，网易云仍待实机验收；
- 已完成当前的显示场景骨架、后台手动预览、内容保存和图片 / 视频 / 专辑封面兼容（四场景重构按需求文档进行中）；
- 已完成 SQLite 音乐人演出表及 Artist in Town 自动匹配；
- 已完成 SQLite 豆子 / 活动多记录内容库及逐条预览；
- 已完成自然曲终识别、豆子 / 活动自动轮换、定时回切、最小间隔和小时占比限制；
- 品牌内容、每日次数上限、Windows 时间线实机验收和长时间加速模拟尚未完成。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
