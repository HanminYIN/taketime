# 自托管部署指南

本文描述一个通用的 Linux + systemd + HTTPS 反向代理部署。示例域名、路径和口令都是占位符。

## 架构

```text
浏览器 → HTTPS 反向代理 :443 → 127.0.0.1:8000 → TakeTime → SQLite
```

不要直接向公网开放 8000。TakeTime 是单用户、单实例应用；同一数据库不要同时连接多个写入进程。

## 目录建议

```text
/opt/taketime/current -> /opt/taketime/releases/<release-id>
/opt/taketime/releases/<release-id>/
/var/lib/taketime/medication.db
/var/backups/taketime/
/etc/taketime/access.env
```

应用账号应是无登录 shell 的专用系统用户。数据库目录权限只授予该账号；环境文件只允许 root 读取。

## 生成干净 release

从已审核 tag 导出，不要复制工作树：

```bash
git archive --format=tar --output=taketime-v1.0.0.tar v1.0.0
sha256sum taketime-v1.0.0.tar > taketime-v1.0.0.tar.sha256
```

解压到全新目录后先执行：

```bash
python3 scripts/verify_release_artifact.py .
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

门禁失败时不要切换线上指针。

## 环境与服务

`/etc/taketime/access.env` 示例：

```ini
TAKETIME_ACCESS_PHRASE="请替换为高强度私人口令"
TAKETIME_DEMO_PHRASE="请替换为不同的演示口令"
```

不要把实际值写入仓库、shell 历史或 systemd unit。若不需要 VPS Demo，可省略 `TAKETIME_DEMO_PHRASE`，此时 `/demo` 返回 404。

systemd 的关键参数：

```ini
[Service]
User=taketime
Group=taketime
WorkingDirectory=/opt/taketime/current
EnvironmentFile=/etc/taketime/access.env
Environment=APP_TIMEZONE=Asia/Shanghai
Environment=TZ=Asia/Shanghai
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 -u /opt/taketime/current/server.py --host 127.0.0.1 --port 8000 --db /var/lib/taketime/medication.db --require-existing-db
Restart=on-failure
UMask=0077
```

生产环境使用 `--require-existing-db`，避免路径错误时悄悄创建空数据库。进一步建议启用 `NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome=true` 和仅允许数据库目录写入的 `ReadWritePaths`。

## 首次建库

确认目标数据库及所有 sidecar 都不存在，然后以应用账号排他创建：

```bash
sudo -u taketime env APP_TIMEZONE=Asia/Shanghai \
  python3 /opt/taketime/current/scripts/create_fresh_database.py \
  /var/lib/taketime/medication.db
```

创建器会拒绝既有文件、符号链接和 SQLite sidecar，并立即验证全新数据库不含历史记录。

## 反向代理

- 为公网域名启用有效 TLS 证书和 HTTP → HTTPS 跳转。
- 代理到 `http://127.0.0.1:8000`，传递 `Host`、客户端地址和 `X-Forwarded-Proto`。
- 私人入口建议再增加反向代理层强认证。
- `/demo` 只应开放 Demo 页面及必要静态资源，不能放开真实业务 API。
- 配置修改前运行代理自身的语法检查，不要覆盖同机其他站点。

## 在线备份

应用运行时使用 SQLite backup API，不要只复制主库：

```bash
sqlite3 /var/lib/taketime/medication.db \
  ".backup '/var/backups/taketime/medication-YYYYMMDD.db'"

sqlite3 /var/backups/taketime/medication-YYYYMMDD.db \
  'PRAGMA integrity_check; PRAGMA foreign_key_check;'
```

备份文件同样包含敏感医疗数据，应使用严格权限并纳入保留/删除策略。定期在隔离位置做恢复演练。

## 原子升级与回滚

1. 记录当前 `current` 指向。
2. 创建并验证数据库在线备份。
3. 把新代码解压到不可变的全新 release 目录。
4. 在新目录运行发布包门禁和测试。
5. 用临时符号链接 + 原子 `mv` 切换 `current`。
6. 重启服务，轮询 `/api/health`，再验证 schema、记录计数和公网 HTTPS。
7. 验证失败时把 `current` 指回旧 release 并重启；只有数据库迁移本身有问题时才使用数据库回滚点。

不要通过删除数据库、WAL/SHM 或历史记录来解决启动失败。
