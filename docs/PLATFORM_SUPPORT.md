# macOS / Windows 双平台维护约定

## 原则

只维护一套产品核心：

- 同一套 `/display` 和 `/admin` HTML；
- 同一套 API、状态协议、调度规则、内容模型和 SQLite 数据；
- 同一套母版与动效逻辑；
- 平台相关代码只放在曲目数据源和部署启动层。

禁止复制出 `mac-version`、`windows-version` 两套长期分叉代码。

## 目录边界

| 目录/文件 | 是否共用 | 职责 |
|---|:---:|---|
| `frontend/` | 是 | display/admin HTML、CSS、JS |
| `app/server.py` | 是 | 本地服务和 API |
| `app/state_store.py` | 是 | 统一状态协议 |
| `app/sources/base.py` | 是 | TrackSource 接口 |
| `app/sources/macos.py` | 否 | MediaRemote 系统级读取＋Apple Music/Spotify 降级 |
| `app/sources/windows.py` | 否 | Windows SMTC 包装 |
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

- 使用 `/Users/kaluozheng/Music-Player-Investigation/get_music_powershell.py`；
- Windows 上默认从同级 `Music-Player-Investigation` 查找，也可以用环境变量 `CORD_WINDOWS_SOURCE` 指定；
- 当前旧脚本没有真实 position/duration，R2 需要补齐或加一层新的轻量时间线读取；
- 兼容性取决于播放器是否向 Windows SMTC 发布媒体信息。
