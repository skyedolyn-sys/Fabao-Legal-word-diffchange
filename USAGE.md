# Kimi法宝 — 使用指南

跨 CLI 工具复用的合同修订审阅助手。支持 Claude Code（通过 skill 机制）和 Kimi CLI（通过命令行直接调用）。

---

## 目录

- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [Kimi CLI 使用方式](#kimi-cli-使用方式)
- [Claude Code 使用方式](#claude-code-使用方式)
- [输出格式说明](#输出格式说明)
- [自定义规则](#自定义规则)
- [文件结构](#文件结构)

---

## 环境要求

- Python 3.9+
- 仅使用标准库（zipfile, xml.etree, json, re, pathlib）
- 无需安装任何第三方包

---

## 快速开始

```bash
# 方式一：通过 wrapper 脚本（推荐）
~/.claude/skills/kimi-fabao/kimi-fabao /path/to/contract.docx

# 方式二：直接调用 Python 脚本
cd ~/.claude/skills/kimi-fabao/scripts
python3 analyze_revisions.py /path/to/contract.docx

# 保存到文件
python3 analyze_revisions.py /path/to/contract.docx /path/to/output.json

# 使用 NDA 专用 Playbook
python3 analyze_revisions.py /path/to/nda.docx /path/to/output.json --playbook nda

# 模板初筛模式（clean 文档，无修订标记）
python3 analyze_revisions.py /path/to/template.docx /path/to/output.json --mode template
```

---

## Kimi CLI 使用方式

Kimi CLI 没有内置的 skill 机制，但可以直接调用分析脚本，然后将 JSON 输出交给 Kimi 做最终复核。

### 方式一：命令行管道（推荐）

**Step 1 — 安装 wrapper（可选但推荐）：**

```bash
# 创建 symlink 到 PATH 中的目录
mkdir -p ~/.local/bin
ln -s ~/.claude/skills/kimi-fabao/kimi-fabao ~/.local/bin/kimi-fabao

# 确保 ~/.local/bin 在 PATH 中（如不在，加入 ~/.bashrc 或 ~/.zshrc）
export PATH="$HOME/.local/bin:$PATH"
```

**Step 2 — 分析合同：**

```bash
# 使用 wrapper（已安装 symlink）
kimi-fabao contract.docx

# 或使用完整路径
~/.claude/skills/kimi-fabao/kimi-fabao contract.docx

# NDA 专用 Playbook
kimi-fabao nda.docx result.json --playbook nda

# 模板初筛模式（clean 文档）
kimi-fabao template.docx result.json --mode template
```

**Step 3 — 在 Kimi 中提示：**

```
这是一份合同的修订分析结果（JSON格式），请基于以下规则做最终复核：
1. 检查脚本条款类型分类是否正确
2. 评估脚本的风险定级是否合理
3. 对标记为 unknown 的修订给出人工定级
4. 分析脚本报出的关联修订集群是否存在风险叠加
5. 生成最终的乙方视角审阅报告

可先查看 summary_by_risk 快速了解高风险修订分布，再深入 analyzed_revisions 逐条复核。

[粘贴 JSON 输出]
```

### 方式二：分步交互

**Step 1 — 提取分析：**

```bash
kimi-fabao contract.docx result.json
```

**Step 2 — 在 Kimi CLI 中上传 result.json：**

```bash
kimi chat --file result.json
```

**Step 3 — Kimi prompt：**

```
请基于附件中的合同修订分析结果，从乙方（服务提供方）视角逐条复核并输出审阅报告。
要求：
- 对每条修订给出风险等级（🔴强烈反对/🟠需协商/🟢可接受）
- 对🟠和🔴的修订给出具体修改建议
- 标注条款定位路径（如"第3条 服务范围"）
- 按文档出现顺序排列
- 最后给出汇总表格和整体评估
```

### 方式三：Python 导入（高级）

```python
import sys
sys.path.insert(0, "~/.claude/skills/kimi-fabao/scripts")

from analyze_revisions import analyze_revisions

# 通用规则（默认，修订审阅）
result = analyze_revisions("contract.docx")

# NDA 专用 Playbook
result = analyze_revisions("nda.docx", playbook="nda")

# 模板初筛模式（clean 文档）
result = analyze_revisions("template.docx", mode="template")

# 组合：NDA Playbook + 模板模式
result = analyze_revisions("nda_template.docx", playbook="nda", mode="template")

# result 结构：
# {
#   "document": "contract.docx",
#   "playbook": "nda",              # 使用的 Playbook ID（可选）
#   "playbook_info": {              # Playbook 元数据（如使用 Playbook）
#     "id": "nda",
#     "name": "保密协议(NDA)审阅Playbook",
#     "version": "1.0.0"
#   },
#   "summary": { ... },
#   "analyzed_revisions": [ ... ],   # 按文档顺序排列的修订列表
#   "revision_clusters": [ ... ],    # 关联修订集群
#   "summary_by_risk": {             # 按风险等级预聚合（LLM-friendly）
#     "high": [ ... ],
#     "medium": [ ... ],
#     "low": [ ... ],
#     "unknown": [ ... ]
#   },
#   "raw": { ... }                   # 原始提取数据
# }

for rev in result["analyzed_revisions"]:
    print(f"[{rev['location']}] {rev['clause_type']} | {rev['preliminary_risk_level']}")
    print(f"  修订: {rev['text']}")
    if rev["matched_rules"]:
        for r in rev["matched_rules"]:
            print(f"  规则: {r['rule_name']} — {r['rationale']}")
```

---

## Claude Code 使用方式

Claude Code 通过 skill 机制自动加载。使用方式：

```
Kimi法宝，帮我审一下这份合同的修订
```

或上传 .docx 文件后直接说：

```
从乙方视角审阅一下这份合同的修订
```

Claude 会自动：
1. 调用 `scripts/analyze_revisions.py` 执行分析
2. 基于规则引擎输出进行 LLM 复核
3. 生成结构化审阅报告

---

## 输出格式说明

### summary（摘要）

```json
{
  "total_paragraphs": 45,
  "total_revisions": 12,
  "insertions": 8,
  "deletions": 4,
  "total_comments": 3,
  "total_clauses": 6,
  "high_risk_revisions": 3,
  "medium_risk_revisions": 4,
  "low_risk_revisions": 2,
  "unclassified_revisions": 3,
  "revision_clusters": 2
}
```

### analyzed_revisions（逐条分析）

```json
[
  {
    "id": "1",
    "type": "insertion",
    "text": "包括但不限于甲方后续提出的所有相关需求",
    "author": "甲方法务",
    "location": "第3条 服务范围",
    "clause_type": "服务定义",
    "preliminary_risk_level": "medium",
    "matched_rules": [
      {
        "rule_id": "rule_service_001",
        "rule_name": "开放式服务范围",
        "risk_level": "medium",
        "rationale": "开放式表述导致服务范围不可量化"
      }
    ],
    "context": {
      "before": "乙方应向甲方提供",
      "after": "的技术服务。",
      "full_sentence": "乙方应向甲方提供包括但不限于甲方后续提出的所有相关需求的技术服务。"
    }
  }
]
```

字段说明：

| 字段 | 说明 |
|------|------|
| `id` | 修订在文档中的唯一标识 |
| `type` | `insertion` 或 `deletion` |
| `text` | 修订的文本内容 |
| `author` | 修订作者 |
| `location` | 条款定位路径（如"第3条 服务范围 > 3.2 服务内容"） |
| `clause_type` | 条款类型（服务定义/费用与支付/知识产权等） |
| `preliminary_risk_level` | 脚本初步定级：`high` / `medium` / `low` / `unknown` |
| `matched_rules` | 匹配的风险规则列表 |
| `context` | 上下文：before（前文）、after（后文）、full_sentence（整句） |

### summary_by_risk（按风险等级预聚合）

LLM-friendly 视图，将 `analyzed_revisions` 按 `preliminary_risk_level` 预分组：

```json
{
  "high": [
    { /* revision with preliminary_risk_level = "high" */ }
  ],
  "medium": [
    { /* revision with preliminary_risk_level = "medium" */ }
  ],
  "low": [
    { /* revision with preliminary_risk_level = "low" */ }
  ],
  "unknown": [
    { /* revision with preliminary_risk_level = "unknown" */ }
  ]
}
```

**用途**：
- LLM 可先扫 `summary_by_risk.high` 快速定位核心风险点
- 再按需要深入 `summary_by_risk.medium` / `unknown`
- 每个 revision 对象与 `analyzed_revisions` 中的条目完全一致（纯冗余，无信息损失）

### revision_clusters（关联集群）

```json
[
  {
    "group_id": "liability_expansion",
    "theme": "责任范围扩大",
    "revision_ids": ["5", "6", "7"],
    "count": 3
  }
]
```

表示修订 5、6、7 可能在"责任范围扩大"主题上存在关联，需重点复核是否存在风险叠加。

---

## 自定义规则

### 场景一：新增行业-specific 风险规则（通用规则）

比如你的公司经常遇到"要求源代码交付"的修订，可以新增一条规则：

**编辑 `rules/risk_rules.json`：**

```json
{
  "id": "rule_ip_003",
  "name": "要求交付源代码",
  "applies_to_clause_types": ["知识产权", "服务定义"],
  "applies_to_revision_types": ["insertion"],
  "patterns": {
    "insertion": ["源代码", "source code", "源码", "全部代码"]
  },
  "risk_level": "high",
  "rationale": "要求交付源代码可能导致核心技术泄露"
}
```

修改后立即生效，无需重启任何服务。

### 场景二：新增合同类型 Playbook

如果你经常审阅某类特定合同（如 SaaS 协议、技术服务合同），可以创建专用 Playbook：

**Step 1 — 创建目录和规则文件：**

```bash
mkdir -p rules/playbooks/saas
```

**Step 2 — 编写 `rules/playbooks/saas/clause_patterns.json`：**

```json
{
  "version": "1.0.0",
  "playbook_id": "saas",
  "playbook_name": "SaaS协议审阅Playbook",
  "priority_order": ["服务级别", "数据安全", "费用", ...],
  "patterns": {
    "服务级别": {
      "keywords": ["SLA", "可用性", "uptime", "服务级别", ...],
      "priority": 1
    }
  }
}
```

**Step 3 — 编写 `rules/playbooks/saas/risk_rules.json`：**

格式与通用 `risk_rules.json` 完全一致。

**Step 4 — 使用 Playbook：**

```bash
python3 analyze_revisions.py saas_contract.docx --playbook saas
```

### 场景三：调整条款类型关键词

比如你的合同使用"商务条款"而非"费用与支付"作为标题：

**编辑 `rules/clause_patterns.json`：**

```json
"费用与支付": {
  "keywords": [
    "费用", "价格", "付款", "支付", "发票", "账期",
    "预付款", "定金", "保证金", "商务条款"
  ],
  "priority": 5
}
```

---

## 文件结构

```
kimi-fabao/
├── SKILL.md                      # Claude Code skill 定义
├── USAGE.md                      # 本文件：跨 CLI 使用指南
├── kimi-fabao                    # 入口 wrapper 脚本
├── rules/                        # 规则库（可自定义扩展）
│   ├── clause_patterns.json      # 通用：条款类型分类规则
│   ├── risk_rules.json           # 通用：风险标记规则
│   └── playbooks/                # 细分合同类型 Playbook
│       └── nda/                  # NDA 专用规则
│           ├── clause_patterns.json
│           └── risk_rules.json
├── scripts/                      # 分析脚本
│   ├── extract_revisions.py      # 底层：DOCX 修订提取
│   └── analyze_revisions.py      # 上层：规则引擎 + 初步分析
└── evals/
    └── evals.json                # 测试用例
```

---

## 常见问题

**Q: Kimi CLI 如何知道调用哪个脚本？**

A: 使用 skill 根目录下的 `kimi-fabao` wrapper 脚本：

```bash
# 方式一：直接调用（无需安装）
~/.claude/skills/kimi-fabao/kimi-fabao contract.docx

# 方式二：创建 symlink 到 PATH（推荐）
ln -s ~/.claude/skills/kimi-fabao/kimi-fabao ~/.local/bin/kimi-fabao
kimi-fabao contract.docx

# 方式三：设置环境变量（脚本找不到 rules/ 时用）
export KIMI_FABAO_RULES="$HOME/.claude/skills/kimi-fabao/rules"
```

**Q: 脚本输出太大，Kimi 上下文装不下怎么办？**

A: 可以只提取高风险修订：

```python
import json
with open("result.json") as f:
    data = json.load(f)

# 只保留 high + medium + unknown（需要人工复核的）
need_review = [r for r in data["analyzed_revisions"]
               if r["preliminary_risk_level"] in ("high", "medium", "unknown")]

with open("filtered.json", "w") as f:
    json.dump({"revisions": need_review}, f, ensure_ascii=False, indent=2)
```

**Q: 规则误报怎么办？**

A: 规则匹配是启发式的，存在误报正常。LLM 复核步骤的职责之一就是过滤掉不合理的规则匹配。如果某条规则持续误报，可以：
1. 在 `risk_rules.json` 中收紧关键词（更具体）
2. 添加 `applies_to_clause_types` 限制缩小适用范围
3. 添加负面关键词过滤（需要代码支持，未来版本）
