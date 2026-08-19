# EviScope：VS Code Codex 项目交接与执行提示词

> 用法：将本文从“给 Codex 的提示词”开始完整粘贴到服务器上 VS Code 的 Codex 新会话中。本文记录的是截至 2026-08-17 的状态。Codex 必须先核验文件和哈希，不能仅凭本文宣布实验完成。

## 给 Codex 的提示词

你正在协助我完成软件工程研究项目 **EviScope**，目标投稿 **FSE 2027 Research Papers**。服务器项目根目录是：

```text
/data/disk1/Lhuan/EviScope
```

请把自己视为严谨的研究工程协作者，而不是迎合我的助手。所有结论必须区分：已核实事实、工程验证、模型预测、人工金标签和尚未验证的假设。发现方法学缺陷时必须直接指出；不要为了推进进度而降低证据标准。

### 一、研究方向与核心问题

工作标题：

> *Unknown Is Not Hallucinated: Evidence Escalation for Reliable Code Review Verification*

研究对象是代码审查评论中的**原子事实主张**，不是从零生成完整 code review。核心问题是：

> 在不显著提高错误接受率的前提下，按需证据升级能否减少 diff-only 代码审查验证器对有效评论的错误拒绝？

系统必须在冻结的 review-time 证据上对每个原子主张作三态判断：

- `SUPPORTED`：当前证据足以支持；
- `CONTRADICTED`：当前证据与主张冲突；
- `INSUFFICIENT`：在预定义证据宇宙与预算内无法支持或反驳。它不代表主张在现实世界中为假。

渐进证据层级是：

- L0：评论发生时的 diff；
- L1：变更文件的 before/after 与相关 enclosing symbols；
- L2：仓库内定义、引用、调用关系、依赖、配置与测试；
- L3：评论发生时可见的 PR 描述、关联 Issue、项目文档与历史。

只有当前层级为 `INSUFFICIENT` 时才能升级；第一次出现 `SUPPORTED` 或 `CONTRADICTED` 后停止。禁止外部互联网 L4 和评论发生后的未来信息。

中心假设是：把 `INSUFFICIENT` 与 `CONTRADICTED` 分开，并只对证据不足的主张执行预算受限的定向检索，会优于 diff-only 和无差别 full-context。

### 二、为什么不继续旧 EviReview 方向

旧 EviReview 主要研究对 LLM 代码审查评论进行幻觉/正确性判断。HalluJudge 已将代码审查幻觉操作化为“评论主张与给定 code diff 的上下文失配”，与旧方向在研究对象、输入和主要判定目标上高度重合。继续旧方向很难形成足够清晰的新增贡献。

EviScope 不应攻击或否定 HalluJudge。HalluJudge 应被视为直接相关工作和 diff-only 基线。新项目的实质差异必须由实验建立：diff 中不可证明的主张可能需要仓库级或 PR 级证据，因此“未知”不能直接等同于“幻觉”。如果真实数据无法证明 beyond-diff 主张具有可测规模，或者 targeted escalation 不能优于强基线，项目应诚实停止或缩小主张。

旧 EviReview 的六个手工任务不得进入论文主结果，只能作为历史原型或工程 smoke test。

### 三、不可违反的方法学边界

1. 不把“diff 中不可证”直接称为 hallucination。
2. 不把开发者回复、接受或后续修复直接当作正确性金标准。
3. 不允许评论发生后的 commit、测试结果或文档进入 review-time 证据包。
4. 不用同一个模型生成评论、构造证据并提供最终金标签。
5. 不把模型预标注、模型多数投票或 Codex 判断写成人工 gold。
6. Stage S 不允许查看 diff、路径、仓库、作者回复或 verdict；它只能看到盲化后的评论文本。
7. Stage V 只能使用已冻结并仲裁的 claim，不能修改 claim 文本或跨度。
8. A/B 必须独立标注；分歧必须由第三名人员仲裁。A、B 或模型不能冒充独立第三人。
9. 选择规则、主指标和停止规则不能在看到测试结果后偷偷修改。
10. 数据按 repository/PR/actor 保留聚类关系；统计时不能把同一 PR 内评论视为完全独立。
11. 不宣称现实 prevalence，除非未来建立预定义的随机自然分布样本。
12. 不使用“首个、首次、全面解决”等措辞，除非系统文献检索确实支持。

正式标注协议为：

```text
governance/annotation_guide_v0.3.md
schemas/materiality_screening.schema.json
schemas/annotation_v0.3.schema.json
```

v0.1/v0.2 仅保留为协议历史，新数据不得静默降级到旧版本。

### 四、截至 2026-08-17 已完成的工作

#### 1. 工程 scaffold

- 数据、标注、Pilot 和服务器环境 JSON schema 已建立；
- dependency-free semantic validator 和单元测试已建立；
- review-time snapshot builder 已建立；
- 服务器环境采集脚本不收集密钥、用户名、主机名或网络地址；
- 本地历史验证曾达到 24/24 tests；之后加入 review snapshot 与 v0.3 协议，当前实际测试数必须重新运行确认，不能沿用旧数字。

进入工作目录后首先运行：

```bash
cd /data/disk1/Lhuan/EviScope
python3 scripts/validate.py --all
python3 -m unittest discover -s tests -v
```

#### 2. 服务器与本地模型

服务器已确认：

- 8 张 NVIDIA A100-SXM4-80GB；
- 约 1 TiB 内存；
- `/data/disk1` 约 3.5 TiB；
- Docker 可由 `Lhuan` 用户使用；
- 当前 EviScope vLLM 容器使用 GPU 1、3；未经我明确授权不要停止、删除或重建该容器。

模型服务：

```text
endpoint: http://127.0.0.1:18000
served model: qwen3-coder-30b-a3b
weights: Qwen3-Coder-30B-A3B-Instruct, bfloat16
tensor parallel: 2
max model length: 32768
vLLM: 0.14.1.dev1+gd68209402
container image digest:
vllm/vllm-openai@sha256:bb3c2948540aecfe5f65950ec06b3c080139ba37fd4d236c32ab11872039ebe2
```

健康检查：

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:18000/health
curl --noproxy '*' -sS http://127.0.0.1:18000/v1/models
```

服务器环境曾通过：

```text
python3 scripts/validate.py server_environment.json
```

但 `governance/gate0_status.json` 可能仍是较早状态。只能根据真实、可审计证据更新，不能因为模型能运行就把整项 Gate 标为 passed。

#### 3. GitHub 网络注意事项

服务器 shell 中存在失效的本地代理环境变量，通常指向 `127.0.0.1:17897`。访问 GitHub 时优先显式绕过：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
git -c http.proxy= -c http.version=HTTP/1.1 ...

curl --noproxy '*' ...
```

Git smart HTTP 偶发约 130 秒超时。仓库使用 partial clone 时，`git diff` 可能触发 promisor remote lazy fetch。已下载的对象会保留；不要删除仓库重来。应逐 blob 重试、核验 object ID，再生成快照。任何空 diff 的 SHA-256 `e3b0c442...` 都是失败产物，不能登记为证据。

#### 4. 已重建并审计的候选 PR

所有 snapshot 都必须以 inline comment 的 `original_commit_id` 为 review head，而不是用最终 PR head 替代。

**pytest #14523**

- 5 个 review-time snapshots；
- 26 条 inline records；
- 20 条 `HUMAN_REVIEWER`，6 条 `AUTHOR_CONTEXT`；
- 2 名 reviewer；
- reviewer 锚点失败 0；
- anchor audit SHA-256：`2664ee78da57b6d4de5a6130082e87310b4882a997c293635c7590178bcd6986`。

**Django #20583**

- 8 个 snapshots；
- 47 条 inline records；
- 28 条 `HUMAN_REVIEWER`，19 条 `AUTHOR_CONTEXT`；
- 4 名 reviewer；
- reviewer 锚点失败 0；
- 一条 GitHub API 空 hunk 使用 `API_LINE_COORDINATE`，其余为强 hunk/body 锚点；
- anchor audit SHA-256：`64cc811a6e9b2d8fe50820ddff0afd7a85ba6b19867cedf6caa5730869b6fd4f`。

**Quarkus #52871**

- 4 个 snapshots；
- 17 条 inline records；
- 16 条 `HUMAN_REVIEWER`，1 条 `AUTHOR_CONTEXT`；
- 2 名 reviewer；
- reviewer 锚点失败 0；
- snapshot manifest SHA-256：`e1876f6a81c4ef21b63ef01e6eddf1e1ca2940b71d1f7ddbdc9fe55e3868ad22`；
- anchor audit SHA-256：`0683c1437b6742f3dd41636982ba12deba6aeba70f0cfbd17533bdf94157ec7f`。

**scikit-learn #34412**

- 4 个 snapshots；
- 27 条 inline records；
- 18 条 `HUMAN_REVIEWER`，9 条 `AUTHOR_CONTEXT`；
- 3 名 reviewer；
- reviewer 锚点失败 0；
- snapshot manifest SHA-256：`f8574dff9e41436860c9e0b653697da9e45edad0933dfb8f1def0203f4f0298f`；
- anchor audit SHA-256：`186beb6beb2dbc955e9a57a9825c23b54b279ce5e2b03d78f065d47a4b09cd68`。

scikit-learn 的两个不同 review heads：

```text
8341c2029b9fd763bd908798a0886241fa2b4e22
b4174c03dd7d3e597badb7f041d40679a3559aed
```

对应不同 base/tree，但 L0 diff 哈希相同。已查明第二个是把新 `main` 合入 PR 分支的 merge commit。这是合法的 evidence-equivalent state：必须保留各自评论和 provenance；模型推理可按 L0 SHA 缓存，统计记录不得合并。

#### 5. 已排除或降级的候选

- Maven #11639：只有 3 条 reviewer target，作为校准/低密度 control，不进入主 Pilot 推断；
- Spring #36641：发生 base-ref change 与 force-push，历史基线恢复存在歧义，排除；
- JUnit #5258：58 commits、29 files，作为规模压力候选，不进入当前主 Pilot；
- Kafka #22191：规模过大，当前排除；
- 旧 EviReview 六任务：仅工程 smoke，不进入分析。

不要为了增加样本量重新纳入已记录为历史歧义或规模不合适的 PR，除非先修改并登记 inclusion protocol，且理由与标签结果无关。

#### 6. 已冻结的跨仓库 Stage-S 候选包

目录：

```text
data/private/pilot/stage-s-pilot-candidate-v0.1/
```

冻结规则：四仓库各选择 12 条已锚定 reviewer 评论；先覆盖 reviewer × review-state strata，再用预注册 SHA-256 rank 补足；选择不使用评论内容、materiality、claim 或 verdict。

结果：

- 48 条评论；
- 四仓库各 12 条；
- 覆盖 11 个 reviewer actor groups；
- 覆盖 21 个 review states；
- 盲化包中只包含 `sample_id` 与 `comment_text`；
- private map 与 Stage-S 输入严格分离；
- 当前状态是 `pre_gate_candidate_not_gold`。

冻结哈希：

```text
stage_s_inputs.json
657d6525769fb855d8e33a2f4139a044877b61cbc2aedb387db4e8e75b7e5a09

private_sample_map.json
6614ba94ab213618180ecde3295079551476204a94d42c252c7f628cba54c458

selection_manifest.json
290dbba13878bc16e339c0e32cea2542a93bfb75f3392ce0678c4c96511a6d5e
```

这些文件一旦哈希不一致，必须停止并报告，不得自动覆盖或“修复”。

#### 7. Stage-S 模型工程 smoke

S001-S008 开发集暴露了模型字符 offset 不可靠：9 个无效 fragments 中，8 个引用文本正确且唯一可定位，1 个擅自改变引号、无法对齐。不能静默改写模型引用。

随后注册 v0.2 adapter：模型只返回逐字引用文本；程序仅在文本于评论中**恰好出现一次**时计算 start/end；零次或多次均失败；原始输出永久保留。

独立 holdout S009-S016 结果：

```text
request success: 8/8
JSON parse success: 8/8
alignment valid: 8/8
decision distribution: 4 MATERIAL / 4 NON_MATERIAL
protocol SHA-256:
25e2168b4386adbc71fbff6dae1a4a1f8ff321500afae9cab295d834bf7f5cc4
result SHA-256:
064aa18d96ba93a5a0f9882bd0ac24ebbf9c5ff220bffe11c14e6ccbb93eeddb
```

这只能支持“结构化生成与确定性对齐工程可行”，不能支持 materiality accuracy、segmentation accuracy 或 gold validity。不要把剩余 32 条模型输出当作正式标注，也不要把模型结果暴露给独立人工标注者。

### 五、当前真实状态与阻塞项

项目尚未正式进入 Gate 1。当前人员条件是：我可以作为 annotator A，并可以找一名同学作为 annotator B，但尚未确认独立第三名 adjudicator。

正式推进前必须得到可审计确认：

1. annotator A 明确接受任务与 v0.3 指南；
2. annotator B 明确接受并独立工作；
3. 第三名 adjudicator 明确接受，且不冒充 A/B；
4. 记录服务器使用权限、GPU 最低可用数量和调度限制；
5. 冻结模型条件与预算上限；本地 Qwen 可作为一个条件，但论文不能只靠一个模型支撑普遍结论。

如果第三人始终无法找到，必须把 Gate 标为 blocked，不能用 Codex、Qwen 或 A/B 自己的复议代替独立仲裁。

### 六、你应当按此顺序执行后续任务

#### P0：先把一次性命令工程化并验证

目前若干 anchor audit、Pilot selection 和 model smoke 是通过审计过的一次性 Python 命令生成的。请将它们实现为可复用脚本和单元测试，但不得改变现有冻结数据：

1. `scripts/audit_comment_anchors.py`
2. `scripts/freeze_stage_s_selection.py`
3. Stage-S verbatim fragment aligner 与独立测试
4. model smoke runner，明确标记 `not_annotation_not_gold`
5. 冻结文件 hash verifier

要求：默认拒绝覆盖；输入、输出和规则都记录 SHA-256；失败显式返回非零；禁止宽泛吞掉异常；测试必须包含空 hunk、重复 fragment、找不到 fragment、offset 错误、重复 evidence-equivalent snapshot 和 future leakage 负例。

#### P1：制作人工标注工具，而不是让人手填 JSON

实现一个离线 Stage-S 标注工具，至少满足：

- 只读取 `stage_s_inputs.json`，绝不能加载 private map；
- 显示一条评论和进度，不显示仓库、路径、diff、actor 或模型预测；
- 支持选择 `MATERIAL/NON_MATERIAL`；
- non-material reason 只能来自 v0.3 注册枚举；
- material claim 可通过选中文本或精确复制文本添加 fragment；
- 工具自动计算 Unicode start/end，并立即验证 `comment[start:end] == text`；
- 支持多个有序、不重叠 fragments；
- 支持断点保存，但导出前做完整 schema/semantic validation；
- A/B 使用独立输出目录和匿名 private ID；
- 不记录姓名到可发布目录；
- 不把模型 smoke 输出提供给 A/B。

优先实现简单、可测试的本地 Web UI 或 CLI，不引入不必要的前端框架。先用 synthetic fixture 和 Maven 非 Pilot 样本测试，不打开48条正式包。

#### P2：人员校准与 Gate 判定

1. 让 A/B 阅读 `annotation_guide_v0.3.md`；
2. 使用 Maven reviewer 评论或另外冻结的非 Pilot 样本进行训练；
3. A/B 独立完成校准；
4. 第三人仲裁；
5. 只基于预注册统计报告 materiality agreement 与 segmentation disagreement；
6. 达不到阈值时修订指南并用新的独立校准集复测，不能反复改同一批答案；
7. 只有人员、协议、算力和预算条件全部满足，才更新 Gate 状态。

不要替人做标注并伪装成人类结果。Codex 可以解释规则、检查跨度、发现矛盾和生成工具，但不能填写 A/B 或 adjudicator 身份下的正式标签。

#### P3：正式 Stage S

在 Gate 通过后：

1. 复制相同哈希的盲化输入给 A/B；
2. 两人独立完成48条 materiality 与 atomic-claim segmentation；
3. 分别冻结、验证和哈希输出；
4. 在双方冻结前禁止相互查看；
5. 第三人只对分歧进行仲裁；
6. 冻结 adjudicated Stage-S claim set；
7. 报告原始评论数、角色排除、non-material attrition、material 评论数、claim 数和 disagreement 类型。

Pilot 原计划希望得到至少60个 claims，但48条评论不保证达到60。若不足，应将其作为可行性结果；不得根据标签挑选“主张更多”的评论凑数。是否扩大下一轮样本必须使用预先登记、与 verdict 无关的规则。

#### P4：构建 L1-L3 review-time evidence

只能对仲裁后 claims 进行。每个 artifact 必须含：稳定 ID、来源 locator、review-time cutoff、内容 SHA-256、evidence level 和生成方法。

- L1：before/after changed files、enclosing symbol；
- L2：定义、引用、caller/callee、imports、配置、相关测试；
- L3：当时的 PR body、关联 Issue、项目文档和可用历史。

必须实现 future-artifact detector，并建立负向测试。GitHub 当前页面内容不能直接代替历史内容。任何无法证明 review time 可用性的 artifact 都必须排除或标为不可用。

#### P5：Stage V 人工金标准

- A/B 对冻结 claims 在嵌套 L0-L3 上独立判定；
- 当前层级 decisive 后停止；
- decisive judgment 必须引用 raw hashed artifact IDs；
- 第三人仲裁 verdict、minimum level、evidence scope 和 leakage 分歧；
- 至少20%记录进行完整证据包 reverse verification；
- 报告三态一致性、最低证据层级一致性和分歧结构，不能只报一个总体 kappa。

#### P6：模型与基线实验

在同一冻结 claim/evidence 集上比较：

1. diff-only/HalluJudge-style judge；
2. full-context；
3. generic lexical/embedding top-k RAG；
4. EviScope targeted evidence escalation；
5. 必要消融：没有三态、没有定向检索、不同预算、不同停止规则。

同一模型内做配对比较，固定 temperature、prompt、token budget 和 release rule。至少记录：

- 三态 macro/micro 指标与每类混淆矩阵；
- 对 gold `SUPPORTED` 的错误拒绝；
- 对 `CONTRADICTED` 和终局 `INSUFFICIENT` 的错误接受；
- risk–coverage；
- 达到 decisive verdict 的证据层级；
- token、检索 action、chunks、延迟和失败率；
- repository/PR clustered bootstrap 置信区间；
- 重复运行子集的稳定性。

不能仅凭 Qwen3-Coder 单模型结果宣称方法普遍有效。其他模型条件和预算尚需冻结。

#### P7：继续/停止判据

以下任一情况应触发停止、缩小主张或重新设计，而不是包装成成功：

- beyond-diff 的 material claims 太少；
- minimum evidence level 无法可靠标注；
- diff-only 并未产生实质错误拒绝；
- targeted escalation 不优于强 RAG/full-context 基线；
- 提升仅来自更强模型或更多 token；
- 错误接受明显增加；
- 结果只在单个 PR、仓库或 reviewer 上成立；
- review-time leakage 无法控制；
- 无法获得第三名仲裁者。

### 七、你每次工作的操作规范

每次开始时：

1. `cd /data/disk1/Lhuan/EviScope` 并确认真实路径；
2. 阅读本提示词、README、v0.3 guide、experiment defaults 和 gate status；
3. 检查工作树/文件状态，不覆盖已有私有 artifact；
4. 先运行相关验证与测试；
5. 明确本轮属于工程、数据、人工 gold、模型实验还是论文写作；
6. 先复述会影响结论的假设，再执行修改。

执行过程中：

- 优先把重复命令变成带测试的脚本；
- 保留 raw input/output，不原地修改；
- 派生 artifact 写入新版本目录；
- 所有冻结 artifact 输出 SHA-256；
- 网络失败与科学失败分开记录；
- 不执行 `git reset --hard`、递归删除或清理 Docker；
- 不停止 `eviscope-qwen3-coder` 容器，除非我明确授权；
- 不把 token、密钥、用户名、hostname、IP 或私有路径写进公开 artifact；
- partial clone 缺 blob 时逐对象补齐，不能接受空 diff；
- 发现现有文件与本文哈希冲突时立即停止并报告。

每轮结束时必须报告：

1. 实际修改了哪些文件；
2. 运行了哪些验证以及精确结果；
3. 新 artifact 的 SHA-256；
4. 哪些结论已建立，哪些仍只是推测；
5. Gate 是否变化及其证据；
6. 下一项最高优先级任务；
7. 是否存在需要我本人、同学、仲裁者或管理员作出的决定。

### 八、你现在应做的第一项工作

先不要运行剩余32条模型 Stage-S 预测，也不要开始正式48条人工标注。按以下顺序行动：

1. 只读核验本文列出的冻结文件、hash、快照数量和 audit 数量；
2. 运行当前 validator 与全部 unit tests，报告真实基线；
3. 检查哪些一次性生成步骤尚未工程化；
4. 提出并实现最小的可测试 Stage-S 人工标注工具；
5. 用 synthetic 与 Maven 非 Pilot 样本做工具测试；
6. 输出清晰的 annotator A/B 操作说明；
7. 保持正式 Pilot 封存，直到第三名 adjudicator 和 Gate 条件确认。

如果你发现本文与服务器真实状态冲突，以服务器原始文件和可验证哈希为事实来源，但必须明确报告冲突，不能静默选择一个版本。
