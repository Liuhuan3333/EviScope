# Section Contracts

## Introduction
- Purpose：建立 diff alignment 与 repository validity 的构念差异。
- Required evidence：HalluJudge、ContextCRBench、试点 prevalence 和错误拒绝结果。
- Forbidden：声称 HalluJudge 错误；在无数据时声称现象普遍。

## Background and Related Work
- Purpose：区分 hallucination detection、review quality evaluation、context-aware generation、claim verification 与 abstention。
- Required evidence：经核实的一手论文。
- Forbidden：仅罗列论文；使用未经核实引用。

## Task and Dataset
- Purpose：给出可复现的三态任务、证据层级、采样和标注协议。
- Required evidence：schema、annotation guide、agreement、样本流失图。
- Forbidden：将接受/修复作为唯一 gold；隐藏排除样本。

## Approach
- Purpose：描述 claim decomposition、triage、retrieval、verification、stopping 和 release policy。
- Required evidence：算法、预算、retrieval index、模型版本和 prompt hash。
- Forbidden：把工具工作流包装成理论创新。

## Study Design
- Purpose：预先固定 RQ、基线、主终点、统计检验和消融。
- Required evidence：预注册时间戳、功效/精度分析、repo-level split。
- Forbidden：测试后选择指标或阈值。

## Results
- Purpose：按 RQ 报告效应量、置信区间和失败案例。
- Required evidence：原始计数、CI、配对检验、跨仓库分布、成本。
- Forbidden：只报平均分；把统计显著当作工程显著。

## Discussion and Threats
- Purpose：解释证据边界、语言/仓库外部效度、judge 和标注偏差。
- Forbidden：声称普适到所有语言、闭源仓库或安全审查。

## Data Availability
- Purpose：满足 FSE 2027 要求，说明匿名复现包、最终公开计划和限制。
- Forbidden：泄露作者身份或仓库私有信息。

