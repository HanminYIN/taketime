# 药时 TakeTime

> 服药有时，养正无恙

[在线互动演示](https://hanminyin.github.io/taketime/) · [产品边界](PRODUCT.md) · [部署指南](DEPLOYMENT.md) · [更新记录](CHANGELOG.md)

TakeTime 是一个单用户、自托管的每日用药记录工具。它把当天的真实作息、用餐时间和实际服药签到结合起来，持续给出下一项待办，而不是只展示一张固定钟点表。

公开 Demo 使用完全虚构的药名、剂量和时间，所有操作只保存在浏览器内存中，刷新即重置，不连接数据库。

> [!IMPORTANT]
> TakeTime 是个人记录与排程软件，不提供诊断、处方、剂量建议或药物相互作用判断。任何计划都应来自医生、药师或药品说明书；自动调整时间不代表医学上允许提前或延后服药。

## 排程方式

每种药只需要选择一种容易理解的时间依据：

| 模式 | 适用关系 | 签到后的行为 |
| --- | --- | --- |
| 跟随作息 | 与起床、睡前等生活节奏相关 | 实际签到只记录，不推动后续剂次 |
| 跟随用餐 | 与早餐、午餐或晚餐相关 | 时间由餐次决定，签到不推动后续剂次 |
| 跟随上次服用 | 重点保持同一种药相邻剂次的原定间隔 | 根据前一次实际签到滚动调整当天同药尚未完成的剂次 |

“跟随上次服用”默认带有单次自动调整上限。偏移超出上限时，系统只记录本次签到，不自动移动后续计划；撤销签到或修改当天作息后，会按现有事实重新计算。

## 主要能力

- 起床打卡后按当天真实作息推算早餐、午餐、晚餐和睡前时间
- 首页优先展示当前最相关的下一项用药，完整计划保留在时间线中
- 三种时间模式、同药限定、偏移上限、撤销重放和跨午夜安排
- 逐项确认或撤销，只有用户明确操作才会写入“已服用”
- 新增、编辑、停用一到多次/日的用药计划
- 每日计划快照，之后修改药单不会悄悄改写既往记录
- 最近 7 天记录与 SQLite 本地持久化
- 私人入口与独立 Demo 使用不同口令、Cookie 和权限边界

当前范围是个人单用户版本，不包含账号注册、多人共享、收费功能或 AI 医疗建议。后续方向见 [ROADMAP.md](ROADMAP.md)。

## 本地启动

需要 Python 3.11 或更高版本。应用默认监听 `127.0.0.1:8000`：

```bash
TAKETIME_ACCESS_PHRASE='请替换为高强度私人口令' \
APP_TIMEZONE=Asia/Shanghai \
python3 server.py
```

然后访问 <http://127.0.0.1:8000>。首次本地启动会在 `data/medication.db` 创建 SQLite 数据库；`data/` 已被 Git 忽略。

如需启用与真实数据隔离的本地 Demo，可额外设置独立口令：

```bash
TAKETIME_ACCESS_PHRASE='请替换为高强度私人口令' \
TAKETIME_DEMO_PHRASE='请替换为不同的演示口令' \
APP_TIMEZONE=Asia/Shanghai \
python3 server.py
```

互动演示位于 <http://127.0.0.1:8000/demo>。不要复用私人口令和 Demo 口令，也不要把口令写入仓库、systemd unit 或命令示例的实际值中。

生产环境应使用反向代理提供 HTTPS，只让 Python 服务监听回环地址，并在升级前使用 SQLite 在线备份。完整步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 测试

安装浏览器测试依赖：

```bash
npm ci
npx playwright install chromium
```

运行完整测试：

```bash
npm test
```

测试包含 Python 单元/集成测试，以及 Chromium 端到端和 320、390、1280 像素响应式回归。浏览器测试使用临时数据库，不读取或修改 `data/medication.db`。

发布目录还可单独执行数据泄露门禁：

```bash
python3 scripts/verify_release_artifact.py /path/to/release
```

门禁会拒绝 `.git`、`data/`、SQLite/WAL/SHM、备份、归档容器、符号链接和缺失的运行文件。

## 数据与安全

TakeTime 没有账号体系、MFA 或多人权限隔离。若部署到公网，应用口令不能替代 HTTPS、防火墙和反向代理层的访问控制。详细威胁边界与漏洞报告方式见 [SECURITY.md](SECURITY.md)，本地数据范围见 [PRIVACY.md](PRIVACY.md)。

## 授权状态

本仓库目前公开源码用于审阅、学习和个人项目协作，但**尚未授予开源许可证**。除法律明确允许的情形外，复制、修改、再分发或商业使用前请先取得版权所有者许可。未来如决定采用正式开源许可证，会通过独立版本更新明确说明。

## 文档

- [PRODUCT.md](PRODUCT.md)：产品范围、排程语义与医疗安全边界
- [ROADMAP.md](ROADMAP.md)：个人版后续路线
- [DEPLOYMENT.md](DEPLOYMENT.md)：自托管、备份、升级与回滚
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献约定
- [DESIGN_REQUIREMENTS.md](DESIGN_REQUIREMENTS.md)：持久视觉与可访问性基线
- [public/assets/README.md](public/assets/README.md)：图片与字体来源
