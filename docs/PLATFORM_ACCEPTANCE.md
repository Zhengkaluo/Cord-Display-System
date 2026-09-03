# 双平台验收状态

更新日期：2026-09-02

| 能力 | macOS | Windows |
|---|---|---|
| 共用本地服务 | 自动测试通过 | 代码共用，待 Windows 实机 |
| display/admin HTML | macOS 浏览器通过 | 同一前端，待 Windows 浏览器实机 |
| mock 实时同步 | 通过 | 同一协议，待 Windows 实机 |
| 自动平台识别 | 通过：识别为 `darwin` / `macos-system` | 选择逻辑测试通过，待 Windows 实机 |
| 真实播放器适配器启动 | 通过：MediaRemote 优先，AppleScript 降级 | 代码完成，待 Windows 实机 |
| Apple Music 真实歌曲信息 | 通过：标题、音乐人、专辑、状态、位置、时长 | 待 Windows 实机 |
| QQ音乐真实歌曲信息 | 通过：QQ音乐 11.8.1；标题、音乐人、专辑、状态、时长、JPEG 封面，并完成 API → display/admin HTML 联调 | 不适用 |
| position/duration | Apple Music position/duration 通过；QQ音乐 duration 通过、position unavailable | 旧 SMTC 脚本尚未提供，R2 待补 |
| 平台启动入口 | `start-macos.command` 已建立 | `start.bat` 已建立，待 Windows 实机 |

当前结论：macOS 已完成 Apple Music 和 QQ音乐的真实歌曲字段验证；QQ音乐真实封面与曲目信息已在 display/admin HTML 中验收。QQ音乐不发布精确 position 是已知限制，后续自然结束判断需要换曲事件与本地计时降级。网易云待实机播放验证。Windows 目前只有代码、数据归一化测试和启动入口，不能替代 Windows 电脑上的 SMTC 实测。
