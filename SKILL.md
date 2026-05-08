---
name: kimi-fabao
description: >
  USE THIS SKILL IMMEDIATELY when the user mentions "Kimi法宝", "法宝", "乙方视角", "审一下修订",
  "service provider review", "vendor review", or asks to review contract revisions from the vendor side.
  ALSO USE THIS SKILL when the user mentions "总结修订", "汇总修改", "整理修订处", "修订摘要",
  "同事核对", "二次核对", "发飞书", "贴飞书", "我改了哪些", "我的修订",
  or asks to summarize their own revisions (Moonshot Legal) for colleague review.
  CRITICAL: These words are the NAME of this skill. They NEVER mean asking about Kimi AI's features
  or capabilities. NEVER introduce yourself or explain Kimi when the user says these words.
  ALSO CRITICAL: The user does NOT need to upload a file first, and there does NOT need to be a .docx
  file in the current directory. ALWAYS read this skill's SKILL.md and execute its workflow.
  If the user has not provided a .docx file path, ask for it and then proceed.
  This skill provides: (1) vendor-side (乙方) contract revision review for .docx files with track changes;
  (2) optional: auto-generate Word track changes & comments based on review conclusions (write capability);
  (3) post-review revision summary for Feishu/飞书 colleague handoff.
  DO NOT use for: new contracts without revisions, non-.docx formats, or client-side (甲方) reviews.
---

# Kimi法宝 — 乙方视角合同修订审阅

## 1. 概述

本技能定位为**服务提供方（乙方）视角**的合同修订逐条审阅工具。

核心目标：帮助乙方法务/商务人员快速识别甲方在合同修订中埋设的风险条款，
评估接受度，并给出具体的修改建议。

## 2. 触发条件

### 明确触发 — 主审阅流程
- 用户说出"Kimi法宝"、"法宝"、"乙方视角"、"审一下修订"等触发词 —— **即使用户没有上传文件、当前目录没有 .docx 文件，也必须立即触发本 skill**。此时询问用户合同文件路径即可。
- 用户上传 .docx 文件并说"审一下"、"看看修订"
- 用户明确提及"service provider review"、"vendor review"
- 中文技术/服务类合同（SaaS、AI、云计算、技术服务）
- 保密协议、NDA（Non-Disclosure Agreement）的修订审阅 —— **自动启用 NDA Playbook**
- 对方发来的模板合同（clean 版本，无修订标记）—— **自动启用 Template 模式**

### 明确触发 — 修订总结流程（§10）
- 用户提到"总结"/"汇总"/"整理" + "修订"/"修改"/"改动"
- 用户提到"同事核对"、"二次核对"、"发飞书"、"贴飞书"
- 用户提到"我改了哪些"、"我的修订"、"Moonshot Legal 的修改"
- 用户在完成 Kimi法宝 主流程审阅后，要求整理输出给同事

### 流程判断逻辑
- 用户意图是**分析对方改了什么** → 走主审阅流程（§3 Step 1-4）
- 用户意图是**总结我方改了什么，给同事看** → 走修订总结流程（§10）

### 明确不触发
- 无修订标记的原始合同（建议用户先开启修订模式）
- 非 .docx 格式
- 甲方视角要求（引导使用 contract-revision-core）

## 3. 工作流（4步 + 可选写入层）

### Step 1: 运行分析引擎

**文件路径处理**：

- 如果用户已提供 .docx 文件路径（上传文件或指定路径），直接使用该路径。
- **如果用户只说触发词（如"kimi法宝"）但未提供文件**：
  1. 先搜索当前目录及子目录中是否存在 .docx 文件（使用 Glob 工具）
  2. 如果找到 1 个 .docx 文件，直接使用该文件并告知用户
  3. 如果找到多个 .docx 文件，列出候选文件让用户选择
  4. 如果未找到 .docx 文件，询问用户合同文件路径
- **不得因为没有文件就拒绝执行或介绍 Kimi 功能。**

**合同类型判断**（在调用引擎前执行）：

LLM 根据以下信息判断合同类型，决定是否使用专用 Playbook：

1. **用户描述**（最高优先级）：用户是否明确说了"NDA"、"保密协议"等
2. **文件名**：如 `NDA_v2.docx`、`保密协议-修订版.docx`
3. **文档标题与首段**：读取文件前 3-5 个段落，看是否出现"保密协议"、"Non-Disclosure"等字样
4. **条款标题分布**：如"保密信息定义"、"除外情形"等 NDA 特有条款密集出现

**判断结果处理**：
- **高置信度识别为 NDA**：直接调用脚本时附加 `--playbook nda`，并告知用户"已启用 NDA 专用审阅规则"
- **高置信度识别为通用技术服务合同**：使用默认通用规则，不附加 `--playbook`
- **不确定或混合合同**：询问用户"这是一份保密协议/NDA 吗？如是，我将启用专用审阅规则获得更精准的分析。"

**审阅模式判断**（引擎自动检测，LLM 无需干预）：

引擎会自动检测文档是否包含修订标记（w:ins/w:del）：
- **含修订标记** → `revision` 模式（默认）：分析修订的增量风险
- **无修订标记** → `template` 模式：全量扫描合同条款风险

如需强制指定模式，可在调用时附加 `--mode template` 或 `--mode revision`。

**调用方式**：

- **Claude Code**：
  ```bash
  # 通用规则（修订审阅，默认）
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx>

  # NDA 专用 Playbook（自动判断后使用）
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx> --playbook nda

  # 模板初筛模式（clean 文档，无修订标记）
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx> --mode template
  ```
- **Kimi CLI**：调用前必须先确认脚本存在，再执行：
  ```bash
  ls ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx>
  # 或使用 NDA Playbook
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx> --playbook nda
  # 或模板初筛模式
  python3 ~/.claude/skills/kimi-fabao/scripts/analyze_revisions.py <input.docx> --mode template
  ```

**严格约束**：
- 如脚本文件不存在或调用失败（FileNotFoundError / ModuleNotFoundError），**不得自行编写 Python 代码解析 DOCX XML**。
- 必须停止并提示用户："分析引擎未找到，请确认 kimi-fabao 已安装于 ~/.claude/skills/kimi-fabao/。"

**引擎内部完成的工作**：
0. 合同类型识别（LLM 层）：根据文件名、用户描述、文档标题自动判断合同类型，选择对应 Playbook
1. 解析 DOCX 结构（段落、标题样式）
2. 自动检测审阅模式：
   - **Revision 模式**：提取 `w:ins` / `w:del` 修订标记与批注，分析增量风险
   - **Template 模式**：提取所有条款段落作为 `existing` 记录，全量扫描风险条款
3. 按 heading 样式进行基础条款分组，提取每条修订的上下文片段（`before` / `after` / `full_sentence`）
4. 基于 `rules/clause_patterns.json`（或 Playbook 专用规则）自动分类条款类型
5. 基于 `rules/risk_rules.json`（或 Playbook 专用规则）做初步风险标记（🔴/🟠/🟢）
6. 关联修订聚类（识别跨条款风险叠加）
7. 支持 `--playbook` 参数切换合同类型专用规则（如 `nda`）
8. 支持 `--mode` 参数切换审阅模式（`revision` / `template`）

**输出结构化 JSON**，包含：
- `analyzed_revisions`: 带初步定位、类型、初步风险等级的修订列表（按文档顺序排列）
- `revision_clusters`: 关联修订组（如"责任范围扩大"集群）
- `summary_by_risk`: 按风险等级预聚合的视图（`high` / `medium` / `low` / `unknown`）
- `summary`: 修订统计与风险分布
- `raw.clauses`: 条款树（主文正文部分）
- `raw.appendices`: 附件列表（独立于主文 clause tree）
- `paragraphs`: 全部段落原始数据（含 text, style, is_heading, heading_level, fmt）
- `summary.heading_source`: 结构识别来源（`styles` / `heuristic` / `bold_fallback` / `none`）
- `summary.doc_patterns`: 文档编号模式档案（has_zhang / has_tiao / has_cn_ordinal / has_decimal 等）

### Step 1.5: 结构识别（引擎启发式 + LLM 精化）

引擎现在**自动检测文档编号模式**并完成粗分：

**引擎启发式（两遍扫描）**：
- **第一遍**：扫描全文段落，统计哪些编号 pattern 存在（`第X章`、`第X条`、`一、`、`X.X`、`（一）`）
- **第二遍**：根据模式档案，赋予每段启发式 heading_level：
  - `第X章` → 始终 L1
  - `第X条` → L1（无章）/ L2（有章）
  - `一、` → L1（无条无章）/ L2（有条）/ L3（有章+条）
  - `（一）` → L2（无条）/ L3（有条）
  - `X.X` / `X.X.X` → L2/L3（自动按 dot 数递增）
  - `附件X` / `Appendix X` → L1，独立分离到 `appendices`
  - **Bold+短文本 fallback**：仅当全文无任何编号 pattern 时启用；排除居中文本、含冒号文本

**LLM 精化职责**（在引擎粗分基础上）：
1. 检查 `summary.heading_source`，了解引擎使用了哪种识别策略
2. 对引擎标记为 `heading_source: "heuristic"` 的条款做校验
3. 识别引擎遗漏的子节标题（无格式短文本如“服务类别”“服务期限”）
4. 确定每处修订所属的精确条款位置，在报告中使用原文编号形式
5. 校准引擎给出的 `location` 路径

### Step 2: LLM 复核与精化

**核心原则**：LLM 基于脚本输出做**复核与精化**，而非从零手工分析。

**复核要点**：

**复核要点**：
1. **条款类型校验**：脚本分类是否正确？标题歧义时需要人工修正
2. **风险等级精化**：脚本的初步标记是否合理？需结合上下文判断
3. **关联分析**：脚本报出的关联集群是否真实存在风险叠加？
4. **规则未覆盖情况**：脚本标记为 unknown 的修订，需人工评估

**分析维度**：

**风险等级**：
- 🔴 **强烈反对** — 对乙方有重大不利影响，必须要求修改
- 🟠 **需协商** — 对乙方有一定影响，建议争取更有利条件
- 🟢 **可接受** — 对乙方影响较小或有利，可直接接受

1. **商业影响**：是否增加成本、延长交付、扩大责任范围
2. **法律风险**：是否导致违约责任扩大、赔偿上限提高、知识产权流失
3. **可操作性**：乙方实际能否履行修订后的义务

**建议动作**：
- **接受**：同意修订，无需修改
- **协商**：提出替代方案或修改建议
- **反对**：要求删除或恢复原条款

### Step 3: 关联修订复核
审查脚本输出的 `revision_clusters`，判断跨条款风险叠加：
- 是否存在"删除责任上限"+"扩大赔偿范围"的责任叠加？
- 是否存在"服务范围扩大"+"免费义务增加"的成本叠加？
- 聚类结果是否合理？是否存在误判？

### Step 4: 生成审阅报告
基于引擎输出 + LLM 复核，生成结构化审阅报告（见第4节输出格式规范）。

### Step 5-7（可选）: 自动写入修订

当用户明确要求"执行写入"、"生成修订版"或"基于审阅结果修改合同"时，触发后置写入层：

**Step 5: 生成 write_plan 模板**
```bash
python3 ~/.claude/skills/kimi-fabao/scripts/write/write_plan_generator.py \
  engine_output.json write_plan_template.json [--playbook nda]
```
- 输入：`engine_output.json`（Step 1 输出）
- 输出：`write_plan_template.json`
- 逻辑：基于 `preliminary_risk_level`（high/medium）和 `matched_rules` 从 `rules/write_actions.json` 映射动作模板

**Step 6: LLM 精化 write_plan**
- LLM 读取 `write_plan_template.json`，根据具体上下文填充占位符（如 `{extracted_risky_text}`、`{suggested_cap}%`）
- LLM 复核 disposition：mandatory 项默认执行，negotiable 项需确认
- 输出最终的 `write_plan.json`

**Step 7: 执行写入**
```bash
python3 ~/.claude/skills/kimi-fabao/scripts/write/execute_revisions.py \
  write_plan.json input.docx output.docx --author "Moonshot Legal" --post-validate
```
- 输入：`write_plan.json` + 原始 `docx`
- 输出：已修订 `docx`（自动备份原文件）
- 支持 action 类型：`replace_in_text`、`delete_text`、`add_comment`、`insert_after_paragraph`、`append_to_paragraph`
- 执行后自动调用 `analyze_revisions.py` 做后置验证

**用户交互**：
- 默认行为（用户只说"审一下"）：只执行 Step 1-4，输出审阅报告
- 触发写入（用户说"并执行写入"）：Step 1-4 + Step 5-7，输出报告 + 已修订 docx
- 分步触发：先审阅生成报告，用户后续说"基于刚才结果执行写入"，从上下文获取 engine_output 继续 Step 5-7

**报告生成时必须使用的脚本输出字段**：
- `analyzed_revisions[].location` → 条款定位路径
- `analyzed_revisions[].clause_type` → 条款类型（LLM 复核后可修正）
- `analyzed_revisions[].preliminary_risk_level` → 脚本初步定级（LLM 复核后可调整）
- `analyzed_revisions[].matched_rules` → 匹配的规则名称和理由
- `analyzed_revisions[].context.before/after/full_sentence` → 修订上下文
- `revision_clusters` → 关联修订组

**报告应明确标注**：
- 哪些判断来自脚本规则引擎（可复现）
- 哪些判断来自 LLM 人工复核（需特别说明推理）
- 脚本标记为 unknown 的修订，必须给出人工定级理由

**禁止行为**：
- 不得忽略脚本已提供的定位信息，重新手动推断条款位置
- 不得忽略脚本的初步风险标记，完全从零重新定级
- 不得遗漏脚本已识别出的关联修订集群

## 4. 输出格式规范

```markdown
# 合同修订审阅报告

## 基本信息
- **合同名称**：{从文件名或首段提取}
- **审阅日期**：{当前日期}
- **审阅视角**：乙方（服务提供方）
- **修订总数**：{N} 处（插入 {M} 处，删除 {K} 处）
- **批注数**：{P} 条

## 修订概览表

| 序号 | 条款 | 类型 | 风险等级 | 建议动作 | 审阅优先级 |
|------|------|------|----------|----------|------------|
| 1 | 第3条 服务范围 | 服务定义 | 🟠需协商 | 协商 | P1 |
| ... | ... | ... | ... | ... | ... |

## 逐条审阅详情

### 第X条 {条款标题} [{条款类型}] — 位置：{条款定位路径}

**修订内容**：
- 删除："{原文}"
- 插入："{修订后文本}"

**风险分析**：
- 风险等级：{🔴/🟠/🟢}
- 商业影响：{分析}
- 法律风险：{分析}
- 可操作性：{分析}

**建议动作**：{接受/协商/反对}

**修改建议**：
{具体的修改建议，包括替代措辞或删除理由}

---

## 汇总与建议

### 优先级排序
1. **P1（必须修改）**：{条款列表} — 涉及核心商业利益
2. **P2（建议修改）**：{条款列表} — 可争取更有利条件
3. **P3（可接受）**：{条款列表} — 影响较小

### 整体评估
- 修订总体倾向：{对乙方有利/中性/不利}
- 关键风险点：{总结}
- 修改建议汇总：{总体修改方向}
```

## 5. 风险等级定义

### 🔴 强烈反对
**标准**：
- 责任上限被取消或大幅降低
- 引入无过错赔偿责任（如"无论是否违约"）
- 知识产权从乙方完全转让给甲方
- 付款条件恶化到影响现金流安全
- 增加无法履行的义务或无限期承诺

**处理**：必须在签约前要求修改，不可单独接受。

### 🟠 需协商
**标准**：
- 赔偿范围扩大但仍有上限
- 服务范围增加但可量化
- 期限延长在可接受边缘
- 数据安全义务增加但行业标准可接受
- 终止条件对乙方略不利

**处理**：提出替代方案，争取更有利条件。

### 🟢 可接受
**标准**：
- 纯措辞优化，无实质影响
- 对乙方有利或中性的修订
- 行业标准条款的常规调整
- 格式、标点、非关键定义的调整

**处理**：直接接受，无需协商。

## 6. 分析维度模板

### 服务定义条款
- 服务范围是否被扩大？是否包含隐含义务？
- 验收标准是否变得主观或不可达成？
- 是否引入"满足甲方所有需求"等开放式表述？
- SOW 变更流程是否对乙方不利？

### 费用与支付条款
- 付款账期是否延长？
- 是否增加预付款/保证金要求？
- 发票要求是否变得不合理？
- 是否引入单方调价权？

### 期限与终止条款
- 自动续约是否对乙方不利？
- 甲方单方终止权是否扩大？
- 终止后过渡期义务是否合理？
- 是否有排他性或竞业限制？

### 知识产权条款
- 背景 IP 归属是否清晰？
- 前景 IP 是否从许可变为转让？
- 是否引入"职务作品"等扩大甲方权利的定义？
- 开源软件合规义务是否合理？

### 违约责任条款
- 违约金比例是否过高？
- 是否取消责任上限或例外？
- 是否引入间接损失赔偿？
- 是否增加单方解约权？

### 数据安全条款
- 数据安全义务是否超出行业标准？
- 数据泄露通知时限是否过短？
- 是否要求承担第三方索赔？
- 数据归属和删除义务是否明确？

### 不可抗力条款
- 不可抗力定义是否过窄？
- 免责范围是否被限制？
- 通知义务是否过重？

### 其他条款
- 争议解决地点是否对乙方不利？
- 法律适用是否可接受？
- 完整协议条款是否排除了先前的有利承诺？

## 7. Playbook 架构（细分合同类型规则）

除通用规则外，支持按合同类型加载专用 Playbook 规则，实现更精准的条款分类和风险识别。

### 已有 Playbook

| Playbook ID | 适用场景 | 专用规则 |
|-------------|----------|----------|
| `nda` | 保密协议 / NDA | 10 类 NDA 条款 + 15 条 NDA 专用风险规则 |

### 使用方式

```bash
# 通用规则（默认）
python3 analyze_revisions.py contract.docx

# NDA 专用 Playbook
python3 analyze_revisions.py nda.docx --playbook nda
```

### 工作原理

- Playbook 规则存放在 `rules/playbooks/<playbook_id>/` 目录下
- 引擎优先加载 Playbook 目录下的 `clause_patterns.json` 和 `risk_rules.json`
- 若 Playbook 目录下缺少某个规则文件，自动回退到基础 `rules/` 目录
- 输出 JSON 中新增 `playbook_info` 字段标识当前使用的 Playbook

### 新增 Playbook 步骤

1. 创建目录：`rules/playbooks/<new_id>/`
2. 编写 `clause_patterns.json`（条款类型定义）
3. 编写 `risk_rules.json`（风险规则）
4. 运行：`python3 analyze_revisions.py contract.docx --playbook <new_id>`

Playbook 规则文件格式与基础规则完全一致，仅需在 `clause_patterns.json` 顶部添加：
```json
{
  "playbook_id": "your_id",
  "playbook_name": "Playbook 显示名称"
}
```

## 8. 规则库扩展（基础规则）

`rules/` 目录下的 JSON 文件支持自定义扩展：

### clause_patterns.json
- 增加新的条款类型：在 `patterns` 中添加新的键值对
- 调整匹配优先级：修改 `priority_order` 数组顺序
- 增加关键词：在对应类型的 `keywords` 数组中添加

### risk_rules.json
- 增加新规则：在 `rules` 数组中添加新规则对象
- 规则字段说明：
  - `id`: 唯一标识符
  - `name`: 规则名称（人类可读）
  - `applies_to_clause_types`: 适用的条款类型列表（空表示全部）
  - `applies_to_revision_types`: 适用的修订类型（`["insertion"]`, `["deletion"]`, `["insertion", "deletion"]`）
  - `patterns`: 按修订类型分组的匹配模式
    - `insertion`: 插入文本匹配的关键词列表
    - `deletion`: 删除文本匹配的关键词列表
  - `risk_level`: `high` / `medium` / `low`
  - `rationale`: 风险说明（用于报告输出）

### 规则生效方式
修改 JSON 文件后无需重启，下次运行 `analyze_revisions.py` 时自动加载最新规则。

## 9. 边界与限制

### 技术限制
- 仅支持 .docx 格式的原生修订标记（w:ins / w:del）
- 不支持 PDF 批注、图片标注、纯文本 diff
- 批注提取依赖 comments.xml，若文档结构损坏可能无法提取
- 脚本风险标记基于关键词启发式匹配，存在误判可能，需 LLM 复核

### 法律限制
- 本技能提供的分析仅供参考，不构成法律意见
- 重大合同决策应咨询执业律师
- 不同法域（中国大陆/香港/美国/欧盟）的法律分析存在差异

### 功能边界
- **分析模式（默认）**：不生成修订后的合同文本，仅提供分析建议
- **写入模式（可选）**：基于审阅结论自动生成 Word track changes 和 comments（需用户显式触发）
- 不替代专业法律检索（法律法规可能更新）
- 不处理非合同类文档


## 10. 修订总结（审后飞书输出）

### 场景
使用 Kimi法宝 完成审阅后，以指定修订人名称（默认 Moonshot Legal）在 Word 修订模式中做了补充修改/标黄/批注，需输出简明摘要发飞书给同事二次核对。

### 输入
- 一份已审阅的 .docx 文件（含 track changes）
- 修订人名称（默认 Moonshot Legal，用户可指定其他名称）

### 处理步骤

**Step 1: 解析文档**
- 提取全部 track changes（w:ins / w:del / w:rPrChange），按作者分组
- 提取全部批注（comments），按作者分组
- 提取高亮（highlights），**仅保留指定修订人通过 w:rPrChange 添加的标黄**，排除对方预置的标黄
- 判断方法：run 有 `w:rPr/w:highlight` 且 `w:rPr/w:rPrChange`（author 为指定修订人）中不含 `w:highlight`，则该高亮为指定修订人新增

**Step 2: 精确定位条目**
- 每处修订定位到**最小子条目编号**（如 §2.2 而非 §2，§3.4 而非 §3）
- 定位方式：向上查找最近的编号段落（匹配 X.X、X.X.X 等格式）
- 若无子条目编号，退回到最近的大条号（如 §2）

**Step 3: 分类归组**
将提取到的内容分为两组：

**第一组 — 对方修改重点**（指定修订人通过标黄/批注标记的内容）：
- 指定修订人标黄的对方原文 → 说明关注原因
- 指定修订人批注中指向对方条款的内容 → 提取批注意图
- 对方（非指定修订人）的 track changes 中被指定修订人标注/关联的重要改动

**第二组 — 我方确认修改**（指定修订人自己的操作）：
- 指定修订人的 track changes（插入/删除）→ 描述具体操作
- 指定修订人的批注 → 提取批注内容和意图

**Step 4: 输出飞书文本**
按下方输出格式模板生成，直接输出纯文本（不用代码块包裹），用户可直接复制粘贴到飞书。

### 输出格式模板

```
以下是对方修改的重点，需要审阅：（已标黄/批注提请注意）
1. §X.X 条款名称 — 修改人+改动描述。风险/影响判断
2. §X.X 条款名称 — 改动描述。需确认的事项

能确定的改了以下：（{修订人名称} 修订，ref:《{文件名}》）
1. §X.X 条款名称 修改描述：具体操作（如删除"X"→插入"Y"）— 补充说明
2. §X.X 条款名称 批注：「批注内容」— 批注意图
```

### 格式要求
- **不用分割线**（---），板块间空一行替代
- 可用**加粗**区分重点
- 条款定位到**最小子条目**（§3.4 不写 §3，§2.2 不写 §2）
- ref 引用文件全名，飞书中替换为文件链接
- 第一板块每条**附风险判断语句**，让同事直接理解关注原因
- 第二板块每条**附修改意图说明**
