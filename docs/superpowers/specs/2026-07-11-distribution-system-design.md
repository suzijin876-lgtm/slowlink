# SlowLink 完整分发体系设计

## 目标

为主 SlowLink 增加公开 GitHub 分发、自动 Release、一键安装更新卸载和服务器安全部署能力。版本从 `1.38.72` 递增到 `1.38.73`。本次只增加分发基础设施，不修改消息监听、识别、去重、转发、Redis 状态或监听自动恢复等主业务逻辑。

## 仓库与历史归档

- 本地仓库：`D:\Users\szjhs\Documents\tg\slowlink`
- GitHub：`https://github.com/suzijin876-lgtm/slowlink.git`
- 默认分支：`main`
- 首个发布标签：`v1.38.73`
- 根目录现有 `V1.*` 目录和 `_v153_*` 历史文件移到仓库外的 `D:\Users\szjhs\Documents\tg\slowlink_releases_archive`，本地保留但不进入 Git 历史。
- Git 只提交当前源码、测试、运维脚本、分发脚本、文档和工作流。
- `.gitignore` 必须排除 `.env`、密码和 Token 文件、Telegram Session、Redis 数据、数据库、日志、备份、缓存、构建产物和本地版本归档。

## Release 架构

GitHub Actions 监听 `v*` 标签并使用 `permissions: contents: write`。工作流先校验标签版本与 `VERSION` 一致，再执行 Python 编译、单元测试、Shell 语法检查和分发安全测试。全部通过后生成并发布四个资产：

1. `slowlink_app_v1_38_73.zip`
2. `slowlink_v1_38_73_full.zip`
3. `slowlink_v1_38_73_update_log.txt`
4. `SHA256SUMS.txt`

app 包用于只替换应用源码；full 包包含首次安装需要的 Docker、Compose、运维脚本、模板和示例配置。两个 ZIP 都不得包含运行时数据或秘密。`SHA256SUMS.txt` 覆盖前三个资产。仓库中不保存 Release ZIP，只在 GitHub Actions 和仓库外本地版本目录中生成。

## 一键安装脚本

根目录 `install.sh` 提供中文菜单，并通过 `/dev/tty` 读取交互输入，兼容 `curl -fsSL <raw-url> | sudo bash`：

```text
1. 安装
2. 更新到最新版本
3. 卸载
0. 退出
```

卸载二级菜单：

```text
1. 卸载程序但保留配置、Telegram Session、Redis 数据和数据库
2. 彻底删除
0. 返回
```

彻底删除必须先输入完全一致的 `PURGE`，未确认时不得停止或删除任何服务。

脚本支持 Ubuntu 和 Debian，自动安装 Docker Engine 和 Docker Compose 插件。Release 下载通过 GitHub API 获取最新正式版本，下载后必须先验证 SHA-256，再解压到临时目录并检查归档中不存在 `.env`、Session、数据库、日志、备份、Redis 数据或 `.git`。

首次安装创建 `/opt/slowlink` 和 `data/sessions`，保留或引导创建 `.env`，启动 Redis 与应用，并安装现有 CPU watchdog。更新时保留 `.env`、`data`、Telegram Session、Redis 命名卷和用户配置，只执行等价于 `docker compose up -d --no-deps --build app` 的应用重建；不得执行 `docker compose down`，不得停止 `slowlink_redis` 或其他容器和服务。

## 管理脚本

`manage.sh` 提供以下命令：

- `status`：显示应用、Redis、健康检查、监听状态和 watchdog 状态。
- `logs`：查看 `slowlink_app` 日志。
- `restart`：只重启 `slowlink_app`，等待健康恢复。
- `update`：调用与 `install.sh` 相同的最新 Release 下载、校验和安全更新流程。
- `backup`：备份 `.env`、`data/sessions`、用户配置和 Redis 数据快照到仓库外的本地备份目录。
- `uninstall`：卸载应用和 watchdog，保留配置、Session、Redis 数据和数据库。
- `purge`：要求输入 `PURGE` 后彻底删除 SlowLink 自有容器、卷、配置和安装目录。

安装脚本和管理脚本共用一个分发辅助脚本，避免下载、校验、健康等待和诊断逻辑重复。

## 状态保护与失败处理

- 更新前记录 `slowlink_app`、`slowlink_redis` 和主机其他容器的启动时间与状态。
- 应用更新失败时保留下载临时目录并输出中文诊断，包括 Docker 状态、Compose 配置检查、应用日志和健康接口结果。
- 更新不能清空 Redis，也不能覆盖 Session 或 `.env`。
- 监听是否自动恢复继续由现有 Redis `listener_desired_state` 和应用启动逻辑负责，分发脚本不修改该状态。
- CPU watchdog 脚本和 systemd 单元保持现有行为，只负责安装、启用和状态检查。
- 卸载保留模式不得删除 Redis 容器、Redis 卷、Session、`.env` 或数据库；彻底删除只处理 SlowLink 自有资源。

## 测试与验收

本地和 GitHub Actions 都执行：

- `python -m compileall -q app tests`
- `python -m unittest discover -s tests`
- `bash -n` 和 `dash -n` 检查 Shell 脚本
- 分发脚本回归测试：菜单、`/dev/tty`、PURGE 前置确认、敏感文件排除、只重建 app、Release 资产命名、校验和、版本一致性
- 本地打包检查：ZIP 内容白名单和四个资产 SHA-256

发布后验证 GitHub Release 含四个资产。服务器部署使用新更新流程，随后确认：

- `/health` 返回 `1.38.73`
- `slowlink_app` 为 healthy
- `slowlink_redis` 未重启且数据正常
- `.env`、Telegram Session 和用户配置仍存在
- `listener_desired_state`、`bot_status`、`tg_logged_in`、`target_chat` 状态合理
- CPU watchdog 为 active，监听自动恢复正常
- 网页可访问且近期无新 traceback
- 主机其他容器和服务的启动时间未变化

## 本地版本归档

在仓库外生成 `D:\Users\szjhs\Documents\tg\slowlink_releases\V1.38.73`，保存与 GitHub Release 一致的四个资产。历史 `V1.*` 目录单独保存在 `slowlink_releases_archive`，不与新发布目录混放。
