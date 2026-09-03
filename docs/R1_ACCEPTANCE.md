# R1 验收记录｜本机双页面骨架

日期：2026-09-01
状态：通过

## 本轮交付

- 本地 Python 服务；
- `/display` 独立显示 HTML；
- `/admin` 独立配置 HTML；
- `/health` 健康检查；
- `/api/state` 统一状态协议；
- `/api/events` SSE 实时推送；
- `/api/mock/track` mock 曲目控制；
- Windows `start.bat` 与跨平台 `python3 run.py` 启动方式；
- macOS `start-macos.command`、Windows `start.bat` 和平台数据源适配结构；
- 无第三方运行依赖。

## 自动测试

命令：

```bash
python3 -m unittest discover -s tests -v
```

结果：5 项通过。

| 测试 | 结果 |
|---|:---:|
| display/admin HTML 入口可访问 | 通过 |
| 健康检查与 schema version | 通过 |
| state 顶层数据协议 | 通过 |
| track 更新与 revision 增长 | 通过 |
| 非法时长输入返回 422 | 通过 |

## 浏览器验收

| 验收项 | 结果 | 证据 |
|---|:---:|---|
| 1920 × 1080 显示 | 通过 | viewport 与 scrollWidth/scrollHeight 均为 1920 × 1080 |
| display 实时连接 | 通过 | 页面显示 `LIVE` |
| admin 实时连接 | 通过 | 页面显示 `LIVE` |
| 配置端推送到显示端 | 通过 | admin 推送“R1 实时同步测试”，display 无刷新更新 |
| revision 同步 | 通过 | display 从 REV 1 更新为 REV 2 |
| 页面脚本错误 | 通过 | display/admin 均无 error 或 warning 日志 |

## 当前限制

- 当前数据源仍为 mock；
- macOS/Windows 真实适配器已建立，但尚未完成两端 R2 实机兼容验收；
- 服务重启后状态回到默认值，SQLite 在第 5 轮加入；
- 当前显示端只是 R1 架构占位，不是已确认的三张正式母版；
- 暂未实现曲目时间自动前进、真实封面抓取、播放事件分类和插播调度；
- Windows 真实电脑和三星屏幕尚未实机验收。

## 下一轮入口

R2 接入 `/Users/kaluozheng/Music-Player-Investigation/get_music_powershell.py` 的 Windows SMTC 数据，并补充 position/duration、事件分类和 mock/真实数据源切换。
