# macOS / Windows 双平台维护约定

## 原则

只维护一套产品核心：

- 同一套 `/display` 和 `/admin` HTML；
- 同一套 API、状态协议、调度规则、内容模型和 SQLite 数据；
- 同一套显示场景与动效逻辑（场景规格以 [DISPLAY_REQUIREMENTS.md](./DISPLAY_REQUIREMENTS.md) 为准）；
- 平台相关代码只放在曲目数据源和部署启动层。

禁止复制出 `mac-version`、`windows-version` 两套长期分叉代码。

## 目录边界

| 目录/文件 | 是否共用 | 职责 |
|---|:---:|---|
| `frontend/` | 是 | display/admin HTML、CSS、JS |
| `app/server.py` | 是 | 本地服务和 API |
| `app/state_store.py` | 是 | 统一状态协议 |
| `app/sources/base.py` | 是 | TrackSource 接口 |
| `app/sources/macos.py` | 否 | 【macOS 专用】MediaRemote 系统级读取＋Apple Music/Spotify 降级 |
| `app/sources/windows.py` | 否 | 【Windows 专用】Windows SMTC 包装，调用 vendor 采集脚本 |
| `app/sources/vendor/get_music_powershell.py` | 否 | 【Windows 专用】项目内自包含的 SMTC 采集脚本（PowerShell 实现），由 windows.py 调用 |
| `.tools/nowplaying-cli/` | 否 | 【macOS 专用】MediaRemote 命令行工具，由 macos.py 调用 |
| `start-macos.command` | 否 | macOS 启动入口 |
| `start.bat` | 否 | Windows 启动入口 |

## 每轮验收矩阵

| 项目 | macOS | Windows |
|---|:---:|:---:|
| API 与状态协议自动测试 | 必须 | 必须 |
| display/admin 页面 | 必须 | 必须 |
| mock 全流程 | 必须 | 必须 |
| 真实曲目信息 | 平台实机 | 平台实机 |
| 播放位置与时长 | 平台实机 | 平台实机 |
| 开机启动与全屏 | 部署轮验证 | 部署轮验证 |
| 断网、进程重启和恢复 | 部署轮验证 | 部署轮验证 |

在没有对应平台实机证据时，只能标为“代码完成，待平台验收”，不能写成已通过。

## 当前兼容边界

### macOS

- 第一数据源为 MediaRemote，读取 macOS 控制中心的系统级正在播放信息；
- QQ音乐 11.8.1 已实测可提供曲名、音乐人、专辑、时长、播放状态和 JPEG 封面；
- QQ音乐当前未发布可持续更新的 elapsedTime，因此进度会标记为 unavailable，不能假装精确；
- 网易云和其他播放器只要出现在控制中心即可走相同入口，但仍需逐一实测字段完整度；
- Apple Music、Spotify 保留 `osascript -l JavaScript` 的直接降级路径；
- MediaRemote 属于非公开系统接口，macOS 大版本升级后必须重新验收；
- 项目内工具通过 `scripts/setup-macos-mediaremote.sh` 固定版本安装，不修改系统 Homebrew。

### Windows

- 采集脚本随项目内置于 `app/sources/vendor/get_music_powershell.py`，无需外部依赖；
- `app/sources/windows.py` 默认调用该内置脚本，也可以用环境变量 `CORD_WINDOWS_SOURCE` 指定其他路径；
- 脚本通过 PowerShell 调用 Windows SMTC（`GlobalSystemMediaTransportControlsSessionManager`）读取全系统正在播放的媒体，支持曲名、音乐人、专辑、播放状态、进度、时长与专辑封面（Base64）；
- position/duration 依赖播放器是否发布时间线属性，部分播放器不发布时会安全降级为空；
- 兼容性取决于播放器是否向 Windows SMTC 发布媒体信息。

## 实机验收状态

- macOS：已完成 Apple Music 与 QQ音乐 11.8.1 真实字段验收（曲名、音乐人、专辑、状态、时长、JPEG 封面），并在 display/admin 联调通过；QQ音乐不发布精确 position 为已知限制；网易云待实机验证。
- Windows：SMTC 采集已实机跑通（曲名、音乐人、专辑、状态、封面正常显示，脚本本身提供 position/duration，随播放器而定）；三星门店屏实机全屏验收待部署轮完成。
