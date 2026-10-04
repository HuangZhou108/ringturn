# Melody Regression Benchmark

该工具用于比较 Basic Pitch、librosa 和生产环境自动候选策略。它不会调用 LLM，
也不会修改任务数据库、Profile 或 LangGraph checkpoint。

## Manifest

复制 `manifest.example.json`，为每首测试音频增加一个 case。相对路径以 manifest
所在目录为基准。测试音频、参考旋律和缓存预测默认放在
`backend/evaluation/datasets/`，该目录已被 Git 忽略，避免提交版权音频。

参考旋律可以是：

- `*.notes.json`：JSON 数组，或 `{ "melody_notes": [...] }`；
- 单旋律 `*.mid` / `*.midi`；多轨 MIDI 必须设置 `reference_instrument`。

没有参考旋律时可以省略 `reference_path`，报告仍会生成结构质量指标，但不会声称
测得了原曲旋律准确率。

参考旋律必须与输入音频使用相同的片段和时间起点。建议填写 `audio_duration`，否则
结构质量覆盖率只能按预测音符自身的时间范围估算。

## 运行真实提取

在 `backend/` 目录安装 requirements 后执行：

```bash
python -m evaluation.melody_benchmark \
  --manifest evaluation/manifest.local.json \
  --output-dir benchmark-results/current
```

Windows PowerShell：

```powershell
python -m evaluation.melody_benchmark `
  --manifest evaluation/manifest.local.json `
  --output-dir benchmark-results/current
```

实际提取会运行 Basic Pitch 和 librosa，并复用生产提取图当前的稳定化、量化、合并
及调性校正参数。候选 MIDI、标准化音符和报告都会写入 `--output-dir`。

## 复用缓存预测

在 manifest 的 `predictions.basic_pitch` 和 `predictions.librosa` 指定音符 JSON：

```bash
python -m evaluation.melody_benchmark \
  --manifest evaluation/manifest.local.json \
  --output-dir benchmark-results/cached \
  --reuse-predictions
```

该模式不运行 Basic Pitch 或 librosa，适合快速比较指标和报告逻辑。
缓存文件应使用真实提取报告生成的 `*.notes.json`（已经过与生产图一致的后处理），
不要直接填入未经稳定化和量化的原始模型事件。

## 回归门禁

```bash
python -m evaluation.melody_benchmark \
  --manifest evaluation/manifest.local.json \
  --output-dir benchmark-results/current \
  --baseline benchmark-results/baseline/report.json \
  --fail-on-regression
```

默认规则：质量分下降超过 2 分、参考 F1 下降超过 0.02，或原本可用的结果变为
不可用，都会标记为回归。

CLI 退出码：

- `0`：评测完成且未触发回归门禁；
- `1`：manifest、参数或依赖错误；
- `2`：`--fail-on-regression` 检测到回归；
- `3`：报告已生成，但至少一个提取器执行失败或缺少缓存预测。
