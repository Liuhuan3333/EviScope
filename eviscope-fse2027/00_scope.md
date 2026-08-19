# EviScope FSE 2027：研究范围（冲刺修订版）

- 项目代号：`eviscope-fse2027`
- 工作标题：*Unknown Is Not Hallucinated: Evidence Escalation for Reliable Code Review Verification*
- 模式：compose
- **投稿目标（已恢复锁定）：FSE 2027 Research Papers**
- 截止时间：2026-10-02 AoE
- 会议时间与地点：2027-07-12 至 2027-07-16，中国深圳
- 文稿要求：18 页正文和图表，另加 4 页参考文献；双盲；必须包含 Data Availability
- 官方 CFP：https://conf.researchr.org/track/fse-2027/fse-2027-papers
- 冲刺修订说明：`governance/fse_2027_sprint_revision_2026-08-19.md`
- 会场锁定：`governance/venue_lock_fse_2027_2026-08-19.md`

## 核心对象与任务

- 核心对象：LLM 生成或人类撰写的代码审查评论中的**原子事实主张**
- 核心任务：在冻结的 review-time 证据上，对每个 claim 作 `SUPPORTED / CONTRADICTED / INSUFFICIENT` 判断；对 `INSUFFICIENT` 执行**预算受限的定向证据升级**
- 正式证据范围：L0 diff；L1 变更文件；L2 仓库符号、依赖和测试；L3 PR/Issue/项目文档
- 系统形态（FSE）：**evidence-escalation verifier**（嵌套证据包 + progressive stop + 可追溯 artifact），不是 multi-agent reviewer，也不以 agent 叙事作为主贡献

## FSE 冲刺范围（相对原方案的预注册缩小）

- **数据集：** 已冻结 4 仓库、48 条评论的 **Challenge set**（`stage-s-pilot-candidate-v0.1`）；**不声称 natural prevalence**
- **语言：** 本稿 Python-only；Java 列为外部有效性限制
- **Gold：** Stage S（进行中）→ 仲裁 → Stage V 双标；目标为全部 MATERIAL claims， honestly 报告 attrition
- **主 RQ：** RQ2 diff-only 构念误差；RQ3 定向升级 vs diff-only / token-matched full-context / top-k RAG
- **次 RQ：** RQ1 描述性 `L*` 分布；RQ4 risk–coverage（时间允许则做，否则 exploratory）

## 交付物

1. Claim-level 任务定义与 v0.3 人工标注协议  
2. 4 仓库 challenge benchmark 与 adjudicated gold  
3. Diff-only 误拒测量结果  
4. EviScope 原型（L0–L3 escalation + stop policy）  
5. 配对基线与聚类统计  
6. 匿名复现包与 18 页论文  

## 硬边界

1. 不把“diff 中不可证”直接称为 hallucination。  
2. 不声称 natural prevalence（本 pilot 不是 random natural sample）。  
3. 不把开发者接受、回复或后续修复直接当作正确性金标准。  
4. 不用同一模型同时生成评论、构造证据和提供最终金标签。  
5. 不在看到测试集结果后修改标签定义、主指标或成功阈值。  
6. 旧 EviReview 六个手工任务不得进入主结果。  
7. 不用 ReAct/agent 包装替代 evidence-escalation 方法与 gold 独立性。  

## 不包含

- 外部互联网 L4、模型训练、多代理 reviewer、自动修复、线上开发者实验  
- SANER Agentic 赛道所需的 agent-first 叙事（已弃用为该投稿默认）  
