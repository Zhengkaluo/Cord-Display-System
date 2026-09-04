# CORD Display System 开发与设计规划（DEVELOPMENT_PLAN）

版本：v1.0
更新日期：2026-09-04
关联文档：[DISPLAY_REQUIREMENTS.md](./DISPLAY_REQUIREMENTS.md)（显示与配置需求，**权威规格来源**）
状态：规划，待开工。

> 冲突裁决原则：本规划与 README 或既有验收文档如有出入，**一律以 `DISPLAY_REQUIREMENTS.md` v1.0 为准**。下方第 1 节列出已知冲突点。

---

## 0. 现状基线

- 架构：本地播放器 → 数据源采集（windows.py / macos.py）→ SourceRunner 每 2 秒轮询 → StateStore 统一状态与调度 → server.py HTTP + SSE → /display + /admin。纯 Python 标准库 + 原生 HTML/JS，零第三方运行依赖。
- 平台：macOS 与 Windows 数据源均已实机跑通（Windows 采集脚本已内置到 `app/sources/vendor/`，编码 bug 已修）。
- 已有能力：mock/真实数据源切换、三场景显示骨架、SSE 实时推送、SQLite 演出表与物料库、曲末自然结束场景插播、左侧视觉全局三选一（album_cover/image/video）。

---

## 1. 与现状的冲突点（以新需求为准）

| 主题 | 现状（README / 现有代码） | 新需求（DISPLAY_REQUIREMENTS v1.0，为准） |
|---|---|---|
| 场景数量 | 三张母版：now_playing / artist_notice / promotion | 四场景：now_playing / promotion / store_event / ambient |
| 演出提示 | 独立整屏场景 artist_notice，切走画面 | 取消独立场景，**并入 now_playing 右侧**作增量信息块，命中即常挂 |
| 门店内容 | 单一「豆子/活动」内容库，顺序轮换 | **promotion 门店推荐 + store_event 门店活动并行两类**，插播时随机混播 |
| 左侧视觉素材 | 只放 1:1 方形，按方形区域裁切 | **比例白名单**（1:1/3:4/4:3/2:3/9:16/9:19.5），等比缩放贴合，左右拼满整屏 |
| 左侧轮播 | 无（全局静态三选一） | 新增**中段插播**：够长的曲子在 insert_at_percent 处临时换素材、含跨曲延续 |
| 全屏缩放 | 无策略（图片一律方区裁切） | **cover/contain 智能切换**（fullscreen_fit_threshold），contain 时取色补边 |
| 背景填充 | 固定死色（ink/paper/khaki） | **前端 Canvas 取色**，analogous/contrast 双方案 + 安全底色回退 |
| 常驻全屏 | 无 | 新增 **ambient** 场景，contain 居中常驻图/视频 |
| 屏幕方向 | 1920×1080（隐含横屏） | 明确**横屏**，全屏白名单 16:9 主推 |

README 需在开发完成后同步重写这些描述，避免与实现脱节。

---

## 2. 目标架构变化（新增/改动的数据与模块）

### 2.1 StateStore 状态模型变化

- `config` 新增字段：`visual_aspect`、`visual_size`、`visual_bg_conflict_threshold`、`right_bg_variant`、`bg_fill_mode`、`fullscreen_fit_threshold`、`insert_min_song_seconds`、`insert_at_percent`、`insert_hold_seconds`、`ambient_media_url`、`ambient_media_type`。
- `DISPLAY_MODES` 由 `{now_playing, artist_notice, promotion}` 改为 `{now_playing, promotion, store_event, ambient}`。
- `display` 结构新增左侧中段插播的独立状态：如 `visual_insert`（素材 URL/type、结束时刻、是否延续中），与场景级插播 `active_insert` 解耦，二者互不干扰。
- 演出提示不再是 display.mode，而是 now_playing 内的右侧增量块，由 artist 命中结果驱动一个 `artist_notice` 内容块的显隐。

### 2.2 内容库拆分

- 现 `display_items` 增加 `category` 字段区分 `promotion` / `store_event`（或复用现有 content_type 语义并明确两类），插播取素材时从两类有效物料随机混选。
- 保留每条物料的 `display_seconds`、生效区间、优先级、启用状态。

### 2.3 前端模块

- 新增独立取色模块（见 DISPLAY_REQUIREMENTS 5.5）：`resolveFillColor(sample,{mode})` 纯函数内核 + `getFillMode(scene)` 作用域解析层 + 素材主色缓存。
- display.js 的 `renderVisual` 扩展为支持比例白名单缩放、中段插播素材切换、取色补边。
- 新增 `renderScene` 对 store_event / ambient 的支持，全屏场景统一走 cover/contain 决策函数。

---

## 3. 里程碑与批次

按"地基→能力→打磨"分五批，每批可独立验收、独立提交。

### R5 · 数据与配置地基（最先做）
- StateStore 加全部新配置字段 + 校验 + 持久化；DISPLAY_MODES 扩为四场景。
- /admin 加对应表单控件（比例、取色方案、阈值、中段插播三参数、ambient 素材）。
- 内容库拆分 promotion / store_event 两类。
- 验收：配置可存取、重启保留、非法值返回 422；四场景可手动切换。

### R6 · now_playing 布局重构
- 左侧视觉比例白名单 + 等比缩放，左右拼满无空隙。
- 专辑图尺寸四档 `visual_size`（small/medium/large/fill）。
- 左右分区双背景方案：左侧默认暖米卡其、与封面主色明度冲突时自动切备选底；右侧默认 ink 近黑、admin 可手动切亮底并联动字色（按 DISPLAY_REQUIREMENTS 5A 品牌配对）。
- CSS 品牌色校准到色板（ink `#040000`、khaki `#D9C486`、brick `#B03D25`、gold `#E0A83A`）。
- 演出提示并入右侧增量块（命中常挂，换到不命中才移除），删除独立 artist_notice 场景。
- 验收：三种典型比例素材（1:1 / 4:3 / 9:16）左右均无空隙；四档尺寸生效；暗色封面下左侧底自动切换、封面轮廓清晰；右侧亮底/暗底字色可读；命中/不命中歌手右侧正确增减信息块。

### R7 · 背景取色模块
- 前端 Canvas 取色内核 + analogous/contrast 双方案 + 安全底色回退 + 主色缓存。
- 应用到左侧补边与全屏 contain 留白。
- 验收：暖/冷/花色三类素材下两种方案观感符合示例图预期；取色失败回退底色、无纯黑边。

### R8 · 全屏场景与 ambient
- store_event 场景（设计同 promotion）落地；promotion/store_event 曲末随机混播。
- 全屏 cover/contain 智能缩放；新增 ambient 常驻全屏（后台手动切入切出、contain 居中、视频 muted loop）。
- 验收：随机混播比例合理；ambient 切入切出正常、整图完整可见。

### R9 · 左侧中段插播（工作量最大，压轴）
- 中段插播独立计时状态：够长曲子在 insert_at_percent 触发、停留 insert_hold_seconds。
- 跨曲延续：按绝对停留时长计时、不因换曲重置；超出当前曲则延续到下一首、结束回落到下一首封面；插播进行中忽略新触发。
- 验收：构造"够长曲 + 触发点靠后"用例验证跨曲延续；验证延续期间新触发被忽略；右侧全程正常更新。

---

## 3A. 排期单

工时为单人开发 + 设计的粗估，不含等待真实门店运行观察的时间。批次严格串行，每批过关后再进下一批；实际起止日随开工日滚动更新，下表以 2026-09-05 起排作为基准示意。

| 批次 | 内容摘要 | 预计工时 | 基准起止（示意） | 依赖 | 状态 |
|---|---|---:|---|---|:---:|
| R5 | 数据/配置地基：11 字段 + 四场景枚举 + 内容库拆两类 + admin 表单 | 1–2 天 | 09-05 → 09-06 | 无 | 待开工 |
| R6 | now_playing 重构：比例白名单 + 四档尺寸 + 左右双背景 + 演出并入 + 品牌色校准 | 3–4 天 | 09-08 → 09-11 | R5 | 待开工 |
| R7 | 背景取色模块：Canvas 取色内核 + 双方案 + 回退 + 缓存 | 2–3 天 | 09-12 → 09-16 | R6 | 待开工 |
| R8 | 全屏场景 + ambient：store_event 落地 + 随机混播 + cover/contain + 常驻宣传 | 3–4 天 | 09-17 → 09-22 | R7 | 待开工 |
| R9 | 左侧中段插播：独立状态机 + 跨曲延续 + 忽略新触发 | 3–5 天 | 09-23 → 09-29 | R6/R7 | 待开工 |

排期维护约定：每批实际开工时把"状态"改为进行中并填真实起始日；完工验收通过后改为已完成并填结束日，同时在 CHANGELOG.md 追加一条记录。若某批工期或范围调整，直接改本表并在 CHANGELOG 说明原因。

---

## 4. 风险与依赖

- **中段插播（R9）是全新逻辑**，当前代码完全没有，需在 StateStore 引入独立计时器与状态机，注意与曲末场景插播的定时器互不打架、以及服务关闭时清理定时器。
- **取色性能**：门店屏常驻停留久，Canvas 取色开销小；但需处理跨域素材（本地 /media 无虞，外链需 CORS）、SVG/视频取色受限时回退。
- **QQ音乐无精确 position**：中段插播依赖播放进度百分比，QQ音乐 position 常为 unavailable，需用"已观察播放时长"估算或对无 position 的曲目降级（不触发中段插播），此边界要在 R9 明确。
- **测试兼容性**：现有测试在 Windows 下清理临时 SQLite 有 WinError 32（tearDown 未 close 连接），新增测试前建议先修，避免误判失败。

---

## 5. 测试策略

- 单元测试：新配置字段校验、四场景切换、内容库两类拆分、中段插播计时状态机（含跨曲延续、忽略新触发）、cover/contain 决策函数。
- 前端可视验收：三种左侧比例无空隙、命中歌手增量块、两种取色方案观感、全屏缩放、ambient 切入切出。
- 回归：保留 R1–R4 已验收能力（SSE 推送、演出匹配、曲末插播限流）不被破坏。
- 命令：`python -m unittest discover -s tests -v`（当前环境无 pytest）。

---

## 6. 运营与内容规则（从 v0.1 收纳，三份文档原未系统覆盖）

### 6.1 插播频控硬约束
- 非音乐内容每小时占比不超过设定上限（默认 10%），属硬限制，避免屏幕变广告牌。
- 同类内容分别计时的最小间隔（默认 20–30 分钟）；品牌、门店推荐、门店活动各自独立计。
- **禁止连续插播**：一次插播后至少完整显示一首曲目或达到规定播放时长，才允许下一次。
- 无可播插播内容时继续显示当前播放，**不为凑频率强行插播**。
- 触发点仅限曲目自然结束后；暂停、拖动、手动切歌默认不触发。

### 6.2 内容库运营字段（在 category 之外补充）
- 发布状态：草稿 / 已发布 / 已停用，人工审核后上线，一键停用。
- 生效与失效时间、每日时段（如 10:00–18:00 按营业时段投放）。
- 每日上限（单条内容每日曝光次数）、优先级、单次展示时长。
- 旧 runtime-config.json 单条内容首次启动迁移为内容库首条，仅迁移一次。

### 6.3 异常与降级显示
- 抓取暂时失败：保留上一条可信状态并显示内部离线标记，**不清空屏幕、不黑屏**。
- 无音乐 / 开店前：显示品牌待机画面。
- 网络/服务异常：前台保持可观看画面，错误只在 admin 显示（含最后更新时间），不向顾客报错。

## 7. 部署与验收边界（从 v0.1 收纳）

### 7.1 门店设备部署（新文档原缺）
- macOS/Windows 开机自启动本地服务与全屏显示；指定显示器、全屏 / Kiosk、不露出桌面。
- 崩溃重启、断网自动重连与进程守护；本地缓存最后状态；日志导出、备份恢复。
- 两平台各自完成部署验收：重启与断网后能自行恢复到营业状态，admin 仍可单独打开。

### 7.2 实机视觉验收
- 目标屏：Samsung The Frame 32LS03C，1920×1080，横屏。
- 用真实电视做远距离字号、色彩、16:9 安全区与裁切检查；长标题/长音乐人名/无封面/明暗封面差异适配。
- 连续 5–7 个营业日试运行无阻断问题方可定 v1.0。

### 7.3 MVP 明确不做
- 不做多门店/多设备分组管理；不自动抓取演出信息（后台人工录入 + 有效期）。
- 不做复杂账号权限，只保留本机管理员入口；不把旧 WebUI 自由网格编辑器作为最终后台。
- 不承诺所有播放器都提供精确时长（缺失时安全降级）；生成式内容不自动发布，对外信息保留人工确认。

## 8. 文档同步清单（开发完成后）

- README.md：重写「三张显示母版」「左侧视觉配置」「豆子/活动内容库」等章节，改为四场景 + 比例白名单 + 两类物料 + 取色。
- PLATFORM_SUPPORT.md：Windows 已实机跑通，保持「实机验收状态」段与实际一致（原 PLATFORM_ACCEPTANCE.md 已并入此文件）。
- DISPLAY_REQUIREMENTS.md：如开发中出现规格调整，回写并升版本号。
- CHANGELOG.md：每次开发（代码改动、文档定稿、排期调整）都追加一条；每批 R5–R9 验收后必记，并同步更新第 3A 节排期单的状态与日期。
