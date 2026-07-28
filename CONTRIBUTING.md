# Contributing

感谢关注 TakeTime。当前项目保持单用户、个人自托管和低理解成本的范围。

## 开始之前

1. 阅读 [PRODUCT.md](PRODUCT.md) 的医疗安全与数据不变量。
2. 涉及界面时，先阅读 [DESIGN_REQUIREMENTS.md](DESIGN_REQUIREMENTS.md) 及其引用的两份设计资料。
3. 不要在代码、Issue、测试、截图或提交信息中加入真实药名、剂量、服药记录、口令、域名、IP 或数据库。
4. 安全问题按 [SECURITY.md](SECURITY.md) 私密报告。

## 本地验证

```bash
npm ci
npx playwright install chromium
npm test
```

浏览器测试必须使用临时数据库。不要修改或读取本机的 `data/medication.db` 来构造测试。

提交发布相关改动时还应验证导出的干净目录：

```bash
python3 scripts/verify_release_artifact.py /path/to/exported-release
```

## 变更要求

- 新行为需要覆盖正常路径、撤销/重试、边界值和历史不被改写的情况。
- 排程逻辑必须明确限定影响的药物、剂次和日期。
- 自动化不得替用户确认已服药，不得生成医学建议。
- UI 在 320、390 和 1280 像素宽度下不能丢失功能或横向溢出，触控目标至少 44px。
- 文案以事实为中心，明确区分“软件计算”和“医疗许可”。

## 授权

提交贡献前请注意：仓库目前没有开源许可证。提交 PR 并不自动改变项目的授权状态；贡献者应确认自己有权提交相关代码和资产。
