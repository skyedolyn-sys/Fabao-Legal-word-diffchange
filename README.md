# Kimi法宝

**合同修订逐条审阅引擎** — Moonshot Legal 内部工具

```
  ┌──────────────────────────────────────────────────────────┐
  │  📄  对方发来修订版合同（.docx, track changes）            │
  └───────────────────────┬──────────────────────────────────┘
                          ▼
                ┌───────────────────┐
                │    Kimi法宝 审阅   │
                │  视角自动识别 → 逐条  │
                └────────┬──────────┘
                         ▼
  ┌──────────────────────────────────────────────────────────┐
  │  🔴 P0  第8条 — 新增无过错责任         → 底线，不可接受     │
  │  🟠 P1  第4章3条 — 删除数据不进训练承诺  → 建议恢复原文      │
  │  🟡 P2  第3章8条 — 赔偿上限调至50%      → 协商争取更高比例   │
  │  🟢 P3  第7章2条 — 通知期限30→15天      → 可接受           │
  │                                                          │
  │  📎 修订版 Word 文件已生成（含 track changes + 批注）        │
  │  📋 飞书摘要已就绪，可直接发送同事二次核对                     │
  └──────────────────────────────────────────────────────────┘
```

纯 Python · 零外部依赖 · 集成 Kimi CLI

---

## 定位与适用场景

本工具面向 Moonshot 法务及商务团队，用于高效处理合同修订审阅工作。

**典型场景**：收到对方修订版合同后，需逐条分析修订内容、评估风险、产出审阅意见并回传。

**原有流程**：打开 Word → 肉眼逐条扫描修订 → 手动整理修改点 → 撰写审阅意见 → 发飞书给同事核对

**使用本工具**：在 Kimi CLI 中输入 `法宝`，拖入 `.docx` 文件，自动完成全部流程。

---

## 核心能力

| 能力 | 说明 |
|:---|:---|
| **修订解析** | 解析 Word 原生 track changes（`w:ins` / `w:del`），逐处提取，无遗漏 |
| **智能编号还原** | `NumberingResolver` 解析 `word/numbering.xml`，还原 `第一章` / `1、` / `（一）` / `A.` / `(a)` / `(i)` 等动态编号，匹配 Word 最终视图 |
| **条款树构建** | 三级标题检测（Word 样式 → 编号启发式 → 粗体回退）+ 上下文感知层级推断，单调栈任意深度嵌套 |
| **视角自动识别** | 从合同文本中提取甲乙方名称，匹配 Moonshot 关键词库确认我方身份，自动派生审阅视角（甲方 / 乙方） |
| **四级风险分级** | 🔴 P0 底线 · 🟠 P1 建议修改 · 🟡 P2 协商争取 · 🟢 P3 可接受 |
| **精确定位** | 每处修订精确到 `第四章 > 3、数据使用限制 > (a) 训练数据`，而非"大约在第几页" |
| **反向写入** | 自动生成 Word track changes + 批注（含优先级前缀），直接回传对方 |
| **飞书摘要** | 输出结构化修订摘要，供同事二次核对 |

---

## 审阅视角

本工具支持**甲方视角**与**乙方视角**两种审阅模式，视角由系统从合同文本中自动识别。

| 维度 | 甲方视角（我方 = 甲方） | 乙方视角（我方 = 乙方） |
|:---|:---|:---|
| 关注焦点 | 乙方修订是否削弱甲方权利 | 甲方条款是否扩大乙方责任 |
| IP 条款 | 确保成果 IP 归属甲方 | 反对背景 IP 或全部 IP 转让 |
| 付款条款 | 关注付款条件合理性 | 反对延长账期、增加保证金 |
| 终止权 | 关注乙方单方终止风险 | 反对甲方单方终止权扩大 |
| 争议解决 | 确保管辖地对甲方有利 | 反对对我方不利的管辖地 |

**视角认定流程**：合同主体识别（Party Identification）→ Moonshot 关键词匹配 → 自动确认我方角色 → 派生审阅视角。详见 `SKILL.md` §2.5。

---

## 优先级体系

| 级别 | 含义 | 判定标准 |
|:---|:---|:---|
| 🔴 **P0 底线** | 不可退让 | 无过错责任、单方救济权、管辖地严重不利、IP 完全转让 |
| 🟠 **P1 建议修改** | 重要，强烈建议争取 | 责任上限不合理、数据安全承诺缺失、单方终止权扩大 |
| 🟡 **P2 协商争取** | 有利条款，灵活把握 | 账期延长、通知期缩短、审计权范围 |
| 🟢 **P3 可接受** | 标准条款，无需修改 | 文字润色、格式调整、合理范围内的期限变更 |

**谈判节奏**：P0 底线先行 → P1 配合施压 → P2 灵活取舍 → P3 主动接受释放善意。

---

## 快速开始

### 安装

```bash
git clone git@github.com:skyedolyn-sys/kimi-fabao-Moonshot-Legal.git \
  ~/.claude/skills/kimi-fabao
```

纯 Python 标准库，无需 `pip install`。

### 使用

在 Kimi CLI 中：

| 指令 | 效果 |
|:---|:---|
| `法宝` / `Kimi法宝` / `审一下修订` | 启动合同修订审阅 |
| `甲方视角` / `乙方视角` / `广告主视角` | 指定审阅视角（亦可自动识别） |
| `总结修订` / `发飞书` | 生成飞书友好的修订摘要 |

拖入 `.docx` 合同文件即可开始审阅。

---

## 工作流

```
                            .docx 文件输入
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   Step 0                  Step 1                  Step 2
   视角认定                 修订提取                 风险分析
   ─────────               ─────────               ─────────
   · 甲乙方名称提取         · DOCX 解压              · 条款类型分类
   · Moonshot 关键词匹配    · track changes 解析     · 规则引擎风险分级
   · 审阅视角派生           · NumberingResolver       · 主题聚类
                           · 三级标题检测 + 上下文推断
                           · 条款树构建 + 附件分离
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                           Step 3 — LLM 审阅
                           ─────────────────
                           · 逐条修订分析
                           · P0-P3 优先级判定
                           · 谈判话术生成
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              Step 5-7      Step 8       Step 10
              反向写入       总览表输出    飞书摘要
              ──────────    ──────────   ──────────
              · 生成修订     · P0→P3排序  · 结构化摘要
              · 注入批注     · 条款位置    · 同事核对
              · 保存 .docx   · 谈判话术    · 一键发送
```

---

## 技术架构

### 修订提取引擎（`extract_revisions.py`）

```
 .docx (ZIP)
     │
     ├── word/document.xml ──────────── track changes 解析
     │                                  w:ins / w:del / w:rPr(rPrChange)
     │
     ├── word/numbering.xml ─────────── NumberingResolver
     │   · numFmt: decimal / chineseCountingThousand / lowerLetter / lowerRoman ...
     │   · 跳过整段删除的修订，匹配 Word Final 视图编号
     │   · 计数器重置：子级编号在父级推进时归零
     │
     ├── 三级标题检测
     │   ├── ① Word heading styles (outline_level)
     │   ├── ② 编号启发式 (第X章 / 第X条 / 一、/ 1、/ X.X / Article X / A. / (a) / (i) / (1))
     │   └── ③ 粗体回退（仅当文档无任何编号模式时启用）
     │
     ├── 上下文感知层级推断
     │   · ancestor_type 跟踪：有状态遍历，每个段落知道上一个 heading 的类型
     │   · 12+ 条推断规则：编号模式 × 祖先上下文 → heading_level
     │   · 罗马/字母消歧：(v) 等歧义字符通过缩进 + 祖先序列判定
     │
     ├── build_clause_tree ──────────── 单调栈，任意深度嵌套
     ├── _separate_appendices ───────── 层级感知切分（仅 heading_level=1 切为顶级附件）
     └── attach_location_paths ──────── 每处修订关联完整条款路径
```

### 风险分析引擎（`analyze_revisions.py`）

```
 提取结果 (JSON)
     │
     ├── ClauseClassifier ──── 条款类型识别（8 通用类型 / NDA 11 类型）
     ├── RiskAssessor ──────── 规则引擎匹配（19 条精准规则 + Playbook 规则）
     ├── RevisionClusterer ─── 主题聚类（责任扩大 / IP转让 / 付款恶化 / 服务扩大 / 数据安全）
     └── 输出 JSON → LLM 消费
```

### 反向写入层（`scripts/write/`）

```
 审阅结论
     │
     ├── write_plan_generator.py ──── 生成写入计划（JSON 指令序列）
     ├── execute_revisions.py ─────── 执行写入
     │   ├── revision_builder.py ──── 构建 w:ins / w:del 修订标记（保留原始字体与样式）
     │   └── comment_injector.py ──── 注入批注（含 annotationRef + 优先级前缀）
     └── docx_operator.py ─────────── DOCX 底层读写
         · Content-Type 自动注册
         · 命名空间前缀修复（ns0: → 默认命名空间）
         · XML 声明与根元素 header 保留
```

---

## Playbook 体系

Playbook 为特定合同类型提供专用的条款分类规则、风险评估规则和写入动作模板。

| Playbook | 适用合同 | 默认视角 | 规则数 |
|:---|:---|:---|:---|
| **通用（default）** | 技术服务、SaaS、云计算等 | 乙方 | 19 条风险规则 |
| **NDA** | 保密协议 / Confidentiality Agreement | 乙方 | 17 条风险规则 + 标准条款库 |
| **推广协议** | 广告代理 / 投放合作 | 甲方（广告主） | 专用风险规则 |

每个 Playbook 包含：
- `clause_patterns.json` — 条款类型分类规则 + 视角角色映射（`perspective_config`）
- `risk_rules.json` — 风险评估规则
- `write_actions.json` — 风险规则到写入动作的映射
- `standard_clauses.json`（可选）— 标准条款替换库

---

## 项目结构

```
kimi-fabao/
├── SKILL.md                              # Skill 定义（Kimi CLI 读取）
├── README.md
├── CHANGELOG-heading-engine.md           # Heading 引擎改进记录
├── kimi-fabao                            # 入口脚本
│
├── scripts/
│   ├── extract_revisions.py              # 修订提取 + NumberingResolver + 标题检测
│   ├── analyze_revisions.py              # 风险分析 + 条款分类 + 聚类
│   ├── expand_risk_rules.py              # 风险规则扩充工具
│   └── write/
│       ├── write_plan_generator.py       # 写入计划生成
│       ├── execute_revisions.py          # 写入执行
│       └── validators.py                 # 写入计划校验 + 文档匹配校验
│
├── rules/
│   ├── clause_patterns.json              # 通用条款类型匹配规则（含 perspective_config）
│   ├── risk_rules.json                   # 通用风险分级规则（19 条）
│   ├── write_actions.json                # 通用写入动作模板
│   └── playbooks/
│       ├── nda/                           # NDA 专用 Playbook
│       │   ├── clause_patterns.json       #   条款分类（11 类型 + 视角映射）
│       │   ├── risk_rules.json            #   风险规则（17 条）
│       │   ├── write_actions.json         #   写入动作模板
│       │   └── standard_clauses.json      #   标准条款库（SIAC 仲裁等）
│       └── marketing-agency/              # 推广协议 Playbook
│           ├── clause_patterns.json       #   条款分类（广告主视角）
│           ├── risk_rules.json            #   风险规则
│           └── write_actions.json         #   写入动作模板
│
├── lib/
│   ├── docx_operator.py                  # DOCX 底层读写（ZIP / XML / Content-Type）
│   ├── revision_builder.py               # 修订标记构建（w:ins / w:del + 样式保留）
│   └── comment_injector.py               # 批注注入（annotationRef + 优先级前缀）
│
└── evals/
    └── evals.json                        # Skill 评估用例
```

---

## 已验证合同类型

| 合同 | 语言 | 编号方式 | 结构复杂度 | 修订量 |
|:---|:---|:---|:---|:---|
| Kimi 大模型技术服务协议 | 中文 | `w:numPr`（第X章 / N、/（N）） | 7 章 + 1 附件 | 68 处 |
| SHEIN 大模型技术服务协议 | 中英混合 | `w:numPr` + A. / (a) / (i) | 9 章 + 6 附件（含 DPA + EU/Swiss/UK SCC） | 1010 处 |
| Enterprise Service Agreement | 英文 | 内联 `X.X` + Article X | 15 Article | 177 处 |
| NDA 保密协议 | 中 / 英 | 混合 | — | — |

---

## 输出规范

### 文件命名

```
{合同简称}_Moonshot Legal_{YYYYMMDD}.docx
```

### 批注格式

每条批注以优先级前缀开头：

```
[P0 底线] 无过错责任条款对我方极为不利，建议删除整条。
[P1 建议修改] 数据不进训练承诺被删除，建议恢复原文。
[P2 协商争取] 赔偿上限50%偏低，建议争取至100%。
[P3 可接受] 通知期限调整在合理范围内。
```

---

## 团队协作

```bash
# 维护者：更新规则后推送
cd ~/.claude/skills/kimi-fabao
git add . && git commit -m "update: 新增XX条风险规则" && git push

# 团队成员：同步最新版本
cd ~/.claude/skills/kimi-fabao && git pull
```

---

## 安全与合规

- **私有仓库** — 仅限授权人员访问
- **禁止开源** — 包含内部法律审阅策略，严禁对外分享
- **使用范围** — Moonshot / 月之暗面 / 揽月星辰 / Kimi 及关联实体
- **免责声明** — 本工具输出仅供参考，不构成法律意见；重大决策应咨询执业律师

---

<p align="center"><sub>Moonshot Legal · Powered by Kimi CLI + Python stdlib</sub></p>
