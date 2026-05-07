#!/usr/bin/env python3
"""
规则库扩充脚本：基于实战Bad Case，大幅扩展risk_rules.json。
核心策略：
  1. 保留原有18条精确规则（依赖clause_type正确分类）
  2. 为每个核心风险模式新增「通用版」规则（applies_to_clause_types: []，兜底）
  3. 新增实战中发现的盲区规则（违约金、抵扣权、模型训练、单方核定等）
"""

import json
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# 原有18条规则（保留不变，在clause_type正确时生效）
# ──────────────────────────────────────────────────────────────
LEGACY_RULES = [
    {
      "id": "rule_liability_001",
      "name": "取消责任上限",
      "applies_to_clause_types": ["违约责任"],
      "applies_to_revision_types": ["deletion", "insertion"],
      "patterns": {
        "deletion": ["不超过", "上限", "最高", "限额", "责任上限", "赔偿上限", "责任限制"],
        "insertion": ["全部损失", "所有损失", "间接损失", "预期利益", "利润损失", "无上限", "无限额"]
      },
      "risk_level": "high",
      "rationale": "取消责任上限或引入间接损失赔偿，显著扩大乙方赔偿责任范围"
    },
    {
      "id": "rule_liability_002",
      "name": "无过错责任",
      "applies_to_clause_types": ["违约责任"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["无论是否违约", "无论过错", "无过错", "严格责任", "绝对责任"]
      },
      "risk_level": "high",
      "rationale": "引入无过错赔偿责任，乙方需为不可控因素承担责任"
    },
    {
      "id": "rule_ip_001",
      "name": "知识产权完全转让",
      "applies_to_clause_types": ["知识产权"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["归甲方所有", "转让给甲方", "甲方享有", "甲方拥有", "全部知识产权", "一切知识产权"]
      },
      "risk_level": "high",
      "rationale": "将所有交付物知识产权完全转让给甲方，乙方丧失后续使用权"
    },
    {
      "id": "rule_ip_002",
      "name": "背景IP转让",
      "applies_to_clause_types": ["知识产权"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["背景知识产权", "背景IP", "已有知识产权", "现有技术", " pre-existing", "背景技术"]
      },
      "risk_level": "high",
      "rationale": "要求转让乙方已有背景知识产权，超出合理范围"
    },
    {
      "id": "rule_data_001",
      "name": "承担所有第三方索赔",
      "applies_to_clause_types": ["数据安全"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["所有第三方索赔", "全部第三方索赔", "任何第三方索赔", "第三方的一切索赔", "承担.*第三方"]
      },
      "risk_level": "high",
      "rationale": "要求乙方承担数据泄露导致的所有第三方索赔，责任不可控"
    },
    {
      "id": "rule_data_002",
      "name": "数据安全义务过重",
      "applies_to_clause_types": ["数据安全"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["等保三级", "等保3级", "ISO27001", "SOC2", "数据本地化", "境内存储", "不得出境"]
      },
      "risk_level": "medium",
      "rationale": "引入超出行业标准的数据安全合规要求，增加运营成本"
    },
    {
      "id": "rule_service_001",
      "name": "开放式服务范围",
      "applies_to_clause_types": ["服务定义"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["包括但不限于", "所有相关", "所有合理", "任何需求", "一切需求", "满足甲方所有", "甲方提出的所有"]
      },
      "risk_level": "medium",
      "rationale": "开放式表述导致服务范围不可量化，可能无限扩大乙方义务"
    },
    {
      "id": "rule_service_002",
      "name": "单方检查权",
      "applies_to_clause_types": ["服务定义"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["随时检查", "随时审计", "单方检查", "单方审计", "甲方有权检查", "甲方有权审计", "无通知检查"]
      },
      "risk_level": "medium",
      "rationale": "赋予甲方无限制的检查/审计权，可能干扰乙方正常运营"
    },
    {
      "id": "rule_payment_001",
      "name": "付款账期延长",
      "applies_to_clause_types": ["费用与支付"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["90日", "90天", "120日", "120天", "6个月", "180天"]
      },
      "risk_level": "medium",
      "rationale": "付款账期过长，影响乙方现金流"
    },
    {
      "id": "rule_payment_002",
      "name": "单方调价权",
      "applies_to_clause_types": ["费用与支付"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["甲方有权调整", "甲方可调整", "单方调整", "单方调价", "甲方决定价格"]
      },
      "risk_level": "high",
      "rationale": "赋予甲方单方调价权，乙方收入不确定性大幅增加"
    },
    {
      "id": "rule_term_001",
      "name": "自动续约",
      "applies_to_clause_types": ["期限与终止"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["自动续期", "自动续约", "自动延长", "自动续签", "除非提前通知"]
      },
      "risk_level": "medium",
      "rationale": "自动续约条款可能导致乙方被动陷入不利合同关系"
    },
    {
      "id": "rule_term_002",
      "name": "甲方单方终止权扩大",
      "applies_to_clause_types": ["期限与终止"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["甲方有权随时终止", "甲方有权单方终止", "甲方可随时解除", "无需理由终止", "任意解除"]
      },
      "risk_level": "high",
      "rationale": "甲方可无理由单方终止，乙方投入无法回收"
    },
    {
      "id": "rule_term_003",
      "name": "竞业限制",
      "applies_to_clause_types": ["期限与终止"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["竞业禁止", "竞业限制", "不得与.*竞争", "不得为.*提供服务", "排他性"]
      },
      "risk_level": "medium",
      "rationale": "竞业限制条款限制乙方与其他客户合作"
    },
    {
      "id": "rule_jurisdiction_001",
      "name": "甲方所在地管辖",
      "applies_to_clause_types": ["其他"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["甲方所在地", "甲方住所地", "甲方注册地", "原告所在地"]
      },
      "risk_level": "medium",
      "rationale": "争议解决地点对乙方不利，增加诉讼成本"
    },
    {
      "id": "rule_service_003",
      "name": "免费义务",
      "applies_to_clause_types": ["服务定义", "费用与支付"],
      "applies_to_revision_types": ["insertion"],
      "patterns": {
        "insertion": ["免费提供", "无偿提供", "免费培训", "免费支持", "不另行收费"]
      },
      "risk_level": "medium",
      "rationale": "要求乙方免费提供额外服务，增加成本"
    },
    {
      "id": "rule_template_001",
      "name": "无限赔偿责任（模板）",
      "applies_to_clause_types": ["违约责任"],
      "applies_to_revision_types": ["existing"],
      "applies_to_modes": ["template"],
      "patterns": {
        "existing": ["无上限", "无限额", "全部损失", "所有损失", "间接损失", "利润损失", "预期利益"]
      },
      "risk_level": "high",
      "rationale": "模板中存在无限赔偿责任条款，对乙方极为不利，建议增加责任上限"
    },
    {
      "id": "rule_template_002",
      "name": "单方任意解除权（模板）",
      "applies_to_clause_types": ["期限与终止"],
      "applies_to_revision_types": ["existing"],
      "applies_to_modes": ["template"],
      "patterns": {
        "existing": ["有权随时终止", "有权单方终止", "可随时解除", "无需理由", "任意解除", "任意终止"]
      },
      "risk_level": "high",
      "rationale": "甲方享有任意解除权而乙方无对等权利，权利义务严重失衡"
    },
    {
      "id": "rule_template_003",
      "name": "宽泛定义条款（模板）",
      "applies_to_clause_types": ["服务定义", "数据安全"],
      "applies_to_revision_types": ["existing"],
      "applies_to_modes": ["template"],
      "patterns": {
        "existing": ["包括但不限于", "一切", "所有", "任何", "全部", "凡是由乙方", "凡与乙方有关"]
      },
      "risk_level": "medium",
      "rationale": "模板中存在开放式定义条款，可能导致义务范围不可量化"
    },
    {
      "id": "rule_template_004",
      "name": "无责任上限保护（模板）",
      "applies_to_clause_types": ["违约责任"],
      "applies_to_revision_types": ["existing"],
      "applies_to_modes": ["template"],
      "patterns": {
        "existing_regex": ["责任.*不.*限制", "赔偿.*不.*上限", "不设.*上限", "不设.*限额"]
      },
      "risk_level": "high",
      "rationale": "违约责任条款中明确排除责任限制，乙方风险敞口无限"
    },
]


# ──────────────────────────────────────────────────────────────
# 通用版 High-risk 规则（applies_to_clause_types: []，兜底）
# ──────────────────────────────────────────────────────────────
GEN_HIGH_RULES = [
    {
        "id": "gen_high_001",
        "name": "【通用】知识产权归甲方",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["归甲方所有", "归甲方", "转让给甲方", "甲方享有所有权", "甲方拥有所有权", "一切知识产权归", "全部知识产权归"],
            "existing": ["归甲方所有", "归甲方", "转让给甲方", "甲方享有所有权"]
        },
        "risk_level": "high",
        "rationale": "知识产权归属甲方，乙方丧失后续使用权和复用权"
    },
    {
        "id": "gen_high_002",
        "name": "【通用】责任上限被取消",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "deletion", "existing"],
        "patterns": {
            "insertion": ["无上限", "无限额", "不设上限", "不设限额", "不承担责任上限", "不限制责任", "赔偿不受限制"],
            "deletion": ["责任上限", "赔偿上限", "责任限额", "最高赔偿", "不超过"],
            "existing": ["无上限", "无限额", "不设上限"]
        },
        "risk_level": "high",
        "rationale": "责任上限被取消或从未设置，乙方赔偿风险敞口无限"
    },
    {
        "id": "gen_high_003",
        "name": "【通用】无过错/严格责任",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["无论是否违约", "无论过错", "无过错责任", "严格责任", "绝对责任", "即使无过错"],
            "existing": ["无论是否违约", "无过错责任", "严格责任"]
        },
        "risk_level": "high",
        "rationale": "引入无过错赔偿责任，乙方需为不可控因素承担责任"
    },
    {
        "id": "gen_high_004",
        "name": "【通用】甲方单方任意终止",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["有权随时终止", "有权单方终止", "无需理由终止", "无需理由解除", "任意解除", "任意终止", "甲方可随时"],
            "existing": ["有权随时终止", "任意解除", "无需理由终止"]
        },
        "risk_level": "high",
        "rationale": "甲方可无理由单方终止，乙方投入无法回收"
    },
    {
        "id": "gen_high_005",
        "name": "【通用】违约金过高或固定金额",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["100万", "1000万", "每次违约", "per breach", "最低赔偿", "固定违约金", "不低于.*万", "十倍", "10倍", "按日.*千分之"],
            "existing": ["100万", "每次违约", "最低赔偿", "固定违约金", "十倍"]
        },
        "risk_level": "high",
        "rationale": "设定过高固定违约金或触发标准过低，轻微违约可能承担过重责任"
    },
    {
        "id": "gen_high_006",
        "name": "【通用】解除合同后全额返还",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["返还全部", "退还全部", "返还已收", "退还已收", "返还所有", "退还所有", "解除合同.*返还", "终止.*返还全部"],
            "existing": ["返还全部已付款", "退还全部已付款", "解除合同.*返还"]
        },
        "risk_level": "high",
        "rationale": "解除合同后需返还全部已收款项，实质上否定全部合同履行价值"
    },
    {
        "id": "gen_high_007",
        "name": "【通用】甲方自行抵扣权",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["直接扣除", "自行抵扣", "从应付款中扣除", "直接抵销", "有权抵扣", "从应付账款中扣除"],
            "existing": ["直接扣除", "自行抵扣", "从应付款中扣除"]
        },
        "risk_level": "high",
        "rationale": "甲方可直接从应付款中扣除违约金及损失，无需争议解决前置"
    },
    {
        "id": "gen_high_008",
        "name": "【通用】承担全部第三方索赔",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["所有第三方索赔", "全部第三方索赔", "任何第三方索赔", "第三方的一切索赔", "承担.*第三方.*损失", "承担.*第三方.*索赔"],
            "existing": ["所有第三方索赔", "任何第三方索赔"]
        },
        "risk_level": "high",
        "rationale": "要求乙方承担数据泄露或违约导致的所有第三方索赔，责任不可控"
    },
    {
        "id": "gen_high_009",
        "name": "【通用】永久或无限期义务",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["永久", "perpetual", "无限期", "永远", "始终", "indefinite", "perpetuity", "永不失效"],
            "existing": ["永久", "perpetual", "无限期"]
        },
        "risk_level": "high",
        "rationale": "永久或无限期义务超出合理范围，对乙方形成长期不可控风险"
    },
    {
        "id": "gen_high_010",
        "name": "【通用】甲方单方调价/核定",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["甲方有权调整", "甲方有权核定", "甲方决定", "以甲方认定为准", "以甲方确认.*为准", "甲方有权重新核定", "甲方单方确认"],
            "existing": ["甲方有权调整", "甲方决定价格", "以甲方认定为准"]
        },
        "risk_level": "high",
        "rationale": "赋予甲方单方调价或核定权，乙方收入/成本不确定性大幅增加"
    },
    {
        "id": "gen_high_011",
        "name": "【通用】连带责任或担保扩大",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["连带责任", "共同责任", "保证责任", "担保责任", "连带赔偿", "共同赔偿"],
            "existing": ["连带责任", "保证责任", "担保责任"]
        },
        "risk_level": "high",
        "rationale": "引入连带责任或担保义务，乙方面临超出自身过错范围的赔偿风险"
    },
    {
        "id": "gen_high_012",
        "name": "【通用】禁止模型训练或AI使用",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不得用于训练", "不得.*模型训练", "禁止.*人工智能", "不得用于.*AI", "不得.*机器学习", "禁止.*模型改进"],
            "existing": ["不得用于训练", "禁止模型训练"]
        },
        "risk_level": "high",
        "rationale": "禁止将数据/内容用于模型训练，对AI公司构成核心业务能力限制"
    },
    {
        "id": "gen_high_013",
        "name": "【通用】数据所有权归甲方",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["数据.*归甲方", "数据所有权.*甲方", "数据.*甲方所有", "数据归披露方", "数据所有权归"],
            "existing": ["数据.*归甲方", "数据所有权.*甲方"]
        },
        "risk_level": "high",
        "rationale": "数据所有权完全归甲方，乙方可能丧失对自身生成数据或分析成果的权利"
    },
    {
        "id": "gen_high_014",
        "name": "【通用】背景IP/已有技术转让",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["背景知识产权", "背景IP", "已有知识产权", "现有技术", "pre-existing", "背景技术", "preexisting"],
            "existing": ["背景知识产权", "背景IP"]
        },
        "risk_level": "high",
        "rationale": "要求转让乙方已有背景知识产权或现有技术，超出合理范围"
    },
    {
        "id": "gen_high_015",
        "name": "【通用】触发标准过低",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["合理理由怀疑", "有理由认为", "视为违约", "即构成违约", "即视为", "一经发现", "一经核实"],
            "existing": ["合理理由怀疑", "视为违约", "一经发现"]
        },
        "risk_level": "high",
        "rationale": "违约触发标准过低或主观性过强，乙方极易被认定为违约"
    },
    {
        "id": "gen_high_016",
        "name": "【通用】IP归属例外+定义缺失",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion_regex": ["除.*外.*归.*所有", "除.*另行约定.*外.*归"],
            "existing_regex": ["除.*外.*归.*所有", "除.*另行约定.*外.*归"]
        },
        "risk_level": "high",
        "rationale": "知识产权归属附加例外条件，若例外条件中的术语未定义，可能导致IP实际转移"
    },
    {
        "id": "gen_high_017",
        "name": "【通用】惩罚性赔偿",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["惩罚性赔偿", "punitive damages", "加倍赔偿", "多倍赔偿"],
            "existing": ["惩罚性赔偿", "punitive damages"]
        },
        "risk_level": "high",
        "rationale": "引入惩罚性赔偿，远超实际损失，对乙方极为不利"
    },
    {
        "id": "gen_high_018",
        "name": "【通用】单方解约+利息",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["返还.*利息", "退还.*利息", "支付.*利息", "按.*利率计算", "同期贷款利率"],
            "existing": ["返还.*利息", "按.*利率"]
        },
        "risk_level": "high",
        "rationale": "解除合同后除返还款项外还需支付利息，进一步加重乙方负担"
    },
]


# ──────────────────────────────────────────────────────────────
# 通用版 Medium-risk 规则（applies_to_clause_types: []，兜底）
# ──────────────────────────────────────────────────────────────
GEN_MED_RULES = [
    {
        "id": "gen_med_001",
        "name": "【通用】开放式范围表述",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["包括但不限于", "所有相关", "所有合理", "任何需求", "一切需求", "满足甲方所有", "甲方提出的所有", "凡是由乙方", "凡与乙方有关"],
            "existing": ["包括但不限于", "一切", "所有", "任何", "全部"]
        },
        "risk_level": "medium",
        "rationale": "开放式表述导致义务范围不可量化，可能无限扩大乙方责任"
    },
    {
        "id": "gen_med_002",
        "name": "【通用】检查/审计/查阅权",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["有权检查", "有权审计", "有权查阅", "有权要求提供", "有权查看", "有权审查", "有权核验"],
            "existing": ["有权检查", "有权审计", "有权查阅"]
        },
        "risk_level": "medium",
        "rationale": "赋予甲方检查/审计/查阅权，如无频率和提前通知限制，可能干扰正常运营"
    },
    {
        "id": "gen_med_003",
        "name": "【通用】付款账期延长",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["90日", "90天", "120日", "120天", "180天", "6个月", "六十日", "六十天"],
            "existing": ["90日", "90天", "120日", "120天", "180天"]
        },
        "risk_level": "medium",
        "rationale": "付款账期过长，影响乙方现金流"
    },
    {
        "id": "gen_med_004",
        "name": "【通用】自动续约条款",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["自动续期", "自动续约", "自动延长", "自动续签", "除非提前通知", "到期自动延续"],
            "existing": ["自动续期", "自动续约", "自动延长"]
        },
        "risk_level": "medium",
        "rationale": "自动续约条款可能导致乙方被动陷入不利合同关系"
    },
    {
        "id": "gen_med_005",
        "name": "【通用】竞业限制或排他性",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["竞业禁止", "竞业限制", "排他性", "独家", "exclusivity", "不得与.*竞争", "不得为.*提供服务", "不得接受.*委托"],
            "existing": ["竞业禁止", "竞业限制", "排他性", "独家"]
        },
        "risk_level": "medium",
        "rationale": "竞业限制或排他性条款限制乙方与其他客户合作"
    },
    {
        "id": "gen_med_006",
        "name": "【通用】免费或无偿义务",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["免费提供", "无偿提供", "免费培训", "免费支持", "不另行收费", "无需支付.*费用", "义务提供"],
            "existing": ["免费提供", "无偿提供", "不另行收费"]
        },
        "risk_level": "medium",
        "rationale": "要求乙方免费提供额外服务或承担额外成本"
    },
    {
        "id": "gen_med_007",
        "name": "【通用】数据安全合规要求过高",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["等保三级", "等保3级", "ISO27001", "SOC2", "SOC 2", "数据本地化", "境内存储", "不得出境", "跨境传输.*禁止"],
            "existing": ["等保三级", "ISO27001", "SOC2", "数据本地化"]
        },
        "risk_level": "medium",
        "rationale": "引入超出行业标准的数据安全合规要求，增加运营成本"
    },
    {
        "id": "gen_med_008",
        "name": "【通用】争议管辖地对乙方不利",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["甲方所在地", "甲方住所地", "甲方注册地", "原告所在地", "被告所在地", "对方所在地"],
            "existing": ["甲方所在地", "甲方住所地", "甲方注册地"]
        },
        "risk_level": "medium",
        "rationale": "争议解决地点在对方所在地，增加应诉成本"
    },
    {
        "id": "gen_med_009",
        "name": "【通用】聘用/招聘限制",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不得聘用", "不得雇佣", "不得招聘", "不得挖角", "不得招揽", "non-solicit", "不得通过猎头", "不得录用"],
            "existing": ["不得聘用", "不得招聘", "non-solicit"]
        },
        "risk_level": "medium",
        "rationale": "限制乙方正常招聘权利，可能因缺乏对价而被认定无效但仍增加谈判成本"
    },
    {
        "id": "gen_med_010",
        "name": "【通用】配合义务扩大",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["无条件配合", "全力配合", "积极配合", "不得拒绝配合", "必须配合", "及时配合"],
            "existing": ["无条件配合", "全力配合", "积极配合"]
        },
        "risk_level": "medium",
        "rationale": "配合义务标准模糊或过于严苛，可能导致乙方资源被占用"
    },
    {
        "id": "gen_med_011",
        "name": "【通用】声誉保护/言论限制",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["有损声誉", "负面言论", "声誉损害", "不利影响", "有损形象", "贬低", "诋毁"],
            "existing": ["有损声誉", "负面言论", "声誉损害"]
        },
        "risk_level": "medium",
        "rationale": "声誉保护标准主观，可能限制乙方正当言论和商业评价"
    },
    {
        "id": "gen_med_012",
        "name": "【通用】保证与陈述条款",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["保证", "陈述", "warranty", "representation", "有权签署", "有权签订", "有权披露", "保证.*真实"],
            "existing": ["保证", "陈述", "warranty", "representation"]
        },
        "risk_level": "medium",
        "rationale": "增加乙方的陈述与保证义务，扩大违约风险面"
    },
    {
        "id": "gen_med_013",
        "name": "【通用】保密/安全标准过高",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["最高标准", "绝对安全", "军事级", "银行级安全", "零容忍", "不得有任何泄露", "零泄露"],
            "existing": ["最高标准", "绝对安全", "军事级", "银行级安全"]
        },
        "risk_level": "medium",
        "rationale": "要求超出行业标准的保密或安全措施，实际难以达成"
    },
    {
        "id": "gen_med_014",
        "name": "【通用】数据/信息删除义务",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["立即删除", "永久删除", "彻底删除", "不得保留", "销毁所有", "删除所有副本"],
            "existing": ["立即删除", "永久删除", "彻底删除"]
        },
        "risk_level": "medium",
        "rationale": "删除义务过重，未考虑法律保留和备份需求"
    },
    {
        "id": "gen_med_015",
        "name": "【通用】关联方/相关方定义过宽",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["关联方", "关联人士", "实际控制人", "最终受益人", "股东", "子公司", "关联企业", "affiliate"],
            "existing": ["关联方", "关联人士", "实际控制人", "最终受益人"]
        },
        "risk_level": "medium",
        "rationale": "关联方定义过宽，可能导致乙方对无法控制的主体承担责任"
    },
    {
        "id": "gen_med_016",
        "name": "【通用】保证金/押金/保函要求",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["保证金", "押金", "履约保函", "质保金", "预付款保证金", "银行保函"],
            "existing": ["保证金", "押金", "履约保函", "质保金"]
        },
        "risk_level": "medium",
        "rationale": "要求乙方提供保证金或保函，占用资金并增加交易成本"
    },
    {
        "id": "gen_med_017",
        "name": "【通用】付款条件恶化",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["验收合格后付款", "确认无误后", "书面确认后付款", "经甲方书面确认", "经甲方验收合格"],
            "existing": ["验收合格后付款", "确认无误后", "经甲方书面确认"]
        },
        "risk_level": "medium",
        "rationale": "付款条件附加甲方单方确认要求，可能导致付款被拖延"
    },
    {
        "id": "gen_med_018",
        "name": "【通用】责任上限排除特定情形",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["故意违约", "重大过失", "保密义务", "知识产权"],
            "existing": ["故意违约.*除外", "重大过失.*除外", "保密义务.*除外"]
        },
        "risk_level": "medium",
        "rationale": "责任上限排除特定情形（如故意违约、重大过失），使上限保护大幅缩水"
    },
    {
        "id": "gen_med_019",
        "name": "【通用】保密期限过长",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["10年", "15年", "二十年", "20年", "十年", "十五年"],
            "existing": ["10年", "15年", "二十年", "20年"]
        },
        "risk_level": "medium",
        "rationale": "保密期限超过行业惯例（通常3-5年），建议协商缩短"
    },
    {
        "id": "gen_med_020",
        "name": "【通用】转委托/分包限制",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不得分包", "不得转包", "不得转委托", "未经同意.*分包", "未经同意.*转包", "禁止分包"],
            "existing": ["不得分包", "不得转包", "不得转委托"]
        },
        "risk_level": "medium",
        "rationale": "禁止转委托或分包，限制乙方灵活调配资源的能力"
    },
    {
        "id": "gen_med_021",
        "name": "【通用】通知义务过重",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["立即通知", "24小时内通知", "48小时内通知", "书面通知", "毫不迟延地通知"],
            "existing": ["立即通知", "24小时内通知", "48小时内通知"]
        },
        "risk_level": "medium",
        "rationale": "通知时限过短或形式要求过高，实际履行困难"
    },
    {
        "id": "gen_med_022",
        "name": "【通用】赔偿范围扩大",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["间接损失", "预期利益", "利润损失", "可得利益", "机会成本", "商誉损失", "所有损失", "全部损失"],
            "existing": ["间接损失", "预期利益", "利润损失", "可得利益"]
        },
        "risk_level": "medium",
        "rationale": "赔偿范围扩大至间接损失、预期利益等，增加乙方潜在赔偿额"
    },
    {
        "id": "gen_med_023",
        "name": "【通用】溯及既往义务",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["追溯至", "溯及", "合同签订前", "签署日前", "生效日前", "适用于.*之前"],
            "existing": ["追溯至", "溯及", "合同签订前"]
        },
        "risk_level": "medium",
        "rationale": "义务溯及合同签订前，乙方无法控制的历史行为可能被追责"
    },
    {
        "id": "gen_med_024",
        "name": "【通用】禁止反向工程",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不得反向工程", "no reverse engineering", "不得反编译", "no decompilation", "不得反汇编", "no disassembly"],
            "existing": ["不得反向工程", "不得反编译", "不得反汇编"]
        },
        "risk_level": "medium",
        "rationale": "反向工程限制可能超出保密协议合理范围，影响乙方技术自主"
    },
    {
        "id": "gen_med_025",
        "name": "【通用】知识产权保证",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不侵犯", "不侵害", "无权利瑕疵", "权利完整", "有权使用", "有权许可", "不冲突"],
            "existing": ["不侵犯", "不侵害", "无权利瑕疵", "权利完整"]
        },
        "risk_level": "medium",
        "rationale": "知识产权保证条款增加乙方审查和担保义务，扩大风险面"
    },
    {
        "id": "gen_med_026",
        "name": "【通用】数据出境/本地化限制",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不得出境", "不得跨境传输", "数据本地化", "境内存储", "本地化部署"],
            "existing": ["不得出境", "不得跨境传输", "数据本地化", "境内存储"]
        },
        "risk_level": "medium",
        "rationale": "数据出境限制或本地化要求可能影响乙方全球化技术架构"
    },
]


# ──────────────────────────────────────────────────────────────
# 通用版 Low-risk 规则（减少unknown数量）
# ──────────────────────────────────────────────────────────────
GEN_LOW_RULES = [
    {
        "id": "gen_low_001",
        "name": "【通用】乙方免责条款",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["不视为违约", "不承担.*责任", "免除.*责任", "不构成违约", "不承担责任"],
            "existing": ["不视为违约", "不承担.*责任", "免除.*责任"]
        },
        "risk_level": "low",
        "rationale": "为乙方增设免责情形，通常对乙方有利或中性，可直接接受"
    },
    {
        "id": "gen_low_002",
        "name": "【通用】定义条款细化",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "existing"],
        "patterns": {
            "insertion": ["指：", "定义为", "以下称", "以下简称", "系指", "是指"],
            "existing": ["指：", "定义为", "以下称", "以下简称"]
        },
        "risk_level": "low",
        "rationale": "术语定义细化或新增，通常为中性修订，有助于明确范围"
    },
    {
        "id": "gen_low_003",
        "name": "【通用】联系方式/地址更新",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "deletion"],
        "patterns": {
            "insertion_regex": ["^(地址|电话|邮箱|联系人|传真|网址)"],
            "deletion_regex": ["^(地址|电话|邮箱|联系人|传真|网址)"]
        },
        "risk_level": "low",
        "rationale": "联系方式、地址等信息的更新，通常无实质风险"
    },
    {
        "id": "gen_low_004",
        "name": "【通用】签署信息更新",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "deletion"],
        "patterns": {
            "insertion_regex": ["^(签署日期|签订日期|日期：|Date:)"],
            "deletion_regex": ["^(签署日期|签订日期|日期：|Date:)"]
        },
        "risk_level": "low",
        "rationale": "签署日期等程序性信息的更新，通常无实质风险（但需核查逻辑一致性）"
    },
    {
        "id": "gen_low_005",
        "name": "【通用】纯格式/标点调整",
        "applies_to_clause_types": [],
        "applies_to_revision_types": ["insertion", "deletion"],
        "patterns": {
            "insertion_regex": ["^[、，。；：！？\"\"''（）【】《》]$"],
            "deletion_regex": ["^[、，。；：！？\"\"''（）【】《》]$"]
        },
        "risk_level": "low",
        "rationale": "纯标点、格式调整，无实质影响"
    },
]


def main():
    rules_dir = Path(__file__).resolve().parent.parent / "rules"
    output_path = rules_dir / "risk_rules.json"

    all_rules = (
        LEGACY_RULES
        + GEN_HIGH_RULES
        + GEN_MED_RULES
        + GEN_LOW_RULES
    )

    data = {
        "version": "2.0.0",
        "description": "Expanded risk assessment rules (v2). Strategy: keep legacy precise rules + add generic catch-all rules with applies_to_clause_types: [] to handle clause classification failures.",
        "risk_levels": {
            "high": {"label": "强烈反对", "emoji": "🔴", "description": "对乙方有重大不利影响，必须要求修改"},
            "medium": {"label": "需协商", "emoji": "🟠", "description": "对乙方有一定影响，建议争取更有利条件"},
            "low": {"label": "可接受", "emoji": "🟢", "description": "对乙方影响较小或有利，可直接接受"},
        },
        "rules": all_rules,
        "scoring": {
            "multiple_matches": "take_highest",
            "no_match_default": "low",
            "confidence_threshold": {
                "high": 0.8,
                "medium": 0.5,
                "low": 0.0
            }
        },
        "stats": {
            "total_rules": len(all_rules),
            "legacy_rules": len(LEGACY_RULES),
            "generic_high": len(GEN_HIGH_RULES),
            "generic_medium": len(GEN_MED_RULES),
            "generic_low": len(GEN_LOW_RULES),
        }
    }

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written {len(all_rules)} rules to {output_path}")
    print(f"  Legacy (precise): {len(LEGACY_RULES)}")
    print(f"  Generic high:     {len(GEN_HIGH_RULES)}")
    print(f"  Generic medium:   {len(GEN_MED_RULES)}")
    print(f"  Generic low:      {len(GEN_LOW_RULES)}")


if __name__ == "__main__":
    main()
