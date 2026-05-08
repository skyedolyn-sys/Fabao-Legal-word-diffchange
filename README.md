# 🔒 Kimi法宝 — 乙方视角合同修订审阅

> **INTERNAL USE ONLY — Moonshot Legal Team**  
> ⚠️ 本工具为月之暗面法务团队内部开发，仅供内部使用，**严禁开源或对外分享**。

---

## 简介

**Kimi法宝** 是面向服务提供方（乙方）视角的合同修订智能审阅工具，集成于 Claude Code / Kimi CLI，帮助法务/商务人员快速识别甲方在合同修订中埋设的风险条款，评估接受度并给出修改建议。

**适用场景：**
- 技术/服务类合同（SaaS、AI、云计算、技术服务）的修订审阅
- 保密协议（NDA）的修订审阅
- 对方模板合同（clean 版本）的初筛
- 审阅后生成修订摘要，发飞书给同事二次核对

**核心能力：**
- 📄 解析 Word 原生修订标记（track changes）
- 🔍 按条款定位并聚合修订内容
- 🚦 自动风险分级（🔴强烈反对 / 🟠需协商 / 🟢可接受）
- 📝 可选：基于审阅结论自动生成 Word 修订和批注
- 💬 生成飞书友好的修订摘要文本

---

## 快速开始

### 1. 安装

```bash
# 克隆到 Claude Code skills 目录
git clone https://github.com/skyedolyn-sys/kimi-fabao-Moonshot-Legal.git ~/.claude/skills/kimi-fabao

# 安装 Python 依赖（如未安装）
pip install python-docx lxml
```

### 2. 使用

在 Claude Code 中直接说出触发词：

```
法宝
# 或
kimi法宝
# 或
审一下修订
```

然后按提示上传或指定 `.docx` 合同文件即可。

**常用指令：**
| 指令 | 说明 |
|------|------|
| `法宝` | 触发合同修订审阅 |
| `审一下修订` | 同上 |
| `总结修订` | 审阅后生成飞书摘要 |
| `发飞书` | 同上 |
| `执行写入` | 基于审阅结果自动生成 Word 修订 |

---

## 项目结构

```
kimi-fabao/
├── SKILL.md                  # Skill 定义文件（Claude Code 读取）
├── README.md                 # 本文件
├── scripts/
│   ├── analyze_revisions.py      # 核心分析引擎
│   ├── extract_revisions.py      # 修订标记提取
│   └── write/                    # 自动写入修订模块
├── rules/
│   ├── clause_patterns.json      # 条款类型匹配规则
│   ├── risk_rules.json           # 风险分级规则
│   ├── write_actions.json        # 自动写入动作模板
│   └── playbooks/
│       └── nda/                  # NDA 专用 Playbook
├── lib/
│   ├── docx_operator.py          # DOCX 文件操作
│   ├── revision_builder.py       # 修订构建
│   └── comment_injector.py       # 批注注入
└── evals/
    └── evals.json                # Skill 评估用例
```

---

## 规则定制

### 修改风险规则

编辑 `rules/risk_rules.json`，下次运行自动生效，无需重启：

```json
{
  "rules": [
    {
      "id": "your_rule_id",
      "name": "规则名称",
      "applies_to_clause_types": ["liability"],
      "patterns": {
        "insertion": ["关键词1", "关键词2"]
      },
      "risk_level": "high",
      "rationale": "风险说明"
    }
  ]
}
```

### 新增合同类型 Playbook

1. 创建目录：`rules/playbooks/<playbook_id>/`
2. 编写 `clause_patterns.json` 和 `risk_rules.json`
3. 使用时附加 `--playbook <playbook_id>`

---

## 团队更新流程

**维护者更新规则：**
```bash
cd ~/.claude/skills/kimi-fabao
# 修改规则文件...
git add .
git commit -m "update: 调整赔偿上限规则"
git push origin main
```

**团队成员同步：**
```bash
cd ~/.claude/skills/kimi-fabao
git pull origin main
```

---

## 安全与合规

- 🔒 **私有仓库**：本代码存放于 GitHub Private Repository，仅限授权人员访问
- 🚫 **禁止开源**：本工具包含 Moonshot 内部法律审阅策略，**严禁以任何形式开源或对外分享**
- 📋 **使用范围**：仅限 Moonshot / 月之暗面 / 揽月星辰 / Kimi 及其关联实体的法务、商务人员使用
- ⚖️ **免责声明**：本工具提供的分析仅供参考，不构成法律意见。重大合同决策应咨询执业律师

---

## 问题反馈

如有问题或改进建议，请联系 **Moonshot Legal Team** 或在本私有仓库提交 Issue。
