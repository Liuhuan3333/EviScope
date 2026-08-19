# Research Canon

## 已核实事实

1. HalluJudge 将代码审查幻觉操作化为评论主张与给定 code diff 的上下文失配，报告最佳 F1 约 0.85；它是直接基线，而不是需要被否定的工作。来源：https://arxiv.org/abs/2601.19072
2. ContextCRBench 表明 PR/Issue 和代码上下文会显著改变代码审查生成与质量判断，同时额外上下文也可能对部分模型产生噪声。来源：https://arxiv.org/html/2511.07017
3. RevMate 已将检索、评论生成和过滤用于真实代码审查环境，因此“RAG + reviewer”本身不足以构成创新。来源：https://arxiv.org/html/2411.07091
4. LAURA 已使用历史代码审查示例和上下文增强生成评论，因此本项目不能以检索增强生成作为主贡献。来源：https://arxiv.org/html/2512.01356
5. CRScore 已提出无参考的代码审查评论质量评估，但不标注最小证据充分性。来源：https://aclanthology.org/2025.naacl-long.457/
6. 代码变更到自然语言生成研究报告代码审查评论中存在较高比例的幻觉，传统文本指标单独检测能力有限。来源：https://aclanthology.org/2025.ijcnlp-long.137/
7. FSE 2027 Research Track 全文截止为 2026-10-02 AoE，正文与图表上限 18 页，参考文献另 4 页，实行 heavy double-anonymous review，并鼓励匿名复现包。来源：https://conf.researchr.org/track/fse-2027/fse-2027-papers

## 术语定义

- 原子主张：能够被独立支持、反驳或判为证据不足的最小评论命题。
- 当前证据包：在某个实验条件下允许验证器看到的、已冻结并可追溯的 review-time artifact 集。
- SUPPORTED：当前证据包包含足以支持主张的证据。
- CONTRADICTED：当前证据包包含与主张冲突的证据。
- INSUFFICIENT：在预定义证据包和预算内既不能支持也不能反驳；它不是对现实真假的断言。
- 最低充分证据层级：在预定义的嵌套证据包 L0-L3 中，第一个允许专家稳定裁决主张的层级；不是对所有可能证据的数学最小性证明。
- 错误拒绝：金标签为 SUPPORTED 的主张被系统过滤或判为失配。
- 错误接受：金标签为 CONTRADICTED 或终局 INSUFFICIENT 的主张被系统作为可靠评论发布。

## 尚未建立的关键事实

1. 真实代码审查评论中，需要 L1-L3 证据的有效主张比例未知。
2. Diff-only judge 是否在这些主张上产生实质性错误拒绝，尚待实验证明。
3. Targeted evidence escalation 是否优于 full-context 和 generic top-k RAG，尚待实验证明。
4. 最低证据层级能否获得足够高的标注一致性，尚待试点证明。
5. HalluJudge、ContextCRBench 等公开数据和代码的实际可复用范围需要逐项核验。

## 禁止主张

- “现有幻觉检测是错误的。”
- “更多上下文必然提升准确率。”
- “EviScope 证明评论真实正确。”
- “这是首个仓库级代码审查系统。”
- “开发者采纳等于评论正确。”
- 在未完成系统检索前使用“首个”“首次”“全面解决”等措辞。

