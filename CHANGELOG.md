# 更新日志

本项目遵循语义化版本号。发布更新日志由本文件对应版本章节自动生成。

## [1.38.73] - 2026-07-11

- 初始化公开 Git 仓库和 `main` 分支，清理仓库根目录历史版本包与运行时文件。
- 增加 GitHub Actions 标签发布流程，自动测试并生成 app 包、full 包、更新日志和 `SHA256SUMS.txt`。
- 增加中文一键安装、更新、卸载和管理脚本，支持 Ubuntu、Debian 与 `curl | sudo bash`。
- 更新时保留 `.env`、`data`、Telegram Session、Redis 数据和用户配置，只重建 `slowlink_app`。
- 保留现有 CPU watchdog 和 Redis 监听状态自动恢复逻辑。
- 本版本不修改消息监听、识别、去重或转发业务逻辑。

