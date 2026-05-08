# ⚔️ Kimi法宝

> *甲方改了一百处，法宝一秒全看透。*

```
         ┌─────────────────────────────────────┐
         │  📄 对方发来一份修订版合同.docx       │
         │     track changes 密密麻麻            │
         │     红红绿绿看得头疼                   │
         └──────────────┬──────────────────────┘
                        ▼
              ┌─────────────────┐
              │   ⚔️ Kimi法宝   │
              │   "法宝，审一下" │
              └────────┬────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  🔴 第四章3条：删除了数据不进训练承诺 → 强烈反对  │
    │  🟠 第三章8条：新增赔偿上限50% → 需要协商       │
    │  🟢 第七章2条：调整通知期限30→15天 → 可接受      │
    │  📝 谈判话术已生成，飞书摘要已就绪               │
    └─────────────────────────────────────────────┘
```

**Moonshot Legal 内部工具** · 纯 Python · 零外部依赖 · 集成 Kimi CLI

---

## 它解决什么问题

你是乙方法务。甲方把你的模版合同改了一遍发回来。

**以前**：打开 Word → 肉眼逐条扫修订 → 手动整理修改点 → 写审阅意见 → 发飞书给同事 → 耗时 2 小时

**现在**：
```
> 法宝
# 拖入 .docx 文件，等 3 秒
```
完事。

---

## 核心能力

| 能力 | 说明 |
|:---|:---|
| 📄 **修订解析** | 解析 Word 原生 track changes（`w:ins`/`w:del`），不丢一处 |
| 🔢 **智能编号** | `NumberingResolver` 解析 `word/numbering.xml`，自动还原 `第一章`、`1、`、`（一）`、`Article 1` 等编号，匹配 Word 视觉呈现 |
| 🏗️ **条款树构建** | 三级标题检测（Word 样式 → 编号启发式 → 粗体回退），单调栈任意深度嵌套 |
| 🚦 **风险分级** | 🔴 强烈反对 · 🟠 需协商 · 🟡 关注 · 🟢 可接受 |
| 🎯 **精确定位** | 每处修订精确到 `第四章 > 3、 数据使用限制`，不再"大概在第几页" |
| ✍️ **反向写入** | 审阅完毕可自动生成 Word track changes + 批注，直接回传给甲方 |
| 💬 **飞书摘要** | 一键输出结构化摘要，发飞书让同事二次核对 |

---

## 快速开始

### 安装

```bash
git clone git@github.com:skyedolyn-sys/kimi-fabao-Moonshot-Legal.git \
  ~/.claude/skills/kimi-fabao
```

纯 stdlib，**不需要 pip install 任何东西**。

### 使用

在 Kimi CLI 里说：

| 说法 | 效果 |
|:---|:---|
| `法宝` / `kimi法宝` / `审一下修订` | 启动合同修订审阅 |
| `总结修订` / `发飞书` | 生成飞书友好的修订摘要 |
| `执行写入` | 自动生成 Word 修订和批注 |

然后拖入 `.docx` 合同文件即可。

---

## 工作原理

```
 .docx 文件
     │
     ▼
 extract_revisions.py
     ├── 解压 docx (zipfile)
     ├── NumberingResolver: 解析 word/numbering.xml
     │   └── numFmt: decimal / chineseCountingThousand / lowerLetter / lowerRoman ...
     │   └── 跳过整段删除的修订，匹配 Word Final 视图编号
     ├── 三级标题检测
     │   ├── ① Word heading styles (outline_level)
     │   ├── ② 编号启发式 (第X章/第X条/一、/1、/X.X/Article X/附件X)
     │   └── ③ 粗体回退 (仅当无任何编号时)
     ├── build_clause_tree: 单调栈，任意深度
     ├── _separate_appendices: 附件自动分离
     └── 输出: paragraphs[] + clauses[] + appendices[] + revisions[]
            │
            ▼
      analyze_revisions.py
            ├── ClauseClassifier: 条款类型识别
            ├── RiskAssessor: 规则引擎风险分级
            ├── RevisionClusterer: 主题聚类
            └── 输出 JSON → LLM 消费
                   │
                   ▼
              LLM 审阅层
              ├── 逐条分析 + 谈判话术
              ├── 飞书摘要生成
              └── (可选) write/ 反向写入 Word
```

---

## 编号识别：为什么需要 NumberingResolver

Word 有个"坑"：你在文档里看到的 `第一章`、`1、`、`（一）` 这些编号，**可能根本不在 XML 的文字节点里**。它们藏在 `word/numbering.xml` 的 `w:numPr` 定义中，由 Word 渲染时动态生成。

如果不解析 numbering.xml，你只能看到：
```
❌  服务内容          ← 第一章 去哪了？
❌  服务类别          ← 1、 去哪了？
```

法宝的 `NumberingResolver` 做的事：
```
word/numbering.xml          paragraph XML
 ┌──────────────┐     ┌──────────────────┐
 │ numId=1       │     │ <w:numPr>         │
 │ abstractNum=3 │     │   numId=1, ilvl=0 │
 │ lvlText="第%1章"│ ──▶ │ </w:numPr>        │  ──▶  "第一章 服务内容"
 │ numFmt=chinese │     │ <w:t>服务内容</w:t>│
 └──────────────┘     └──────────────────┘
```

还正确处理了：
- **w:suff**（编号后的 tab/空格分隔符）
- **整段删除**（track changes 删掉的段落不占编号，匹配 Word Final 视图）
- **计数器重置**（子级编号在父级推进时归零）

---

## 项目结构

```
kimi-fabao/
├── SKILL.md                      # Skill 定义（Kimi CLI 读取）
├── README.md                     # ← 你在这里
├── kimi-fabao                    # 入口脚本
├── scripts/
│   ├── extract_revisions.py      # 修订提取 + NumberingResolver + 标题检测
│   ├── analyze_revisions.py      # 风险分析 + 条款分类 + 聚类
│   ├── expand_risk_rules.py      # 风险规则扩充脚本（生成 risk_rules.json v2）
│   └── write/                    # 反向写入 Word 修订
│       ├── write_plan_generator.py
│       ├── execute_revisions.py
│       └── validators.py         # 写入计划校验 + 文档匹配校验
├── rules/
│   ├── clause_patterns.json      # 条款类型匹配规则
│   ├── risk_rules.json           # 风险分级规则
│   ├── write_actions.json        # 写入动作模板
│   └── playbooks/nda/            # NDA 专用 Playbook
├── lib/
│   ├── docx_operator.py          # DOCX 底层操作
│   ├── revision_builder.py       # 修订构建器
│   └── comment_injector.py       # 批注注入器
└── evals/
    └── evals.json                # Skill 评估用例
```

---

## 已验证的合同类型

| 合同 | 语言 | 编号方式 | 结构 | 修订 |
|:---|:---|:---|:---|:---|
| Kimi 大模型技术服务协议 | 中文 | `w:numPr`（第X章/N、/（N）） | 7章 + 1附件 | 68处 ✅ |
| Enterprise Service Agreement | 英文 | 内联 `X.X` + Article X | 15 Article | 177处 ✅ |
| NDA 保密协议 | 中/英 | 混合 | — | — ✅ |

---

## 团队协作

```bash
# 维护者：更新规则后推送
cd ~/.claude/skills/kimi-fabao
git add . && git commit -m "update: 调整赔偿上限规则" && git push

# 团队成员：同步最新
cd ~/.claude/skills/kimi-fabao && git pull
```

---

## 安全与合规

🔒 **私有仓库** — 仅限授权人员访问  
🚫 **禁止开源** — 包含内部法律审阅策略，严禁对外分享  
📋 **使用范围** — Moonshot / 月之暗面 / 揽月星辰 / Kimi 及关联实体  
⚖️ **免责声明** — 分析仅供参考，不构成法律意见，重大决策应咨询执业律师

---

<p align="center"><sub>Built with ❤️ by Moonshot Legal · Powered by Kimi CLI + pure Python stdlib</sub></p>
