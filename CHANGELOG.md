# Changelog

Tadado 版本更新日志。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.1.2] — 2026-06-09

### Added
- **版本与更新**：关于对话框新增检查更新功能（GitHub Release API + 阿里云盘自动回退），20 秒超时，检测到新版本时下载渠道标注 ⭐ 推荐
- **阿里云盘下载渠道**：关于对话框 + README 增加阿里云盘分享链接（国内用户推荐，仅提供安装版）
- **交流方式**：关于对话框新增邮箱 `hanxy8413@gmail.com`、微信公众号 `Pyvan`、GitHub 项目地址
- **`src/version.py`**：统一版本号来源，消除与 `pyproject.toml` 的不一致
- **`src/services/update_checker.py`**：异步更新检测服务，QNetworkAccessManager + QProcess 双通道
- **发布脚本增强**：`release.ps1` 新增源码包生成（`git archive`）和阿里云盘上传步骤

### Changed
- 关于对话框重新布局：版本状态 + 检查更新 + 下载渠道 + 交流方式集中在同一区域

---

## [0.1.2-pre] — 2026-06-09

### Fixed
- 进度栏按钮筛选结果错误：原按 `deadline_date`/`scheduled_date` 范围过滤，改为按 `activity_log` 活动时间戳精准过滤，与活动报告（TaskTreePanel）结果一致
- 进度栏与活动报告活动计数不一致：统一 `_ts_in_range` 与 `_entry_date` 时间戳解析逻辑（双格式支持、key 名兼容）

### Changed
- 取消进度栏与速览栏的按钮联动锁定：6 个周期按钮始终可点击，`set_synced_period()` 替换为 `reset_to_unclicked()`
- 进度栏活动过滤从 SQL 层 `activity_*` 预计算列改为 Python 层 `filter_tasks_by_activity()` 精准扫描，避免跨天列值过时

---

## [1.0.0] — 2026-06

### 核心功能
- Markdown 语法创建和管理任务，支持优先级、截止时间、标签
- 9 列表格视图：复选框、序号、创建时间、任务内容、截止时间、进度、状态、标签、归档
- 全文搜索（SQLite FTS5）+ 状态/优先级/排序筛选
- 日历热力图（12 月 × 7 行 × 5 列矩阵）+ 活动报告导出（Markdown/Excel）
- 分区管理：多分区隔离、密码保护、自动锁定
- 批量操作：全选、右键批量变更状态/延后/中止/删除、导出
- 标签管理：重命名、合并，全局自动同步

### 提醒 & 后台
- 到期任务提醒（可配置间隔），安静时段免打扰
- 每日自动归档已完成任务
- 循环任务自动创建下一实例

### 窗口 & UI
- 无边框自定义标题栏 + Win32 原生拖拽/停靠（Aero Snap）
- 浅色/深色双主题，Design Tokens 语义化配色
- 系统托盘：最小化到托盘、双击恢复、快捷新建
- 开机自动启动（可选）

### 数据
- 导入 Markdown 文件
- 导出 Markdown / Excel 活动报告
- 生产/开发环境数据隔离

---

格式说明：
- `Added` — 新增功能
- `Changed` — 功能变更
- `Fixed` — Bug 修复
- `Removed` — 移除功能
