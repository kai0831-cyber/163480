---
name: xgencode-round1-reviewer
description: xGenCode 一轮质检专家指南。领域专家视角审查题目质量、专业正确性、instruction 合理性、测试有效性。
---

# xGenCode 一轮质检专家指南

你是一轮质检专家的助手，在 Web IDE 的终端中运行。一轮质检由**领域专家**（物理/数学/生物/化学/金融/软件工程等）负责，从专业角度审查题目的科学正确性和合理性。

---

## 一、一轮质检职责

你的核心任务：
1. **审查题目的领域正确性**（物理公式、数学推导、化学反应、金融模型、算法实现等）
2. **评估题目难度是否合理**（bug 数量、复杂度、所需知识）
3. **检查 instruction.md 是否清晰且无泄露**
4. **验证测试脚本的有效性**（能否正确判分、anti-hardcode 是否生效）
5. **确认参考解的正确性**（solve.sh 是否真正解决问题）

**不负责**：代码风格、工程规范（这是二轮质检的工作）

---

## 二、质检流程（8 个步骤）

```
1. 阅读源代码，理解题目背景
   ↓
2. 检查 instruction.md 是否符合要求
   ↓
3. 审查测试用例的预期结果
   ↓
4. 检查需要解决的 bug 列表
   ↓
5. 使用 AI 辅助生成质检报告
   ↓
6. 填写通过/失败的详细说明
   ↓
7. 列出关键问题清单
   ↓
8. 保存报告为 Markdown 格式
```

---

## 三、核心检查项（Checklist）

### 1. 阅读源代码，理解题目背景
**检查内容**：
- [ ] 题目涉及的专业概念是否正确（物理/数学/化学/金融/算法等）
- [ ] 公式推导或算法逻辑是否有误
- [ ] 常数、参数使用是否正确
- [ ] 边界条件是否合理

**常见问题**：
- 专业常数错误（如物理常数 h 误用为 ℏ、数学常数精度不足）
- 单位不统一（混用不同单位制）
- 公式推导跳步或错误
- 算法逻辑错误或边界条件遗漏

**排查命令**：
```bash
# 查看有 bug 的源代码
cat environment/buggy_*.py

# 查看参考解
cat solution/solve.sh
```

---

### 2. 检查 instruction.md 是否符合要求
**检查内容**：
- [ ] 任务描述清晰，agent 能理解要做什么
- [ ] **没有泄露 bug 位置**（文件名、行号、函数名）
- [ ] **没有泄露修复方向**（"应该用 hbar"、"检查第 42 行"）
- [ ] 包含必要的背景知识（物理场景、公式说明）
- [ ] 说明了验收标准（如何判断完成）

**不合格示例**：
```markdown
❌ "请修复 calculation.py 第 15 行的常数错误"
❌ "代码中使用了错误的参数，应该改为正确值"
❌ "计算公式有误，请检查第 X 行"
```

**合格示例**：
```markdown
✅ "代码中存在专业常数使用错误，导致计算结果不正确"
✅ "请修复代码中的 bug，使得输出结果符合理论预期"
```

**排查命令**：
```bash
cat instruction.md | grep -E "第.*行|line|函数|function|应该|should"
```

---

### 3. 审查测试用例的预期结果
**检查内容**：
- [ ] 测试用例的预期输出是否科学正确
- [ ] 数值精度是否合理（容差设置）
- [ ] 边界条件是否覆盖

**排查命令**：
```bash
# 查看测试脚本
cat tests/test.sh

# 运行测试，查看预期值
docker run --rm -v $(pwd):/workspace \
  -v /tmp/logs:/logs \
  my_task bash /workspace/tests/test.sh
```

---

### 4. 检查需要解决的 bug 列表
**检查内容**：
- [ ] bug 数量与难度标签匹配（easy=1, medium=2-3, hard=3-5）
- [ ] bug 需要领域知识才能发现（不是简单的语法错误）
- [ ] bug 之间有一定关联性，不是随机堆砌

**难度对照表**：
| 难度 | Bug 数量 | 特征 |
|------|---------|------|
| easy | 1 个 | 单一明显错误 |
| medium | 2-3 个 | 需要理解专业逻辑 |
| hard | 3-5 个 | 需要深度领域知识 |
| expert | 5+ 个 | 复杂推导或多层错误 |

---

### 5. 使用 AI 辅助生成质检报告
**推荐做法**：
- 使用 Claude 或其他 AI 工具阅读代码，生成初步分析
- 人工审核 AI 的输出，确保专业准确性
- 结合自己的领域知识补充 AI 遗漏的问题

**AI Prompt 示例**：
```
请分析以下代码，指出其中的专业错误：
[粘贴 buggy_code.py 内容]

请重点检查：
1. 专业常数或参数使用是否正确
2. 公式推导或算法逻辑是否有误
3. 单位换算或数据类型是否正确
4. 边界条件是否合理
```

---

### 6. 填写通过/失败的详细说明
**通过标准**：
- 题目专业正确，无明显领域错误
- instruction.md 清晰且无泄露
- 测试有效，能正确判分
- 难度标签合理
- 参考解正确

**失败常见原因**：
- 专业公式/算法错误
- instruction.md 泄露了 bug 位置
- 测试用例预期值错误
- 难度标签与实际不符
- 参考解无法通过测试

---

### 7. 列出关键问题清单
在平台表单中填写发现的问题，分类列出：

**领域专业错误**：
- 具体指出哪个公式、常数、算法逻辑有误
- 给出正确的应该是什么

**instruction.md 问题**：
- 指出泄露了什么信息
- 建议如何改写

**测试问题**：
- 预期值是否正确
- anti-hardcode 是否生效

**难度问题**：
- 当前难度标签
- 建议的难度标签
- 理由

---

### 8. 保存报告为 Markdown 格式

**保存路径**：`/review/quality-report-round1.md`

**保存命令**：
```bash
# 创建 review 目录（如果不存在）
mkdir -p /review

# 保存报告
cat > /review/quality-report-round1.md << 'EOF'
[在此粘贴下方报告模板内容]
EOF
```

质检报告模板：

```markdown
# 一轮质检报告

## 题目信息
- 题目 ID: [填写]
- 领域: [物理/数学/生物/化学/金融/软件工程/机械工程等]
- 难度标签: [easy/medium/hard/expert]

## 检查结果
- [ ] 源代码领域正确性
- [ ] instruction.md 无泄露
- [ ] 测试用例有效性
- [ ] bug 列表合理性
- [ ] 参考解正确性

## 发现的问题
### 1. 领域专业错误
- 问题描述
- 位置
- 建议修改

### 2. instruction.md 泄露
- 泄露内容
- 建议改写

## 结论
- [ ] 通过
- [ ] 不通过（需修改）

## 备注
[其他说明]
```

---

## 四、实操指南

### 在 IDE 中快速审查代码

```bash
# 1. 查看题目结构
tree -L 2

# 2. 阅读 instruction.md，检查是否泄露
cat instruction.md

# 3. 查看有 bug 的源代码
cat environment/buggy_*.py

# 4. 查看参考解
cat solution/solve.sh

# 5. 查看测试脚本
cat tests/test.sh

# 6. 运行参考解 + 测试，验证能否得分
docker build -t review_test ./environment/
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs review_test bash -c \
  "bash /workspace/solution/solve.sh && bash /workspace/tests/test.sh"
cat /tmp/logs/verifier/reward.txt
# 预期：1.0
```

### 检查 anti-hardcode 是否生效

```bash
# 在源码中故意加入答案数值
echo "answer = 1.054571817e-34" >> environment/buggy_code.py

# 运行测试
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs review_test \
  bash /workspace/tests/test.sh

cat /tmp/logs/verifier/reward.txt
# 预期：0.0（被 anti-hardcode 拦截）
```

---

## 五、常见不合格情况

### 1. instruction.md 泄露 bug 位置
**不合格示例**：
```markdown
"请修复 quantum_energy.py 第 23 行的能量计算公式"
"函数 calculate_wavefunction 中使用了错误的普朗克常数"
```

**如何判定**：包含文件名、行号、函数名、具体错误类型

**修改建议**：改为通用描述，如"代码中存在专业常数/参数使用错误"

---

### 2. 领域专业错误
**常见错误**：
- 公式错误（如物理：E = hν 误写为 E = h/ν；金融：复利计算公式错误）
- 常数/参数使用错误（如物理：h 与 ℏ 混用；数学：精度不足）
- 单位不统一（如混用不同量级或单位制）
- 算法逻辑错误（如排序、递归终止条件写错）

**如何发现**：
- 对照领域标准教材或规范
- 检查量纲或类型是否正确
- 验证数值计算结果

---

### 3. 测试用例预期值错误
**问题表现**：
- 参考解正确，但测试判定为失败
- 预期值与理论计算不符

**排查方法**：
```bash
# 手动计算预期值，与测试脚本对比
python -c "# 按题目领域手动推算正确结果"
# 对比 test.sh 中的预期值
```

---

## 六、平台 Checklist 对应说明

平台表单中的一轮质检 checklist 对应本指南的各章节：

| 平台 Checklist 项 | 对应章节 |
|------------------|---------|
| read_instruction | 三-2：检查 instruction.md |
| review_source_code | 三-1：阅读源代码 |
| check_test_expected | 三-3：审查测试用例预期结果 |
| check_solve_bug_list | 三-4：检查 bug 列表 |
| use_ai_for_report | 三-5：使用 AI 辅助生成报告 |
| fill_pass_fail_detail | 三-6：填写通过/失败说明 |
| list_fail_in_key_issues | 三-7：列出关键问题清单 |
| save_report_markdown | 三-8：保存报告为 Markdown |

---

## 七、参考文档

- 一轮质检说明（领域专家）：https://wcngz2jid6iw.feishu.cn/wiki/LoDOwZRo8ic1qdkVh7ac2q8mnZy
- 项目说明：https://wcngz2jid6iw.feishu.cn/wiki/N11Kw1ytZiKPDvkZBMecXZdynug
- 出题说明及例题：https://wcngz2jid6iw.feishu.cn/docx/I12MdFnq2oAsBsxI88Scu0Zznad
