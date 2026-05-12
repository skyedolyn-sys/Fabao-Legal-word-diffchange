---
name: kimi-fabao
description: >
  USE THIS SKILL IMMEDIATELY when the user mentions "Kimi法宝", "法宝", "审一下修订", "审一下",
  "乙方视角", "甲方视角", "Moonshot视角", "月之暗面视角", "广告主视角",
  "service provider review", "vendor review", "client-side review", "advertiser review",
  or asks to review contract revisions.
  ALSO USE THIS SKILL when the user mentions "总结修订", "汇总修改", "整理修订处", "修订摘要",
  "同事核对", "二次核对", "发飞书", "贴飞书", "我改了哪些", "我的修订",
  or asks to summarize their own revisions (Moonshot Legal) for colleague review.
  CRITICAL: These words are the NAME of this skill. They NEVER mean asking about Kimi AI's features
  or capabilities. NEVER introduce yourself or explain Kimi when the user says these words.
  ALSO CRITICAL: The user does NOT need to upload a file first, and there does NOT need to be a .docx
  file in the current directory. ALWAYS read this skill's SKILL.md and execute its workflow.
  If the user has not provided a .docx file path, ask for it and then proceed.
  This skill provides: (1) contract revision review for .docx files with track changes, with automatic
  perspective detection based on party identification (甲方/乙方); (2) optional: auto-generate Word track
  changes & comments based on review conclusions (write capability); (3) post-review revision summary for
  Feishu/飞书 colleague handoff.
  DO NOT use for: new contracts without revisions, non-.docx formats.
---

# Kimi法宝 — 合同修订逐条审阅

## 1. 概述

本技能定位为**合同修订逐条审阅工具**，支持**甲方视角**和**乙方视角**两种审阅模式：

- **甲方视角**：以甲方利益为核心，关注乙方修订是否损害甲方权益。
- **乙方视角**：以乙方利益为核心，关注甲方条款是否损害乙方权益。

**视角自动识别**：本技能会从合同文本中自动提取甲乙方名称，匹配 Moonshot 关键词确认“我方”身份，然后自动派生审阅视角。无需用户手动指定视角（但用户可随时覆盖）。详见 §2.5 视角认定流程。

核心目标：帮助法务/商务人员快速识别合同修订中的风险条款，评估接受度，并给出具体的修改建议。

## 2. 触发条件

### 明确触发 — 主审阅流程
- 用户说出"Kimi法宝"、"法宝"、"审一下修订"、"审一下"等触发词 —— **即使用户没有上传文件、当前目录没有 .docx 文件，也必须立即触发本 skill**。此时询问用户合同文件路径即可。
- 用户上传 .docx 文件并说"审一下"、"看看修订"
- 用户明确提及视角词："乙方视角"、"甲方视角"、"Moonshot视角"、"月之暗面视角"、"广告主视角"、"service provider review"、"vendor review"、"client-side review"、"advertiser review"
- 用户明确说"我是甲方"、"我是乙方"、"我们是服务方"、"从广告主角度看"
- 中文技术/服务类合同（SaaS、AI、云计算、技术服务）
- 保密协议、NDA（Non-Disclosure Agreement）的修订审阅 —— **自动启用 NDA Playbook**
- 对方发来的模板合同（clean 版本，无修订标记）—— **自动启用 Template 模式**

> **视角说明**：无论用户是否指定视角，本技能都会先从合同文本中识别甲乙方身份，然后自动确认审阅视角。详见 §2.5。

**两种视角的差异对照**：
| 维度 | 甲方视角（我方=甲方） | 乙方视角（我方=乙方） |
|------|--------------------------|---------------------------|
| 关注焦点 | 乙方修订是否削弱甲方权利 | 甲方条款是否扩大乙方责任 |
| IP 条款 | 坚持"乙方 IP 归甲方" | 反对"乙方 IP 归甲方" |
| 付款条款 | 关注付款条件是否合理 | 反对延长账期、增加保证金 |
| 中止权 | 关注乙方单方中止权 | 反对甲方单方中止 |
| 争议解决 | 坚持有利管辖地 | 反对对己方不利的管辖地 |

### 明确触发 — 修订总结流程（§10）
- 用户提到"总结"/"汇总"/"整理" + "修订"/"修改"/"改动"
- 用户提到"同事核对"、"二次核对"、"发飞书"、"贴飞书"
- 用户提到"我改了哪些"、"我的修订"、"Moonshot Legal 的修改"
- 用户在完成 Kimi法宝 主流程审阅后，要求整理输出给同事

### 流程判断逻辑
- 用户意图是**分析对方改了什么** → 走主审阅流程（§3 Step 0-4）
- 用户意图是**总结我方改了什么，给同事看** → 走修订总结流程（§10）

### 明确不触发
- 无修订标记的原始合同（建议用户先开启修订模式）
- 非 .docx 格式
- 纯通用法律咨询（无具体合同文件）

## 2.5 视角认定流程

> **核心原则：视角不是用户告诉系统的，而是从合同文本中读出来的。**

审阅视角只有两种：**甲方视角**和**乙方视角**。所谓"Moonshot 视角"不是第三种视角，而是"确认 Moonshot 在合同中是甲方还是乙方"的过程，确认后自动派生为甲方视角或乙方视角。

**认定时机**：在调用分析引擎前（§3 Step 0），必须完成视角认定。

### Step A：合同主体识别（Party Identification）

从合同文本前 20 段中，提取**双方当事人名称**及其**角色标签**。

#### 中文合同提取

**提取方式**（依次尝试）：
1. **定义段匹配**：正则匹配 `甲方[：:]\s*(.+?)(?:\s*[（(]|$)` 和 `乙方[：:]\s*(.+?)(?:\s*[（(]|$)`
2. **合同首段推断**：从"本合同由以下双方签订"等句式中提取双方名称
3. **签署栏回溯**：如首页未找到，向文档末尾查找签章栏的公司名称

**提取结果**：甲方名称、乙方名称（角色标签固定为"甲方"/"乙方"）。

#### 英文合同提取

英文合同**不使用"甲方/乙方"**，而是使用角色名（role label）定义双方。

**提取方式**（依次尝试）：

1. **Preamble 定义句**（最可靠）：
   匹配以下常见句式，提取公司名和角色标签：
   - `This Agreement is entered into by and between [Company A] (the "Role A") and [Company B] (the "Role B")`
   - `This Agreement is made between [Company A] ("Role A") and [Company B] ("Role B")`
   - `BETWEEN: [Company A] ("Role A") AND [Company B] ("Role B")`
   - `[Company A], a [jurisdiction] [entity type] (hereinafter "Role A")`

2. **PARTIES / RECITALS 节**：
   在标题为 "PARTIES"、"RECITALS"、"WHEREAS" 的段落中查找公司名和角色定义。

3. **Signature Block 回溯**：
   在文档末尾查找 `By:___` / `Name:` / `Title:` / `For and on behalf of [Company]` 等签署栏。

**提取结果**：
- Party 1 名称 + 角色标签（如 `Revolut Ltd` + `Disclosing Party`）
- Party 2 名称 + 角色标签（如 `Moonshot AI, Inc.` + `Receiving Party`）

#### 角色标签 → 甲方/乙方映射

角色标签映射采用**分层查找**机制：

**映射优先级**：
1. **Playbook 自带映射**（优先）：每个 playbook 的 `clause_patterns.json` 中定义了 `perspective_config.party_role_mapping`，包含该合同类型专属的角色映射。如已确定使用某个 playbook（如 NDA），直接使用其映射。
2. **通用基础规则映射**（次优先）：`rules/clause_patterns.json` 中的 `perspective_config` 提供通用服务合同的角色映射。
3. **全局兜底表**（最终 fallback）：覆盖尚无专用 playbook 的合同类型。

**全局兜底映射表**（仅用于无对应 playbook 的合同类型）：

| 合同类型 | 甲方等价（Principal / Buyer 侧） | 乙方等价（Agent / Provider 侧） |
|---------|-------------------------------|-------------------------------|
| **许可协议** | Licensor | Licensee |
| **采购协议** | Buyer / Purchaser | Seller / Supplier / Vendor |
| **雇佣协议** | Employer / Company | Employee / Contractor |
| **租赁协议** | Landlord / Lessor | Tenant / Lessee |
| **分销协议** | Supplier / Principal / Manufacturer | Distributor / Agent / Reseller |
| **投资协议** | Investor | Company / Investee |
| **SaaS/API** | Customer / Subscriber | Provider / Platform |

> NDA、服务协议、推广协议的映射已内置于对应 playbook 的 `perspective_config` 中，不在此表重复。

**映射规则**：
- 如角色标签在 playbook 映射或兜底表中命中 → 直接映射
- 如角色标签为通用词（如 "Party A" / "Party B"）→ 无法映射，需进入 Step B P3 向用户确认
- 如角色标签不在任何映射中 → LLM 根据合同上下文判断其甲方/乙方等价关系
- **Mutual NDA 特别规则**：双方同时为 Discloser/Recipient 时，不分甲乙方，按 Step B 匹配 Moonshot 后以 **Moonshot 对手方的修订** 作为审阅目标（此规则定义在 NDA playbook 的 `perspective_config.special_rules` 中）

#### 双语合同 / 混合合同

- 如合同同时包含中英文当事人定义，**以中文"甲方/乙方"为准**（中文为法律效力文本的常见约定）
- 如合同明确约定"以英文版本为准"，则以英文角色标签为准
- 提取时应同时记录中英文名称（如甲方中文名 + 英文名）

### Step B：我方身份确认（Our Party）

**判断规则（优先级降序，命中即停）**：

| 优先级 | 判断方式 | 说明 |
|--------|---------|------|
| **P1** | **用户明确指定** | 用户说"我是甲方"/"乙方视角"/"I'm the Recipient" 等 → 直接采用 |
| **P2** | **合同文本中公司名称匹配** | 任一方名称中匹配 Moonshot 关键词库 → 自动确定我方角色 |
| **P3** | **向用户确认** | 无法自动判断时，必须询问用户 |

**Moonshot 关键词库**（匹配任一方当事人名称，不区分大小写，任一命中即匹配）：
- `月之暗面`
- `Moonshot`
- `北京月之暗面科技有限公司`
- `Moonshot AI`
- `Kimi`
- `moonshot`

> **英文实体名说明**：Moonshot 在英文合同中可能以不同法律实体出现（如 `Moonshot AI, Inc.`、`Moonshot Technology Ltd`、`Moonshot AI Pte. Ltd.` 等）。关键词库匹配为子串匹配，只要公司名中包含 `Moonshot` 即命中。

**P3 确认话术**：

中文合同：
> 合同中甲方为"XX公司"，乙方为"YY公司"。请确认我方是哪一方？

英文合同：
> Contract parties: [Company A] (Role A) and [Company B] (Role B). Which party is ours?

如双方名称都未识别到：
> 未能从合同文本中识别当事人名称。请告知我方在合同中的角色。

**⚠️ 重要：不再设置默认视角。** 如果无法通过 P1 或 P2 确定我方身份，必须通过 P3 向用户确认，不得默认为乙方。

### Step C：审阅视角自动派生

| 我方身份 | → 审阅视角 | 审阅关注点 |
|---------|-----------|-----------|
| 我方 = 甲方（或甲方等价角色） | **甲方视角** | 关注对方修订是否损害我方权益 |
| 我方 = 乙方（或乙方等价角色） | **乙方视角** | 关注对方条款是否损害我方权益 |

**报告开头必须输出确认信息**：

中文合同：
```
甲方：{甲方名称} ｜ 乙方：{乙方名称}
我方：{公司名称}（{甲方/乙方}）→ {甲方/乙方}视角
```

英文合同：
```
{Role A}：{Company A} ｜ {Role B}：{Company B}
Our Party：{Company Name}（{Role Label} ≈ {甲方/乙方}）→ {甲方/乙方}视角
```

### 视角对输出的影响

- **报告标题**：注明当前视角和我方身份（如"我方：Moonshot AI, Inc.（Receiving Party ≈ 乙方）→ 乙方视角"）
- **风险等级判断标准**：根据视角切换（见 §5 风险等级定义）
- **分析维度**：根据视角选择对应列的分析要点（见 §6 分析维度模板）
- **建议动作措辞**：
  - 甲方视角：中文合同"建议要求乙方修改"，英文合同"Recommend requesting {Counter-party Role} to revise"
  - 乙方视角：中文合同"建议争取修改"，英文合同"Recommend negotiating revision"
- **Playbook 选择**：基于合同类型选 playbook（NDA / marketing-agency / 通用），与视角独立
  - 甲方视角下使用 marketing-agency playbook 的风险规则天然匹配
  - 乙方视角下使用 base/NDA playbook 的风险规则天然匹配
  - 如视角与 playbook 内置视角不一致（如乙方视角 + marketing-agency playbook），LLM 需在复核阶段翻转风险评级

### "Moonshot视角"触发词的处理

当用户说"Moonshot视角"或"月之暗面视角"时：
1. **不作为独立视角处理**
2. 正常执行 Step A（合同主体识别）→ Step B P2（公司名称匹配 Moonshot 关键词库）
3. 如 P2 命中 → 自动确定 Moonshot 是甲方还是乙方（英文合同通过角色映射表确定）→ 派生视角
4. 如 P2 未命中 → 进入 P3 向用户确认

## 3. 工作流（5步 + 可选写入层）

### Step 0: 合同主体识别与视角认定

本步骤在调用分析引擎之前执行，是整个审阅流程的前置步骤。

**0a. 文件路径处理**：

- 如果用户已提供 .docx 文件路径（上传文件或指定路径），直接使用该路径。
- **如果用户只说触发词（如“kimi法宝”）但未提供文件**：
  1. 先搜索当前目录及子目录中是否存在 .docx 文件（使用 Glob 工具）
  2. 如果找到 1 个 .docx 文件，直接使用该文件并告知用户
  3. 如果找到多个 .docx 文件，列出候选文件让用户选择
  4. 如果未找到 .docx 文件，询问用户合同文件路径
- **不得因为没有文件就拒绝执行或介绍 Kimi 功能。**

**0b. 合同主体识别**（执行 §2.5 Step A）：

获取到文件后，先快速读取合同前 20 段文本（可先运行引擎获取 `paragraphs` 数组，或直接读取文件首页），提取甲乙方名称。

**0c. 我方身份确认与视角派生**（执行 §2.5 Step B + Step C）：

1. 检查用户是否已明确指定视角（P1）
2. 在甲乙方名称中匹配 Moonshot 关键词库（P2）
3. 如 P1 和 P2 均未命中，向用户确认（P3）
4. 确定我方身份后，自动派生审阅视角

**0d. 合同类型判断**：

LLM 根据以下信息判断合同类型，决定是否使用专用 Playbook：

1. **用户描述**（最高优先级）：用户是否明确说了“NDA”、“保密协议”等
2. **文件名**：如 `NDA_v2.docx`、`保密协议-修订版.docx`
3. **文档标题与首段**：读取文件前 3-5 个段落，看是否出现“保密协议”、“Non-Disclosure”等字样
4. **条款标题分布**：如“保密信息定义”、“除外情形”等 NDA 特有条款密集出现

**判断结果处理**：
- **高置信度识别为 NDA**：直接调用脚本时附加 `--playbook nda`，并告知用户“已启用 NDA 专用审阅规则”
- **高置信度识别为通用技术服务合同**：使用默认通用规则，不附加 `--playbook`
- **不确定或混合合同**：询问用户“这是一份保密协议/NDA 吗？如是，我将启用专用审阅规则获得更精准的分析。”

**Step 0 完成后，输出确认信息**：
```
📋 合同基本信息
甲方：{甲方名称} ｜ 乙方：{乙方名称}
我方：{公司名称}（{甲方/乙方}）→ {甲方/乙方}视角
合同类型：{类型} ｜ Playbook：{playbook名称/通用}
```

### Step 1: 运行分析引擎

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

**输出文件命名规范**：
- 格式：`{原合同名}_Moonshot Legal_{YYYYMMDD}.docx`
- 示例：`NDA_template_Revolut_Moonshot Legal_20260509.docx`
- 日期为执行当天，格式固定 8 位数字（年4+月2+日2）
- 输出文件必须保存到**原文件所在的同一文件夹**，不得放到 `/tmp/` 或其他临时目录

**输出路径三件套（强制，每次生成文件后必须执行）**：
1. **验证路径存在**：输出前先用 `ls` 或 `find` 确认文件确实存在（目录可能被用户重命名/移动）
2. **输出文件路径**：纯文本绝对路径，单独一行，iTerm2 可 cmd+click 打开
   - ✅ 正确：纯文本路径，如 `/Users/moonshot/Documents/合同审核类/NDA/file.docx`
   - ❌ 禁止：不用 markdown 链接 `[text](url)`、不用 `file://` URL、不用 OSC 8 转义序列
3. **打开文件夹**：用 `open "文件夹路径/"` 在 Finder 中定位
4. **总览表**：输出 Step 8 修订及建议总览表

**输出示例**：
```
📄 输出文件

中文批注版：/Users/moonshot/Documents/合同审核类/NDA/xxx_v2.docx
英文批注版：/Users/moonshot/Documents/合同审核类/NDA/xxx_v2_EN.docx

📂 已在 Finder 中打开所在文件夹

[总览表]
```

**文件格式一致性规则（强制）**：
- **原则**：**输入什么格式，输出什么格式。**
- 本技能的分析引擎和写入层基于 `.docx`（OOXML）工作。若用户提供的原始文件为 `.doc`（Word 97-2003）或其他非 `.docx` 格式：
  1. 分析/修改前，使用系统工具（如 macOS `textutil` 或 LibreOffice）将原始文件转换为 `.docx` 作为**中间态**
  2. 完成分析或写入后，**必须将输出文件转回原始格式**
  3. **不得将中间 `.docx` 文件作为最终交付物暴露给用户**
- **原因**：`textutil` 等工具生成的 `.docx` 中间文件可能缺少 `word/styles.xml` 等 Word 必需的内部部件，导致 Microsoft Word / Word for Mac 无法直接打开；而转回 `.doc` 时，转换引擎会补齐缺失信息，兼容性更好。

**用户交互**：
- 默认行为（用户只说"审一下"）：只执行 Step 0-4，输出审阅报告
- 触发写入（用户说"并执行写入"）：Step 0-4 + Step 5-8，输出报告 + 已修订 docx + 总览表
- 分步触发：先审阅生成报告，用户后续说"基于刚才结果执行写入"，从上下文获取 engine_output 继续 Step 5-8

**批注格式要求**：
- 每条批注必须以优先级标签开头：`[P0 底线]`、`[P1 建议修改]`、`[P2 协商争取]`、`[P3 可接受]`
- 标签后接空格，再写批注正文
- 语气保持外交化、柔和，不使用"必须""强烈建议"等强硬措辞，应使用"建议考虑""如有可能""供参考"
- 示例：`[P0 底线] 目前仅赋予 Discloser 单方申请禁令救济的权利。建议改为“任何一方”均有权申请，这样双方的合法权益都能得到平等保护。`

### Step 8: 输出修订及建议总览表

**触发时机**：Step 7 执行写入完成后，**必须自动输出**此表，无需用户额外要求。

**排序规则**：先按优先级分组（P0 → P1 → P2 → P3），每组内按条款在合同中的出现顺序排列。

**表格模板**：

```markdown
**{合同名称} 修订及建议总览表**
**审阅方：Moonshot Legal ｜ 日期：{YYYY-MM-DD} ｜ 视角：{甲方/乙方}（{我方公司名称}）**

---

| # | 优先级 | 条款 | 风险点 | 操作 | 原文要点 | 修订 / 建议内容 |
|---|--------|------|--------|------|----------|----------------|
| 1 | 🔴 **P0 底线** | §X(x) | {风险描述} | ✏️ 改 + 💬 批注 | {原文关键信息} | → {修订后内容} |
| ... | 🟠 **P1 建议修改** | ... | ... | ... | ... | ... |
| ... | 🟡 **P2 协商争取** | ... | ... | ... | ... | ... |
| ... | 🟢 **P3 可接受** | ... | — | 💬 批注 | ... | ✅ 标准条款，建议接受 |

---

**汇总统计**

| 优先级 | 含义 | 条数 | 文本修改 | 仅批注 |
|--------|------|------|----------|--------|
| 🔴 P0 底线 | 不可退让，影响核心权益 | X | X | X |
| 🟠 P1 建议修改 | 重要，强烈建议争取 | X | X | X |
| 🟡 P2 协商争取 | 有利条款，灵活把握 | X | X | X |
| 🟢 P3 可接受 | 标准条款，无需修改 | X | X | X |
| **合计** | | **X** | **X** | **X** |

**谈判节奏建议：** P0 底线先行 → P1 配合施压 → P2 灵活取舍 → P3 主动接受释放善意。
```

**字段说明**：
- **优先级**：带 emoji 色标 + 加粗标签（🔴 P0 底线 / 🟠 P1 建议修改 / 🟡 P2 协商争取 / 🟢 P3 可接受）
- **条款**：使用合同原文编号（如 §2(b)、§5(g)、VARIABLES 争议解决）
- **风险点**：一句话概括风险（P3 可接受项此栏写 "—"）
- **操作**：`✏️ 改 + 💬 批注`（有文本修改+批注）或 `💬 批注`（仅批注无文本改动）
- **原文要点**：原条款关键信息，高亮核心词（用加粗标记）
- **修订 / 建议内容**：有改动的用 `→` 开头写修订内容；仅批注的写建议说明；P3 可接受项写 `✅ 标准条款，建议接受`

**优先级分级标准**：

| 等级 | 含义 | 判断标准 |
|------|------|----------|
| P0 底线 | 不可退让 | 影响核心权益：无过错责任、单方救济权、管辖地严重不利、知识产权完全转让 |
| P1 建议修改 | 重要修改 | 条款明显不对等，但不直接危及核心权益：范围过宽、权利单方享有 |
| P2 协商争取 | 灵活协商 | 有改进空间但影响有限：时限模糊、期限偏长、保留条款缺上限 |
| P3 可接受 | 标准条款 | 行业惯例、表述清晰合理、双方对等，无需修改 |

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
- **甲方**：{甲方名称}
- **乙方**：{乙方名称}
- **我方**：{公司名称}（{甲方/乙方}）
- **审阅视角**：{甲方视角 / 乙方视角}
- **修订总数**：{N} 处（插入 {M} 处，删除 {K} 处）
- **批注数**：{P} 条

## 修订概览表

| 序号 | 条款 | 类型 | 风险等级 | 建议动作 | 审阅优先级 |
|------|------|------|----------|----------|------------|
| 1 | 第3条 服务范围 | 服务定义 | 🟠需协商 | 协商 | P1 建议修改 |
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
1. **P0（底线）**：{条款列表} — 不可退让，影响核心权益
2. **P1（建议修改）**：{条款列表} — 重要，强烈建议争取
3. **P2（协商争取）**：{条款列表} — 有利条款，灵活把握
4. **P3（可接受）**：{条款列表} — 标准条款，无需修改

### 整体评估
- 修订总体倾向：{对我方有利 / 中性 / 不利}
- 关键风险点：{总结}
- 修改建议汇总：{总体修改方向}
```

## 5. 风险等级定义

> **视角适配**：以下标准根据当前审阅视角（乙方或甲方）动态适用。输出报告时必须注明当前视角。

### 🔴 强烈反对

**乙方视角标准**：
- 责任上限被取消或大幅降低
- 引入无过错赔偿责任（如"无论是否违约"）
- 知识产权从乙方完全转让给甲方
- 付款条件恶化到影响现金流安全
- 增加无法履行的义务或无限期承诺

**甲方视角标准**（我方=甲方时适用）：
- 知识产权从甲方转让给乙方，或甲方 IP 授权范围被扩大
- 乙方引入单方免责条款（如"平台删除乙方不承担任何责任"且无协助义务）
- 付款条件中乙方获得单方调价权或预付款/保证金要求
- 争议解决地被改为对甲方不利的境外仲裁/诉讼
- 乙方单方中止权过大（无通知期、无紧急情况限定）
- 甲方核心数据/用户信息归属被模糊或转移给乙方

**处理**：必须在签约前要求修改，不可单独接受。

### 🟠 需协商

**乙方视角标准**：
- 赔偿范围扩大但仍有上限
- 服务范围增加但可量化
- 期限延长在可接受边缘
- 数据安全义务增加但行业标准可接受
- 终止条件对乙方略不利

**甲方视角标准**（我方=甲方时适用）：
- 乙方赔偿上限过低（如仅限制为当月服务费）
- 乙方免责范围扩大（如素材违规被删完全免责且不协助）
- 服务范围被缩窄或乙方增加过多例外情形
- 乙方终止条件过于宽松（轻微违约即可终止）
- 返点/优惠条件的排除范围过宽，与商务谈判结果不符
- 数据安全义务低于行业标准或数据泄露通知时限过长

**处理**：提出替代方案，争取更有利条件。

### 🟢 可接受

**通用标准**（双视角一致）：
- 纯措辞优化，无实质影响
- 对**当前视角方**有利或中性的修订
- 行业标准条款的常规调整
- 格式、标点、非关键定义的调整

**处理**：直接接受，无需协商。

## 6. 分析维度模板

> 以下模板按条款类型列出**双视角**的分析要点。实际审阅时，根据当前视角选择性使用对应列的要点。

### 服务定义条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 服务范围是否被扩大？是否包含隐含义务？ | 服务范围是否被缩窄？乙方是否增加过多例外或豁免？ |
| 验收标准是否变得主观或不可达成？ | 验收标准是否变得过于宽松，导致甲方无法有效监督？ |
| 是否引入"满足甲方所有需求"等开放式表述？ | 是否引入"尽力而为"等模糊表述，降低乙方责任？ |
| SOW 变更流程是否对乙方不利？ | SOW 变更流程是否赋予乙方单方拒绝权？ |

### 费用与支付条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 付款账期是否延长？ | 付款账期是否合理？是否有预付款保护？ |
| 是否增加预付款/保证金要求？ | 是否缺少预付款或履约保证金？ |
| 发票要求是否变得不合理？ | 发票要求是否合规，能否满足甲方财务流程？ |
| 是否引入单方调价权？ | 乙方是否保留单方调价权或汇率风险转嫁条款？ |

### 期限与终止条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 自动续约是否对乙方不利？ | 自动续约是否对甲方不利（如锁定期过长）？ |
| 甲方单方终止权是否扩大？ | 乙方单方终止权是否过大（轻微违约即可终止）？ |
| 终止后过渡期义务是否合理？ | 终止后乙方是否拒绝配合数据迁移/账户交接？ |
| 是否有排他性或竞业限制？ | 是否有排他性要求限制甲方与其他代理商合作？ |

### 知识产权条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 背景 IP 归属是否清晰？ | 甲方背景 IP 是否被乙方不当使用或主张权利？ |
| 前景 IP 是否从许可变为转让？ | 乙方创作素材的 IP 是否明确归甲方所有？ |
| 是否引入"职务作品"等扩大甲方权利的定义？ | 是否明确乙方需配合签署权属转让文件？ |
| 开源软件合规义务是否合理？ | 乙方使用开源软件是否给甲方带来传染许可风险？ |

### 违约责任条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 违约金比例是否过高？ | 乙方违约金比例是否过低，不足以约束违约行为？ |
| 是否取消责任上限或例外？ | 乙方责任上限是否过窄（如仅限直接损失）？ |
| 是否引入间接损失赔偿？ | 甲方是否被排除间接损失索赔权？ |
| 是否增加单方解约权？ | 乙方是否享有过于宽松的单方解约权？ |

### 数据安全条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 数据安全义务是否超出行业标准？ | 数据安全义务是否低于行业标准？ |
| 数据泄露通知时限是否过短？ | 数据泄露通知时限是否过长（超过24-48小时）？ |
| 是否要求承担第三方索赔？ | 乙方是否推卸数据泄露的第三方索赔责任？ |
| 数据归属和删除义务是否明确？ | 合作终止后乙方是否承诺彻底删除甲方数据？ |

### 不可抗力条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 不可抗力定义是否过窄？ | 不可抗力定义是否过宽（如将平台政策变化纳入）？ |
| 免责范围是否被限制？ | 乙方是否借不可抗力过度扩大免责范围？ |
| 通知义务是否过重？ | 乙方是否未设置合理的不可抗力通知和恢复义务？ |

### 其他条款

| 乙方视角关注点 | 甲方视角关注点 |
|---------------|--------------------------|
| 争议解决地点是否对乙方不利？ | 争议解决是否约定为中国境内仲裁/诉讼（如 SHIAC）？ |
| 法律适用是否可接受？ | 法律适用是否为中华人民共和国法律（不含港澳台）？ |
| 完整协议条款是否排除了先前的有利承诺？ | 完整协议条款是否排除了乙方先前的口头/书面承诺？ |
| — | 保密条款中甲方保密信息的定义是否过宽？ |

## 7. Playbook 架构（细分合同类型规则）

除通用规则外，支持按合同类型加载专用 Playbook 规则，实现更精准的条款分类、风险识别和视角配置。

### 已有 Playbook

| Playbook ID | 适用场景 | 原生视角 | 甲方等价（示例） | 乙方等价（示例） | 专用规则 |
|-------------|----------|----------|----------------|----------------|----------|
| `nda` | 保密协议 / NDA | 乙方（接收方） | 披露方 / Disclosing Party | 接收方 / Receiving Party | 11 类条款 + 15 条风险规则 + mutual NDA 规则 |
| `marketing-agency` | 推广/代理协议 | 甲方（广告主） | 广告主 / Advertiser / 委托方 | 代理商 / Agency / 代理方 | 10 类条款 + 15 条风险规则 + write_actions |
| _(base)_ | 通用技术/服务合同 | 乙方 | 甲方 / Client / Customer | 乙方 / Service Provider / Vendor | 8 类条款 + 18 条风险规则 |

### 使用方式

```bash
# 通用规则（默认）
python3 analyze_revisions.py contract.docx

# NDA 专用 Playbook
python3 analyze_revisions.py nda.docx --playbook nda

# 推广协议专用 Playbook
python3 analyze_revisions.py promo.docx --playbook marketing-agency
```

### 工作原理

- Playbook 规则存放在 `rules/playbooks/<playbook_id>/` 目录下
- 引擎优先加载 Playbook 目录下的 `clause_patterns.json` 和 `risk_rules.json`
- 若 Playbook 目录下缺少某个规则文件，自动回退到基础 `rules/` 目录
- 输出 JSON 中新增 `playbook_info` 字段标识当前使用的 Playbook
- 每个 Playbook 的 `clause_patterns.json` 包含 `perspective_config`，定义该 playbook 的原生视角和角色映射（详见 §2.5 Step A）

### 新增 Playbook 步骤（7-Step Checklist）

新增一个 Playbook 需要完成以下 7 步：

| # | 步骤 | 产出文件 | 说明 |
|---|------|----------|------|
| 1 | **确定合同类型 & playbook_id** | — | ID 格式：`kebab-case`，如 `software-license` |
| 2 | **确定原生视角** | — | 该 playbook 的风险规则基于甲方还是乙方立场编写？ |
| 3 | **编写 `clause_patterns.json`** | `rules/playbooks/<id>/clause_patterns.json` | 条款类型定义 + `perspective_config`（见下方模板） |
| 4 | **编写 `risk_rules.json`** | `rules/playbooks/<id>/risk_rules.json` | 按原生视角编写风险规则 |
| 5 | **编写 `write_actions.json`（可选）** | `rules/playbooks/<id>/write_actions.json` | 如需写入能力（Word 批注/修订） |
| 6 | **编写 `standard_clauses.json`（可选）** | `rules/playbooks/<id>/standard_clauses.json` | 标准条款文本库 |
| 7 | **运行验证** | — | `python3 analyze_revisions.py test.docx --playbook <id>` 确认输出正常 |

#### `clause_patterns.json` 模板

新 playbook 的 `clause_patterns.json` 必须包含以下顶层字段：

```json
{
  "playbook_id": "<your-id>",
  "playbook_name": "Playbook 显示名称",
  "perspective_config": {
    "native_perspective": "甲方 或 乙方",
    "party_role_mapping": {
      "甲方_equivalents": {
        "cn": ["甲方"],
        "en": ["Client"]
      },
      "乙方_equivalents": {
        "cn": ["乙方"],
        "en": ["Service Provider"]
      }
    }
  },
  "patterns": {
    "条款类型名": {
      "keywords": ["关键词1", "关键词2"],
      "description": "该条款类型的描述"
    }
  }
}
```

> ⚠️ `perspective_config` 是必填字段。`native_perspective` 必须与 `risk_rules.json` 中的风险规则立场一致——引擎在非原生视角下运行时，LLM 层会在 Step 2 复核阶段对风险等级做方向性调整。


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
- 分析引擎仅支持 `.docx` 格式的原生修订标记（w:ins / w:del）
- **`.doc` 文件处理**：如用户提交 `.doc`，必须先转换为 `.docx` 再处理，最终输出必须转回 `.doc`（见上文"文件格式一致性规则"）
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
