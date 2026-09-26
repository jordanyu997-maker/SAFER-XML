# V2.3 40-App 正式实验运行说明

## 已冻结范围

- 40 个具有 XML-safe 问题的真实开源 Android App
- 110 个 XML 修复任务
- 136 条高置信 XML-safe 问题
- 30 条 boundary 问题，仅用于安全拒绝统计，不进入修复率分母
- 3 个模型：DeepSeek V4 Pro、GPT 5.6 SOL、Claude Opus 4.8
- 2 个方法组：`raw_baseline`、`full_enhanced`
- 每个模型 220 个条件运行，总计 660 个条件运行

`raw_baseline` 只使用通用修复指令并调用模型一次。

`full_enhanced` 使用检测器证据、冻结的 RAG Top-2、XML-safe 过滤、反馈修复、事务执行和安全校验，最多 3 个语义轮次，每轮最多 3 次格式纠正。

## 运行前校验

```bash
python3 tools/run_android_xml_v2_40app_formal_study.py verify
```

输出必须为 `status: passed` 且 `model_calls: 0`。

## 按模型依次运行

DeepSeek：

```bash
read -s "DEEPSEEK_KEY?请粘贴 DeepSeek API Key 后按回车: "; echo
DEEPSEEK_API_KEY="$DEEPSEEK_KEY" python3 tools/run_android_xml_v2_40app_formal_study.py run \
  --models deepseek_v4_pro \
  --resume
unset DEEPSEEK_KEY
```

GPT：

```bash
read -s "GPT_KEY?请粘贴 GPT API Key 后按回车: "; echo
ANDROID_XML_GPT_API_KEY="$GPT_KEY" python3 tools/run_android_xml_v2_40app_formal_study.py run \
  --models gpt_5_6_sol \
  --resume
unset GPT_KEY
```

Claude：

```bash
read -s "CLAUDE_KEY?请粘贴 Claude API Key 后按回车: "; echo
ANDROID_XML_CLAUDE_API_KEY="$CLAUDE_KEY" python3 tools/run_android_xml_v2_40app_formal_study.py run \
  --models claude_opus_4_8 \
  --resume
unset CLAUDE_KEY
```

`--resume` 只用于继续缺失或基础设施失败的记录；不要根据模型效果选择性重跑成功记录。

## 结果位置

- 逐任务记录：`runs/<model>/<task>/<group>/reports/`
- 汇总表：`formal_results.csv`
- 运行清单：`run_manifest.json`

正式运行期间不要修改协议、数据集、Prompt、知识库、检测器、检索器、安全机制或任务清单。
