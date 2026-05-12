# extract_revisions.py — Heading 识别引擎改进记录

> 日期: 2026-05-08
> 文件: `scripts/extract_revisions.py`
> 备份: `scripts/extract_revisions.py.bak`
> 测试合同: SHEIN 大模型技术服务协议（DPA 含 EU/Swiss/UK SCC 附录）

---

## 一、问题背景

在审阅 SHEIN 合同时发现两类结构性缺陷：

1. **字母编号漏识别**：`A.`、`(a)`、`(i)`、`(1)` 等英文编号虽被 `num_prefix` 捕获，但 `_guess_heading_level` 未将其映射为 heading，导致 clause tree 中缺失这些节点，location 路径无法精确到子条款（如 `(d) Specific EU SCC Selections`）。

2. **Appendix 嵌套扁平化**：`_separate_appendices` 采用顺序切分（遇到首个 Appendix 后一律归为附件），导致 DPA 内部的 `Appendix 2` 子附录（`B. SWISS SCCs`、`C. UK Transfer Addendum`）被错误提升为文档级顶层附件，`total_appendices` 从正确的 6 膨胀为 10。

---

## 二、改动清单（6 处）

### 改动 1：新增正则定义（L248-252）

```python
_RE_LETTER_UPPER       = re.compile(r'^[A-Z][.．]\s')       # A. B. C.
_RE_LETTER_LOWER_PAREN = re.compile(r'^\([a-z]\)\s')        # (a) (b) (c)
_RE_ROMAN_LOWER_PAREN  = re.compile(r'^\([ivxlcdm]+\)\s')   # (i) (ii) (iii)
_RE_ARABIC_PAREN       = re.compile(r'^\(\d+\)\s')          # (1) (2) (3)
```

**设计决策**：`_RE_ROMAN_LOWER_PAREN` 不使用 `re.IGNORECASE`，避免 `(I)`/`(IV)` 等大写被误匹配。

### 改动 2：`_scan_doc_patterns` 扫描新编号类型（L277-317）

新增 4 个标志位：`has_letter_upper`、`has_letter_lower_paren`、`has_roman_lower_paren`、`has_arabic_paren`，并将它们纳入 `has_any_numbering` 聚合判断。

### 改动 3：新增 `_classify_heading_type` 函数（L321-347）

将 heading 文本分类为类型字符串（`appendix`/`letter_upper`/`letter_lower`/`roman_lower`/`arabic_paren`/...），用于在顺序遍历时维护 `last_heading_type` 上下文。

### 改动 4：`_guess_heading_level` 重构为上下文感知推断（L350-475）

核心改动。新增两个可选参数（向后兼容）：

```python
def _guess_heading_level(
    text, fmt, doc_pats,
    ancestor_type: str | None = None,    # 上一个 heading 的编号类型
    last_heading_fmt: dict | None = None, # 上一个 heading 的格式（用于缩进比较）
) -> int:
```

**层级推断规则**（新增部分）：

| 编号模式 | 祖先上下文 | → heading_level |
|----------|-----------|-----------------|
| `A.` | `appendix` | 2 |
| `A.` | `letter_upper` / 其他子编号 | 2（兄弟） |
| `A.` | 无/其他 | 1 |
| `(a)` | `letter_upper`/`article`/`tiao`/`decimal` | 3 |
| `(a)` | `roman_lower` 且同缩进 | **fall-through 到 roman 分支**（消歧） |
| `(a)` | 其他 | 2 |
| `(i)` | `letter_lower` / `roman_lower` | 4 |
| `(i)` | `letter_upper`/`decimal` | 3 |
| `(1)` | `letter_lower`/`cn_paren`/`arabic_paren` | 4 |
| `(1)` | `letter_upper`/`decimal`/`arabic_ordinal` | 3 |
| `Appendix X` | `appendix`（嵌套） | 2 |
| `Appendix X` | 无（顶级） | 1 |

**罗马/字母消歧逻辑**：`(v)`/`(i)`/`(x)` 等单字符同时匹配 `_RE_LETTER_LOWER_PAREN` 和 `_RE_ROMAN_LOWER_PAREN`。当 `ancestor_type == "roman_lower"` 且缩进相同时，letter 分支主动 fall-through 到 roman 分支，保持序列连续性。

### 改动 5：`_separate_appendices` 改为层级感知切分（L478-494）

```python
# 旧：顺序切分（遇到首个附件后全部归为附件）
in_appendix = False
for clause in clauses:
    if not in_appendix and _RE_APPENDIX.match(title):
        in_appendix = True
    ...

# 新：仅 heading_level==1 且匹配附件正则才切分
for clause in clauses:
    if level == 1 and _RE_APPENDIX.match(title):
        appendices.append(clause)
    else:
        main.append(clause)
```

效果：DPA 内部的 `Appendix 2` 及其子附录保留在 clause tree 中，不被错误扁平化。

### 改动 6：`attach_location_paths` 兜底追加 num_prefix（L795-803）

为非 heading 的 body 段落，如果有 `num_prefix` 且未包含在 location 路径中，追加为最后一级路径。作为防御性措施，当 heading 识别充分时不触发。

### 附带修复：`_int_to_chinese` 越界 Bug（L42-45）

原代码 `n=10` 时 `digits[10]` 越界（`digits` 字符串长度为 10，索引 0-9）。拆分为 `n < 10` 和 `n == 10` 两个分支。

---

## 三、调用处改动（L957-985）

heading heuristic 遍历循环改为**有状态的顺序处理**：

```python
last_heading_type = None
last_heading_fmt: dict = {}
for para in paragraphs:
    # 已识别的 heading → 更新上下文
    if para["heading_level"] > 0:
        last_heading_type = _classify_heading_type(text)
        last_heading_fmt = para.get("fmt", {})
        continue
    # 未识别 → 带上下文推断
    guessed = _guess_heading_level(text, fmt, doc_patterns,
                                    last_heading_type, last_heading_fmt)
    if guessed > 0:
        ...
        last_heading_type = _classify_heading_type(text)
        last_heading_fmt = fmt
```

---

## 四、验证结果

### 定量对比（SHEIN 合同）

| 指标 | 修改前 | 修改后 |
|------|--------|--------|
| `A. EEA SCCs` heading_level | 0 | **2** ✅ |
| `(a)~(g)` heading_level | 0 | **3** ✅ |
| `(i)~(vii)` heading_level | 0 | **4** ✅（含 `(v)` 消歧） |
| `(1)~(3)` heading_level（第五条下） | 0 | **3** ✅ |
| `total_appendices` | 10 | **6** ✅ |
| `total_revisions` | 1010 | 1010 ✅（无丢失） |
| 中文 heading 层级（第X章/1、） | L1/L3 | L1/L3 ✅（无回归） |

### Clause Tree 结构对比

**修改前**：`Appendix 2` 下无子节点，`B. SWISS SCCs` / `C. UK Transfer` 被切为独立顶级附件。

**修改后**：
```
Appendix 2- Completion of EU SCC, Swiss SCC and UK...
  └─ A. EEA SCCs
  │    ├─ (a) Execution and Scope
  │    ├─ (b) Description of Transfers
  │    ├─ (c) Conflict Resolution
  │    ├─ (d) Specific EU SCC Selections
  │    │    ├─ (i) Module 2 applies
  │    │    ├─ (ii) Clause 7 not apply
  │    │    ├─ ...
  │    │    └─ (vii) Clause 18(b) Jurisdiction
  │    ├─ (e) Annex Completion
  │    │    ├─ (i) Annex I
  │    │    ├─ (ii) Annex II
  │    │    └─ (iii) Annex III
  │    ├─ (f) Audit Rights
  │    └─ (g) Onward Transfers
  ├─ B. SWISS SCCs
  │    ├─ (h) Supervisory Authority
  │    ├─ (i) Governing Law
  │    └─ ...
  └─ C. UK International Transfer Addendum
```

### Location 路径示例

```
修改前: "Appendix 2- Completion of EU SCC..."
修改后: "Appendix 2- ... > A. EEA SCCs > (d) Specific EU SCC Selections..."
```

---

## 五、已知局限

1. **`idx=458 (a) Incorporation` 为 L4**：来自 Word 文档 `outline_level=3`，属于文档原始格式问题，heuristic 不覆盖已有 heading 的段落。
2. **Annex 1B/II/III 嵌套在 Annex 1A 下**：从 L1 → L2，因为 `ancestor_type == "appendix"` 规则将连续 Annex 视为子附录。语义上合理（均为 UK Addendum 子项），location 路径仍可精确定位。
