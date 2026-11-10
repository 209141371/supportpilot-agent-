# SupportPilot Portfolio Checklist

最终目标：让 SupportPilot 同时具备可运行、可解释、可评估、可展示和可公开发布的求职项目形态。

## 1. GitHub 发布

- [x] 本地 Git 仓库已初始化
- [x] `main` 分支存在
- [x] `.env` 未纳入 Git 跟踪
- [x] `supportpilot.db` 未纳入 Git 跟踪
- [x] `data/chroma/` 未纳入 Git 跟踪
- [x] `data/logs/` 未纳入 Git 跟踪
- [x] Git 历史和源码未发现真实 API key
- [x] GitHub 空仓库已创建
- [ ] 完成 GitHub 登录认证
- [ ] 推送 `main` 分支
- [ ] 在 GitHub 页面确认 README 正常渲染

## 2. 项目文档

- [x] README 包含项目背景和目标
- [x] README 包含架构图和核心流程
- [x] README 包含安装、配置和启动命令
- [x] README 包含完整 Eval 命令
- [x] README 标注 controlled smoke-test / regression dataset 限定
- [x] `.env.example` 与实际配置变量一致
- [x] `requirements.txt` 已提交

## 3. 产品能力展示

- [x] 订单查询
- [x] 工单查询
- [x] 工单创建
- [x] 工单状态修改
- [x] 企业政策 RAG
- [x] Shipping Workflow
- [x] HITL 审批
- [x] 工单幂等控制
- [x] Trace、Approval、Failure、Regression 日志

## 4. Eval 与质量口径

- [x] RAG Eval：Top1 Accuracy 100%
- [x] RAG Eval：Recall@3 100%
- [x] Workflow Eval：4/4 PASS
- [x] HITL Eval：5/5 PASS
- [x] Agent Tool Eval：4/4 PASS
- [x] Intent Route Eval：8/8 PASS
- [x] Unified Eval：5/5 Suites PASS
- [x] Release Gate：READY
- [x] 所有指标均注明为当前 controlled regression / smoke-test 结果
- [ ] 扩充真实用户问题、边界样本和对抗样本

## 5. Demo 展示顺序

建议使用以下顺序录制或现场演示：

1. 启动 Agent，展示普通政策问答。
2. 展示订单查询，说明业务数据来自 Tool 和 SQLite。
3. 展示物流异常 Workflow，说明确定性规则和幂等检查。
4. 展示 HITL：先 reject，证明数据库不发生写入。
5. 再 approve，证明写操作在人工批准后执行。
6. 运行统一 Eval，展示 `5/5 PASS` 和 `Release Gate = READY`。

## 6. 简历与面试统一表述

- [ ] 简历使用 AI 产品经理版或技术向 AI PM 版项目描述
- [ ] 统一使用：RAG Top1 `75% → 100%`
- [ ] 统一使用：`5` 类 Eval、`26` 个 controlled cases
- [ ] 统一使用：`5/5 Eval Suites PASS`
- [ ] 统一使用：`Release Gate = READY`
- [ ] 不声称生产准确率 100%
- [ ] 不声称用户解决率、效率提升或成本下降，除非后续有真实数据

## 7. 最终收官标准

SupportPilot 可视为完成收官，当以下条件全部满足：

- [ ] GitHub 登录并成功推送
- [ ] GitHub 仓库可正常打开和阅读
- [ ] README 启动说明可被新用户复现
- [ ] Demo 能完整展示 Agent、Workflow、HITL 和 Eval
- [ ] 简历、README、面试稿使用同一套指标
