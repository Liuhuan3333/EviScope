# EviScope 模型选择建议 v0.1

## 冻结前建议

模型目前只是候选配置，不能将 `status` 改为 `confirmed`。确认前必须在服务器记录：本地 checkpoint 路径、不可变 revision/hash、vLLM 版本、dtype、tensor parallel size、最大上下文、显存占用和一次固定 smoke 输出。

## 推荐层级

### 主模型：Qwen/Qwen3-Coder-30B-A3B-Instruct

用于所有主方法比较和 primary endpoint。理由是任务对象是代码审查评论，不是一般聊天；模型官方仓库将其定位为代码与 agentic coding 模型，并列出 256K 上下文和 vLLM/SGLang 部署支持。两张 A100 80GB 更适合先以 BF16、tensor parallel size 2、32K 最大输入上下文启动，而不是一开始启用 256K 长上下文。长上下文不是本研究变量，过大的窗口还会增加 KV cache 和运行时间。

建议初始参数：

```text
dtype: bfloat16
tensor_parallel_size: 2
max_model_len: 32768
temperature: 0
max_tokens: 1024
gpu_memory_utilization: 0.85-0.90
```

不启用 tool calling 或隐藏思维链输出；检索在模型外部完成，模型只接收结构化证据包并返回 schema 约束的 verdict。

### 第二模型：Qwen/Qwen3-32B

用于跨模型复核和 robustness 分析。它是 dense 32B 通用指令模型，原生上下文为 32K，模型卡提供 YaRN 扩展到 131K 的选项。主实验仍固定 32K，避免把“更长上下文”混入模型差异。

第二模型的作用不是寻找最高分，而是判断 EviScope 的效果是否只来自 Qwen3-Coder 的代码偏好。

### 冒烟模型：Qwen/Qwen3-8B

仅用于：JSON 输出调试、prompt/schema smoke、快速回归和检索管线开发。它不进入论文主结论，也不用于替代 30B 主模型。

## 为什么暂不选其他模型

- 不把闭源 API 模型作为主模型：服务器本地实验的可复现性、成本和网络依赖更差；后续可作为外部 sanity check。
- 不把 Qwen2.5-Coder-32B 作为主模型：它可以作为备用或历史基线，但当前主线需要先固定一个更新的、官方支持 vLLM 的模型，避免在七周窗口内扩大组合。
- 不使用 235B 级模型：两张 A100 80GB 不适合本项目的重复实验成本和上下文预算。
- 不用 7B/8B 模型承担主结论：它适合开发，不足以代表可靠 judge 的上限。

## 实验控制

同一 claim 的所有方法必须在同一模型内配对比较。每个模型单独记录 prompt hash、checkpoint revision、serving engine、dtype、GPU IDs、temperature、max tokens、输入/输出 token 和延迟。不能比较“强模型 + diff-only”和“弱模型 + EviScope”后归因于方法。

## 来源

- Qwen3-Coder 官方仓库：https://github.com/QwenLM/Qwen3-Coder
- Qwen3 官方仓库与 vLLM 部署说明：https://github.com/QwenLM/Qwen3
- Qwen3-32B 模型卡：https://huggingface.co/Qwen/Qwen3-32B
- 备用代码模型 Qwen2.5-Coder-32B：https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct

