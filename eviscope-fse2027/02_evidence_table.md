# Evidence Table

| 候选主张 | 证据 | 强度 | 用途 | 风险 | 状态 |
|---|---|---|---|---|---|
| diff-conditioned alignment 与 repository-conditioned validity 是不同构念 | HalluJudge 的 diff grounding 定义；真实 review artifact 层级 | plausible-inference | 动机、任务定义 | 必须避免稻草人化 HalluJudge | plausible-inference |
| PR/Issue 和代码上下文可能改变 review 判断 | ContextCRBench | evidence-backed | 动机、RQ1 | 不等于支持按需升级 | evidence-backed |
| 无差别增加上下文可能引入噪声 | ContextCRBench；SWE-PRBench 预印本 | evidence-backed/初步 | H3 | 后者为较新预印本，权重应低 | plausible-inference |
| 代码审查评论的幻觉是实际问题 | HalluJudge；Liu et al. 2025 | evidence-backed | 背景 | 数据分布不同，不能外推本研究 prevalence | evidence-backed |
| 现有 RAG reviewer 已较拥挤 | RevMate、LAURA、retrieval-augmented review generation | evidence-backed | 创新边界 | 仍需持续检索 2026 新作 | evidence-backed |
| 三态判断会降低错误拒绝 | 尚无本项目数据 | hypothesis | H2/H4 | 核心假设可能失败 | hypothesis |
| Targeted escalation 优于全文上下文 | 尚无本项目数据 | hypothesis | H3 | 可能被强长上下文模型否证 | hypothesis |
| L1-L3 有效主张占比足以支撑论文 | 尚无本项目数据 | hypothesis | Go/No-Go | 若下置信界低于 10%，主故事显著变弱 | hypothesis |

