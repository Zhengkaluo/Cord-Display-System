# Changelog

本文件记录 Cord-Display-System 的开发变更。每次开发（含代码改动、文档定稿、排期调整）都应在此追加一条记录。

维护约定：
- 格式参考 [Keep a Changelog](https://keepachangelog.com/)，日期用 `YYYY-MM-DD`。
- 变更归类：`Added` 新增 / `Changed` 变更 / `Fixed` 修复 / `Removed` 删除 / `Docs` 文档 / `Plan` 排期。
- 新记录追加在最上方（倒序），最新的在最前。
- 每完成一个开发批次（R5–R9）验收后，必须在此记一条，并同步更新 DEVELOPMENT_PLAN 排期单的状态与日期。

---

## [Unreleased]

### Plan
- 确立 R5–R9 五批次串行排期，写入 DEVELOPMENT_PLAN.md 第 3A 节排期单（基准 2026-09-05 起）。

### Docs — 2026-09-04
- 新建 `docs/DISPLAY_REQUIREMENTS.md` v1.0：四场景模型（now_playing / promotion / store_event / ambient）、左侧比例白名单、中段插播（含跨曲延续）、全屏 cover/contain 缩放、背景取色双方案、左右分区双背景方案、专辑图四档尺寸、CORD 品牌色板（5A）、11 项新配置字段、界面文字示意。
- 新建 `docs/DEVELOPMENT_PLAN.md` v1.0：现状基线、与现状冲突点、目标架构变化、R5–R9 批次、风险、测试策略、运营/部署规则、文档同步清单。
- 新增示意图 `docs/assets/`：`bg-fill-comparison.png`（相近/对比色填充）、`brand-palette.png`（品牌色板）、`now-playing-bg-schemes.png`（四套分区背景方案）。
- 从 logo 定稿提取品牌色：brick `#B03D25`、khaki `#D9C486`、ink `#040000`、gold ≈`#E0A83A`，并确立底色/字色官方配对。
- 收敛文档：删除过时的 `docs/R1_ACCEPTANCE.md`、`docs/PLATFORM_ACCEPTANCE.md`（有效信息并入 PLATFORM_SUPPORT）、根目录旧版 `CORD_门店屏幕系统_开发与设计规划_v01.md`（未覆盖规则并入 DEVELOPMENT_PLAN 第 6–7 节）。
- 修正 `README.md`、`docs/PLATFORM_SUPPORT.md` 中与新需求冲突的过时表述，冲突处统一指向 DISPLAY_REQUIREMENTS。
