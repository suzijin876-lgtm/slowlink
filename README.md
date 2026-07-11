# 慢链 SlowLink

SlowLink 是一个基于 Telethon、Flask 和 Redis 的 Telegram 消息监听与转发系统。它负责监听配置的群组或频道，按规则识别目标内容，执行防重复检查，并转发到指定 Telegram 会话。

## 环境要求

- Ubuntu 或 Debian
- root 或 sudo 权限
- 可访问 Docker 与 GitHub

一键脚本会自动安装 Docker Engine 和 Docker Compose 插件。

## 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/suzijin876-lgtm/slowlink/main/install.sh | sudo bash
```

脚本提供中文菜单：安装、更新到最新版本、卸载和退出。交互输入从 `/dev/tty` 读取，因此兼容管道执行。

安装目录为 `/opt/slowlink`。安装完成后访问 `http://服务器地址:8080`，在网页中完成 Telegram 和转发规则配置。

## 管理命令

```bash
sudo /opt/slowlink/manage.sh status
sudo /opt/slowlink/manage.sh logs
sudo /opt/slowlink/manage.sh restart
sudo /opt/slowlink/manage.sh update
sudo /opt/slowlink/manage.sh backup
sudo /opt/slowlink/manage.sh uninstall
sudo /opt/slowlink/manage.sh purge
```

更新只重建 `slowlink_app`，不会停止 `slowlink_redis` 或主机上的其他服务，并保留 `.env`、`data`、Telegram Session、Redis 数据和用户配置。

`uninstall` 保留配置与数据；`purge` 会要求输入 `PURGE` 后彻底删除 SlowLink 自有资源。

## 稳定性保护

- Docker 健康检查监控 Web 服务。
- CPU watchdog 仅在应用容器持续高 CPU 时重启 `slowlink_app`。
- 监听期望状态保存在 Redis，应用容器重启后可自动恢复监听。
- Docker 日志启用大小和文件数量限制。

## 发布资产

每个 GitHub Release 提供 app 包、full 包、更新日志和 `SHA256SUMS.txt`。安装和更新必须通过 SHA-256 校验后才会部署。

## 安全说明

公开仓库不包含 `.env`、密码、Token、Telegram Session、Redis 数据、数据库、日志或备份。不要手动将这些运行时文件加入 Git。

