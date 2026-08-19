# EviScope：FSE 2027 完整研究实施方案

> 工作标题：*Unknown Is Not Hallucinated: Evidence Escalation for Reliable Code Review Verification*  
> 方案冻结日：2026-08-14  
> FSE 2027 Full Paper：2026-10-02 AoE  
> 决策：Conditional Go；必须在 2026-08-24 通过先导关卡

## 1. 投稿约束与现实判断

FSE 2027 Research Track 要求不超过 18 页正文和图表，另加 4 页参考文献；实行 heavy double-anonymous review；每篇至少三名审稿人；初审结果可能是 accept、reject 或 major revision；要求在结论后提供 Data Availability。会议于 2027-07-12 至 07-16 在深圳举行。

从 2026-08-14 到 10-02 只有 49 天。该窗口不允许从零开展“大规模、多语言、多代理、线上开发者研究”。可行的论文形态必须是：

1. 一个新的、严格定义的经验任务与人工标注基准；
2. 一项证明 diff-only 验证边界的测量研究；
3. 一个简单但可复现的按需证据升级方法；
4. 完整基线、统计分析和匿名复现包。

若只有一名研究者且没有两名额外标注人员，FSE 2027 主会时间上不成立，应该把目标调整为 FSE 2028/ICSE 2028，而不是牺牲标注独立性。

## 2. 研究目标与 RQ

### RQ1：证据需求分布

真实代码审查主张中，有多少能够由 diff 验证，有多少需要文件、仓库或 PR/Issue 证据？

- H1：需要 L1-L3 的 SUPPORTED 主张不是边缘现象。
- 主指标：自然分布集中 beyond-diff SUPPORTED claims 的比例及 repo-cluster bootstrap 95% CI。

### RQ2：Diff-only safeguard 的构念误差

Diff-only judge 是否会系统性拒绝需要 diff 外证据的正确主张？

- H2：L1-L3 SUPPORTED claims 的错误拒绝率高于 L0 claims。
- 主指标：错误拒绝率差，报告绝对百分点、风险比和 95% CI。

### RQ3：按需证据升级

EviScope 是否优于 diff-only、full-context 和 generic top-k retrieval？

- H3a：EviScope 相比最强 diff-only 基线降低至少 10 个百分点的 beyond-diff 错误拒绝率。
- H3b：错误接受率不劣于最强基线；预先把可容忍绝对增幅设为 2 个百分点，另报告 95% CI。
- H3c：相较 full-context，EviScope 使用更少输入 token，或在相同预算下取得更高 macro-F1。

### RQ4：选择性发布

三态判断和弃权能否在给定风险下提高可靠覆盖率？

- 主指标：AURC，以及错误接受率不超过 5% 时的最大 coverage。
- 防游戏化：风险与 coverage 必须成对报告。

## 3. 任务形式化

给定评论 `C`、代码变更 `D`、review-time evidence universe `U`，先将评论拆成原子主张 `c_i`。对某一可见证据包 `K_l`：

```text
V(c_i, K_l) ∈ {SUPPORTED, CONTRADICTED, INSUFFICIENT}
```

证据包嵌套：

```text
K0 = diff
K1 = K0 + changed-file before/after + enclosing function/class
K2 = K1 + definitions + callers/callees + imports + tests + project configuration
K3 = K2 + PR description + linked issue + repository documentation/history available at review time
```

`L*` 是专家第一次能稳定裁决该主张的层级。若 K3 仍不可裁决，终局标签为 INSUFFICIENT。第一篇论文排除外部网页规范，避免不可冻结的信息源。

评论级 release rule：只有所有 material claims 均为 SUPPORTED 时才自动发布；存在 CONTRADICTED 则拒绝；存在 INSUFFICIENT 则弃权。另做聚合规则消融，但不在测试后挑选最优规则作为主结果。

## 4. 数据集

### 4.1 两个互补集合

**Natural set**：按预注册规则随机采样 PR 与评论，用于估计 prevalence。不得按“是否需要仓库上下文”筛选。

**Challenge set**：按 L0-L3、标签和评论类型分层补充，用于比较方法能力。不得用它估计现实比例。

### 4.2 目标规模与最低规模

目标：8 个仓库，Python/Java 各 4 个；约 220 条评论、400–500 个原子主张。

- Natural：至少 120 条评论、约 220–280 claims；
- Challenge：至少 100 条评论、约 180–220 claims；
- 最低可投稿门槛：6 个仓库、300 个完成双人标注的 claims；
- 低于最低门槛：不做跨语言或 prevalence 强主张，原则上停止 FSE 2027 冲刺。

目标不是依靠 400 个相互独立的 claim 获得虚假大样本。统计单位存在 PR/repo 聚类，必须使用聚类 CI 或混合效应模型。

### 4.3 仓库选择

纳入标准：

- OSI 兼容许可证；
- 可恢复 PR base/head SHA 和 review-time 文件；
- 近两年有活跃 PR 与 review；
- 测试和项目结构可解析；
- PR/Issue 可合法公开再分发或以可重建 manifest 发布。

排除标准：

- 无法恢复 review-time snapshot；
- 评论主要是格式、社交或机器人模板；
- 评论依赖私人组织知识；
- 大型生成文件、vendor 代码或跨仓库秘密配置。

仓库在完成标准后再抽样，不能根据初步结果挑选“故事更好”的仓库。

### 4.4 评论来源与偏差控制

评论来自两部分：真实人类评论和模型生成候选评论。模型生成用于补充 CONTRADICTED/INSUFFICIENT 样本，但不能进入 natural prevalence 的人类评论估计。

- 生成器与 judge 模型尽量分离；
- 测试仓库不得用于 prompt 调整；
- 人类评论的 developer acceptance、reply 和 subsequent fix 只作为元数据；
- 后续修复可帮助定位证据，但不能单独决定 gold。

### 4.5 防泄漏

- 所有 evidence 截止于评论产生时刻；
- 冻结 base/head SHA、PR/Issue 更新时间和抓取时间；
- 不向模型提供人工撰写的解释性上下文；只提供原始 artifact；
- development/test 按 repository 分割；
- prompt、阈值和 retrieval budget 在 test 前冻结；
- 新模型或更新版本不得静默替换，记录精确 model ID、日期和参数。

## 5. 标注协议

### 5.1 两阶段标注

**阶段 A：claim segmentation**

两名标注者独立将评论拆为 material atomic claims。纯建议语气、礼貌文本和无事实含义的偏好单独标记，不强行做事实验证。先在 30 条评论上修订手册。

**阶段 B：evidence adjudication**

按 K0→K3 逐层展示 artifact。每层记录：是否可裁决、标签、决定性证据位置和置信度。为降低锚定偏差，至少 20% 样本由另一组标注者从完整 evidence package 反向核验。

### 5.2 每条 claim 的必填字段

- claim text 与原评论 span；
- material/non-material；
- status；
- L*；
- support/refute evidence spans；
- repo、PR、commit、path、symbol、line mapping；
- issue type；
- annotator confidence；
- disagreement reason 与 adjudication record。

### 5.3 一致性门槛

- segmentation：span-level F1 或 unitized alpha；
- 三态标签：Krippendorff’s alpha ≥0.70；
- beyond-diff 二分层级：κ/alpha ≥0.70；
- 若三态一致性 <0.60，停止主任务；0.60–0.70 只能在改手册后重新试点；
- 报告逐标签 confusion，不能只报总体 alpha。

标注者必须至少有一人能够实际阅读对应语言代码。仲裁者不能只是让 LLM 投票。

## 6. EviScope 系统

### 6.1 模块

1. `claim_extractor`：输出原子主张和 source span；
2. `diff_triage`：在 K0 上做三态判断；
3. `query_planner`：从 claim、diff、符号和路径生成结构化查询；
4. `evidence_retriever`：依次搜索 L1-L3；
5. `evidence_verifier`：输出 verdict、证据 ID 和置信度；
6. `stop_policy`：找到支持/反驳证据、达到预算或边际收益不足时停止；
7. `release_policy`：评论级 accept/reject/abstain；
8. `trace_logger`：记录 prompt hash、artifact hash、token、延迟和每步输出。

### 6.2 MVP 检索顺序

优先采用可解释、可复现的确定性检索：

1. changed hunk → enclosing function/class；
2. claim/diff 中 identifier → definition/reference；
3. import 和 call relation；
4. 同 symbol/path 相关测试；
5. PR/Issue 中 lexical links；
6. repository docs/history。

MVP 可用 Tree-sitter、ripgrep/git grep、语言服务器或轻量静态索引。向量检索作为基线，不应成为系统唯一检索手段。

### 6.3 预算

主实验预注册统一预算，例如：最多 5 次 retrieval action、最多 12 个 evidence chunks、最多 12k 输入 token。另画 cost-quality curve，而不是只选有利预算。

### 6.4 两层评估

- Oracle-claim：提供人工 claim segmentation，隔离 retrieval/verifier 能力；
- End-to-end：使用自动 claim extractor，衡量完整系统。

没有 oracle-claim 层，claim extraction 错误会掩盖核心机制；只有 oracle-claim 层，又无法证明部署可用性。

## 7. 基线与实验矩阵

### 7.1 方法基线

- B0：diff-only direct judge；
- B1：HalluJudge Direct；
- B2：HalluJudge structured/ToT；
- B3：changed-file/full-context concatenation；
- B4：generic lexical top-k + judge；
- B5：generic embedding top-k + judge；
- B6：Oracle gold evidence + judge；
- P：EviScope targeted escalation。

CRScore 可作为 comment quality 的补充指标，不是 support-status 主基线。

### 7.2 模型

至少冻结三类 judge：一个强闭源通用模型、一个可部署开源指令模型、一个代码导向模型。所有方法在同一模型内配对比较，禁止把“方法 A + 强模型”与“方法 B + 弱模型”直接比较。

主实验 temperature=0 或供应商最接近确定性的设置；在 15% 分层子集上做 3–5 次重复，估计非确定性。模型名称应在实验冻结时根据实际可访问版本写入 registry。

### 7.3 消融

- 去掉三态，强制二分类；
- 去掉 symbol/call retrieval，仅 lexical；
- 不使用分层停止，直接 full-context；
- 去掉 PR/Issue L3；
- oracle claims vs automatic claims；
- oracle evidence vs retrieved evidence。

主论文最多保留能回答机制问题的消融，避免无意义组合爆炸。

## 8. 指标与统计

### 8.1 主终点

Primary endpoint：在 gold SUPPORTED 且 L*>L0 的 claims 上，EviScope 相对最强 diff-only baseline 的错误拒绝率绝对下降。

Safety endpoint：在 CONTRADICTED/终局 INSUFFICIENT claims 上的错误接受率变化。

### 8.2 其他指标

- claim-level macro-F1；
- 每类 precision/recall；
- L* accuracy 与 weighted kappa；
- evidence Recall@1/5、MRR、证据 span recall；
- comment-level all-claims-supported precision；
- token、latency、retrieval actions；
- AURC 与固定风险 coverage。

### 8.3 检验

- RQ1：repo-cluster bootstrap prevalence CI；
- RQ2：mixed-effects logistic regression，evidence level 为固定效应，repo/PR 为随机截距；
- RQ3：同一 claim 的配对 bootstrap 或 McNemar，报告效应量与 CI；
- RQ4：paired bootstrap 比较 AURC；
- 多重比较：只为预注册 primary family 使用 Holm 修正；
- exploratory analyses 明确标记，不与 confirmatory 结论混写。

不以 p<0.05 代替实际意义。主要结果必须同时满足效应方向、置信区间和安全终点。

## 9. Go/No-Go

### Gate 0：2026-08-16，资源

必须确认：两名独立标注者、一名仲裁者、API/算力预算、仓库快照脚本可用。任一缺失则停止 FSE 2027 冲刺。

### Gate 1：2026-08-24，科学现象

完成 30–50 条评论、至少 60 个 claims 的盲化试点。继续条件：

- ≥20% gold SUPPORTED claims 的 L*>L0；或其 CI/案例结构显示有扩大采样的合理依据；
- diff-only 对 beyond-diff claims 的错误拒绝至少高 10 个百分点；
- 三态和 beyond-diff 标注一致性 ≥0.70；
- gold evidence 定位可达到 ≥80% 完整率；
- deterministic retrieval 的 evidence Recall@5 ≥0.70；
- 提供 oracle evidence 后 judge 明显优于 diff-only。

若 oracle evidence 也不改善 judge，说明核心瓶颈不是检索，主方法应停止。

### Gate 2：2026-09-07，数据与系统

- ≥300 claims 完成双标，目标 400+；
- ≥6 repos，目标 8；
- 测试集冻结；
- 所有主基线跑通；
- EviScope 无 schema/trace 缺失；
- 初始效果不依赖单一仓库或单一模型。

不通过则停止 FSE 2027，保留为下一窗口，不使用不完整结果强投。

### Gate 3：2026-09-20，论文证据

- 主结果与安全终点完成；
- 所有数字可由一条命令从冻结 manifest 重建；
- 18 页初稿完成；
- 匿名 artifact 可运行；
- 至少一次内部红队审稿。

## 10. 49 天倒排计划

| 日期 | 研究线 | 工程线 | 写作/开放科学线 | 验收物 |
|---|---|---|---|---|
| 08-14–08-16 | 冻结构念、RQ、标签 | 创建 schema、model registry | 系统检索更新；核对 FSE 政策 | protocol v0.1；Gate 0 |
| 08-17–08-20 | 选 4 个试点仓库，抽 30–50 评论 | snapshotter、claim/evidence UI | 写 Introduction skeleton | pilot corpus |
| 08-21–08-24 | 双标、仲裁、复现 diff-only/HalluJudge | deterministic retriever spike | 冻结 pilot report | Gate 1 决策 |
| 08-25–08-31 | 扩大 natural/challenge sampling | L1-L3 retriever、verifier、trace | 写 Task/Dataset/Approach | ≥180 claims 双标 |
| 09-01–09-07 | 完成主标注；冻结 train/dev/test | 跑全部基线和 oracle | 预注册 RQ/指标/分析 | Gate 2；≥300 claims |
| 09-08–09-13 | 主实验、重复性子集 | 失败重试但不改 protocol | 写 Study Design/Related Work | raw results v1 |
| 09-14–09-17 | 统计、消融、误差分析 | 一键重建表图 | 写 Results/Threats | frozen results |
| 09-18–09-20 | robustness 与泄漏审计 | 匿名 artifact smoke test | 完整 18 页初稿 | Gate 3 |
| 09-21–09-24 | 只补审稿必须实验 | 修复复现问题 | 两轮内部评审和重写 | draft v2 |
| 09-25–09-27 | 数字交叉核验 | fresh-machine reproduction | 双盲/引用/政策检查 | submission candidate |
| 09-28–09-30 | 不再扩展实验 | artifact 冻结、备份 | 最终排版与 response notes | final PDF |
| 10-01 | 上传并检查 | 校验附件 | 作者、题目、匿名信息检查 | 提前提交 |
| 10-02 AoE | 仅处理提交系统问题 | 不改科学结果 | 截止 | submitted |

08-25 后研究、工程、写作必须并行。等实验全部完成再写论文会错过截止。

## 11. 人员与预算

最低配置：

- 负责人：任务定义、系统、统计和论文统筹；
- 标注者 A/B：独立 claim/evidence 标注；
- 仲裁者：解决分歧并做 20% 反向审计；
- 可选工程协作者：数据抓取和 artifact。

约 400 claims、双人每条 10–15 分钟，纯标注约 133–200 人时，另加培训和仲裁。因此一人无法在七周内同时保证双标和完整系统。

API 预算必须在 pilot 后按实测 token 估算：

```text
总成本 = claims × methods × models × repeats × 每次平均成本
```

主实验避免全组合重复；仅对 15% 分层子集重复。预留 20% 失败重试预算，并保存供应商原始 usage。

## 12. Artifact 与研究治理

建议目录：

```text
eviscope/
  configs/
  schemas/
  data/manifests/
  data/annotations/
  src/snapshot/
  src/claims/
  src/retrieval/
  src/verification/
  src/policy/
  experiments/
  analysis/
  prompts/
  tests/
  paper/
```

每次运行记录：git commit、dataset manifest hash、prompt hash、model ID、temperature、seed、时间、token、原始输出、parser 状态。无效 JSON 不得静默删除。

匿名复现包必须：

- 不包含作者名、个人 GitHub URL、实验室路径；
- 提供环境锁定和最小 smoke dataset；
- 无 API key 时可复现数据处理、统计和论文表图；
- 明确哪些原仓库内容因许可证只提供重建脚本；
- 包含 Data Availability 草稿。

由于本研究会使用 LLM 参与数据生成、方法实现和实验，FSE/ACM 政策要求在 methods 中详细描述与研究结论直接相关的 AI 使用。不能只在致谢中笼统写“使用了 ChatGPT”。

## 13. 预期论文结构

| 章节 | 页数预算 |
|---|---:|
| Abstract + Introduction | 2.0 |
| Background/Related Work | 2.0 |
| Task Definition | 2.0 |
| Dataset and Annotation | 3.0 |
| EviScope | 2.5 |
| Study Design | 2.0 |
| Results | 3.0 |
| Discussion/Threats | 1.2 |
| Conclusion | 0.3 |

主图建议：任务构念与 evidence escalation 流程。主表建议：方法在 beyond-diff claims 上的错误拒绝、错误接受、coverage、token 和 evidence recall。

## 14. 最高风险及应对

1. **与 ContextCRBench 重叠**：必须做逐字段数据和任务矩阵；若其数据已经含完整 claim evidence labels，立即重定向。
2. **最低证据层级主观**：嵌套包、独立双标和反向审计；一致性不过关就删掉 L* 预测贡献。
3. **INSUFFICIENT 无法证明**：绑定 K3 和预算，不主张现实绝对真假。
4. **检索提升来自额外 token**：加入 token-matched full-context/top-k 基线并绘制成本曲线。
5. **LLM judge 自我偏好**：跨模型、生成器/judge 分离、人工 gold、报告模型间差异。
6. **数据不自然**：natural 与 challenge 分开，生成评论不能用于人类评论 prevalence。
7. **时间不足**：三个硬 gate；任何 gate 失败就转下一投稿窗口。

## 15. 最终投稿判据

只有同时满足以下条件才提交 FSE 2027：

- 任务标签一致性达到门槛；
- 数据规模达到最低线且 sampling 可解释；
- beyond-diff 现象在多个仓库存在；
- EviScope 对主终点有实际显著改善；
- 安全终点没有明显恶化；
- 相比 ContextCRBench、HalluJudge 的增量能用一张表清楚解释；
- 论文所有核心数字可从匿名 artifact 重建；
- 无未经核实引用、无未来信息泄漏、无双盲泄漏。

若这些条件没有同时满足，最严谨的决定是不投 FSE 2027，而不是降低标准。失败的试点仍可形成更强的 FSE 2028/ICSE 2028 研究基础。

