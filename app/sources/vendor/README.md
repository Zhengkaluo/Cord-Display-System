# app/sources/vendor

本目录存放随项目内置的、平台相关的第三方/外部采集脚本。

## get_music_powershell.py 【Windows 专用】

- 用途：通过 PowerShell 调用 Windows SMTC（`GlobalSystemMediaTransportControlsSessionManager`）读取全系统正在播放的媒体信息。
- 调用方：`app/sources/windows.py` 的 `WindowsSMTCSource`，命令为 `python get_music_powershell.py --json --thumbnail`。
- 依赖：仅 Python 标准库 + 系统 PowerShell，自包含、无额外依赖。
- 来源：从调研项目 `SystemPlayerInvestigation` 中抽取，仅保留数据源采集所需的这一个脚本。
- 覆盖路径：可用环境变量 `CORD_WINDOWS_SOURCE` 指向其他脚本位置。

> macOS 侧的对应采集工具是 `.tools/nowplaying-cli/`（MediaRemote 命令行），由 `app/sources/macos.py` 调用，与本目录无关。
