# FSE 2027 sprint revision — research direction

Revision date: 2026-08-19  
Authority: project lead  
Supersedes SANER Agentic packaging; restores original FSE research core with a pre-registered scope shrink.

## 1. 你原来的方向是对的

原始 FSE 方案的核心并没有错：

- **构念分离：** diff 对齐 ≠ 仓库/PR 条件下的有效性；`INSUFFICIENT` ≠ 幻觉。
- **任务单位：** 原子 claim 级三态验证，而不是整句 reviewer 生成。
- **证据纪律：** review-time 冻结、L0–L3 嵌套、 progressive stop。
- **科学问题：** diff-only safeguard 是否系统性误拒 beyond-diff 的有效评论；定向升级能否在可控成本下改善。

这些与 `03_argument_map.md`、`01_research_canon.md`、v0.3 标注协议完全一致，也是 FSE 最吃的贡献类型：**新任务 + 测量 + 方法 + 基线 + 威胁**。

## 2. 哪里跑偏了

转向 SANER Agentic 时，贡献重心被换成了：

- “是不是 agent”（tool loop、trace、Relevance 到 agentic SE）；
- 10 页 IEEE 压缩叙事；
- 为了赛道 fit 而弱化 **benchmark + construct measurement** 的主线。

这对 SANER 新赛道合理，但**不是你的原题**。原题在 FSE 上更强，因为：

- HalluJudge 已占 diff-only 幻觉检测；
- ContextCRBench / RAG reviewer 已占“更多上下文”；
- **你真正的增量**是 claim-level 三态、最低证据层级、错误拒绝作为 safeguard 指标——这不是 agent 包装能替代的。

因此：**Stage S 继续；agent 尖刺改为 evidence-escalation MVP；论文叙事回到 FSE 原方案。**

## 3. 修订后的 FSE 2027 论文主张（投稿版）

### 贡献（写进 Introduction 的三条）

1. **Task & benchmark：** 首个（在系统检索确认前不写“首个”进摘要）面向 code review 的 **claim-level review-time verification** 任务，含 materiality screening、三态标签、嵌套证据包与人工 gold 协议。
2. **Measurement：** 在 4 仓库 challenge benchmark 上量化 **diff-only judge 的构念误差**——对 beyond-diff 有效主张的错误拒绝。
3. **Method：** **EviScope**——预算受限、按层级定向升级证据的验证器，相对 diff-only 与 token-matched full-context / top-k RAG 改善错误拒绝，且不明显恶化错误接受。

### 明确不主打

- 多 agent reviewer；
- 自然分布 prevalence（48 条 pilot 不是 natural set）；
- “我们做了一个 agent”；
- 开发者采纳/后续修复当 gold。

## 4. RQ 修订（FSE 优先级）

| RQ | 原方案 | FSE 冲刺修订 |
|----|--------|--------------|
| RQ1 证据需求分布 | natural prevalence | **降为描述性：** 仅在 challenge set 报告 `L*` 分布；不写 population prevalence |
| RQ2 diff-only 构念误差 | 主测量 | **保留为主结果之一** |
| RQ3 定向升级 | H3a/b/c 全做 | **保留 H3a/b；H3c token 效率作次要** |
| RQ4 选择性发布 | AURC 主终点 | **降为次要/exploratory**，除非 9 月中旬前 gold 很充裕 |

## 5. 数据规模修订（诚实但可投）

| 项 | 原目标 | FSE 冲刺目标 |
|----|--------|--------------|
| 仓库 | 8（Py+Java 各 4） | **4（已冻结 pilot 四仓库，Python 为主）** |
| 评论 | 220 | **48（已选，pre-registered）** |
| Claims | 400–500 双标 | **全部 MATERIAL claims 双标 + 仲裁；目标 ≥80 完成 Stage V 即可谈方法，≥120 更稳** |
| 集合 | Natural + Challenge | **仅 Challenge set；Threats 明确说明** |
| 语言 | Py + Java | **Python-only 本稿** |

低于原方案 300-claim 门槛，但 FSE 仍可能接受，如果：

- 任务定义和协议足够严；
- beyond-diff 现象在多个仓库重复出现；
- 方法对比完整、统计聚类正确；
- 诚实报告 attrition 与限制。

## 6. 应该改进的地方（相对原方案）

### 6.1 研究设计

1. **Challenge-first 写进摘要与 Threats 第一句**  
   不要假装 48 条是 random natural sample。FSE 审稿人更吃诚实的设计说明。

2. **Oracle-claim 层提前到 9 月第一周末**  
   先证明“给对证据时 judge 能判对”，再评 retrieval。否则 retrieval 失败与 judge 失败混在一起。

3. **L* 一致性不过关就降级**  
   若 minimum evidence level 的 κ 低，主文保留三态与错误拒绝，L* 放 appendix / future work。不要硬撑第四条贡献。

4. **HalluJudge 对齐表**  
   单独做一张 task matrix：单位（claim vs comment）、标签空间、证据宇宙、主指标。这是防 ContextCRBench/HalluJudge 重叠质疑的关键。

5. **Token-matched 基线必须做**  
   FSE 会问“是不是只是多给了 token”。full-context 与 top-k 都要匹配预算。

### 6.2 工程

1. **Git 今天做** — FSE Data Availability 和复现包硬需求。  
2. **Stage S 继续** — 已在进行，这是 gold 的前置，不是可选项。  
3. **Evidence builder 优先于 agent loop** — 对 FSE，L0–L2 冻结 artifact 比 ReAct 轨迹重要。  
4. **一键重建表图** — 从 9/14 起所有数字必须 manifest-driven。  
5. **双盲从第一天起** — 匿名 Zenodo、无 lab 路径、无作者名在 artifact。

### 6.3 写作（8/25 后并行）

FSE 18 页允许把 Task/Dataset/Protocol 写厚。建议页数：

- Intro + RQs: 2
- Background + Related: 2
- Task definition + protocol: 3
- Dataset + annotation study: 3
- EviScope method: 2.5
- Study design + baselines: 2
- Results: 3
- Threats + conclusion: 0.5 + Data Availability

## 7. 44 天倒排（高强度版）

| 日期 | 研究 | 工程 | 写作 |
|------|------|------|------|
| 08-19–08-26 | A/B Stage S；C 待命 | git；L1 builder smoke；oracle judge smoke | Intro bullet outline |
| 08-27–09-03 | Stage S 仲裁冻结 | L2 builder；Stage V 工具/流程 | Task + Dataset skeleton |
| 09-04–09-10 | Stage V A/B + 仲裁 | EviScope MVP；diff-only + oracle | Related Work + Study Design |
| 09-11–09-17 | 主实验 dev 集 | full-context + top-k baselines | Results 空表 + 图模板 |
| 09-18–09-24 | 统计 + 消融 | 一键重建；匿名 artifact | 完整 18 页 v1 |
| 09-25–09-30 | 只补审稿必要实验 | fresh-machine smoke | 双盲 + 引用检查 |
| 10-01–10-02 | 提交 | 冻结 | final PDF |

每天加长工时主要应加在：**Stage V 双标 + 证据包构建 + 写作并行**，而不是 agent 框架打磨。

## 8. 什么情况下仍应停 FSE 2027

即使用更长工时，以下任一成立仍应停投或改投下一窗口（不是 SANER 降级，是科学停止）：

- 第三人仲裁无法执行；
- adjudicated MATERIAL claims 过少或 beyond-diff SUPPORTED 几乎为零；
- oracle evidence 不能改善 judge；
- EviScope 不优于 token-matched full-context；
- gold 独立性或 review-time 泄漏无法辩护。

## 9. 结论

**你的原 FSE 方向比 SANER agent 包装更贴题、也更像一篇 FSE 会接受的 empirical SE 论文。**  
SANER  detour 的唯一正资产是：Stage S 已开标、人员已就位——这些对 FSE 完全复用。

下一步优先级（FSE 顺序）：

1. A/B 完成 Stage S  
2. Git  
3. L1–L2 evidence + Stage V gold  
4. Oracle-claim → EviScope MVP → baselines  
5. 9/1 起写作并行

Authority: `governance/venue_lock_fse_2027_2026-08-19.md`
