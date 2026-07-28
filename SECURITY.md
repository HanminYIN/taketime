# Security Policy

## Supported version

安全修复只面向 `main` 上的最新版本。此个人项目不承诺长期支持旧 release。

## Reporting a vulnerability

请不要在公开 Issue 中披露可利用细节、真实用药数据、访问口令或服务器信息。优先使用 GitHub 仓库 **Security → Report a vulnerability** 提交私密安全报告，并包含：

- 受影响版本或 commit
- 最小复现步骤
- 预期影响与已验证的边界
- 已采取的临时缓解措施（如有）

在修复发布前，请避免公开利用代码。

## Security model

- 应用设计为单用户、单实例、自托管，不提供多用户权限隔离。
- Python 服务默认只监听 `127.0.0.1`；公网部署必须通过 HTTPS 反向代理。
- 私人应用与 Demo 使用不同口令和不同 `HttpOnly` 会话 Cookie。
- Demo 会话不能访问真实业务 API，Demo 页面不读写 SQLite。
- 口令只能通过运行环境或 root-only 环境文件提供，不能提交到 Git。
- 数据库、WAL/SHM、备份、日志和发布服务器信息都不属于发布源码。
- 发布包应运行 `scripts/verify_release_artifact.py`，拒绝常见运行数据和敏感产物。

应用口令不替代防火墙、TLS、强边界认证、系统补丁或备份。直接把 8000 端口暴露到公网不在支持范围内。

## Dependency and deployment hygiene

- 使用受支持的 Python 与 Node.js 版本，定期安装安全更新。
- GitHub Actions 固定使用官方 action 的主版本，并保持最小权限。
- 上线前运行完整测试、发布包门禁和 SQLite 在线备份。
- 升级使用不可变 release 目录与原子指针；保留经过验证的旧 release 和数据库回滚点。
- 不要把生产数据库复制到 Issue、PR、CI artifact 或公开 Demo。
