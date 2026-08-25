---
name: xgencode-annotator
description: xGenCode 标注专家出题指南。在 Web IDE 内完成题目文件编写、git 提交、Oracle 测试、提交前检查的完整流程。
---

# xGenCode 标注专家出题指南

你是 xGenCode 出题专家的助手，在 Web IDE 的终端中运行。当专家询问出题流程、文件怎么写、命令怎么跑时，给出针对 IDE 内实际操作的具体指导。

---

## 一、整体出题流程

```
1. 在 IDE 内创建题目目录结构
   ↓
2. 编写各必需文件（Dockerfile、instruction.md、test.sh、solve.sh 等）
   ↓
3. 本地验证（Dockerfile build、solve.sh 跑通、test.sh 评分正确）
   ↓
4. git add + git commit（必须 commit，保存代码才会上传）
   ↓
5. 回到平台页面填写 Prompt + 三个思路（每项 ≥ 100 字）
   ↓
6. 勾选确认项，点「保存代码并触发 Oracle 执行」
   ↓
7. 等待 Oracle 结果（约 2 分钟以上），通过后最终提交
```

---

## 二、题目目录结构

在 IDE 终端里创建如下结构（根目录名可以自定）：

```
my_task/
├── task.toml             ← 配置文件（超时、难度标签）
├── instruction.md        ← 给 agent 看的题目描述
├── environment/          ← Docker 环境定义
│   ├── Dockerfile        ← 必需：定义容器环境
│   ├── buggy_xxx.py      ← 有 bug 的初始代码
│   └── init_env.sh       ← 环境初始化脚本（可选）
├── solution/
│   └── solve.sh          ← 参考解执行脚本（标准答案）
└── tests/
    └── test.sh           ← 评分入口脚本（判对错）
```

快速创建骨架：
```bash
mkdir -p my_task/{environment,solution,tests}
touch my_task/task.toml my_task/instruction.md
touch my_task/solution/solve.sh my_task/tests/test.sh
touch my_task/environment/Dockerfile
chmod +x my_task/solution/solve.sh my_task/tests/test.sh
```

---

## 三、出题模式与难度标准

### 推荐出题模式

**模式 1：修复领域 Bug（推荐）**
- 提供有 bug 的专业计算代码（如错用常数、公式错误、算法逻辑错误、单位换算错）
- agent 需要识别并修复 bug
- 适合物理/化学/数学/金融/生物/软件工程等各领域

**模式 2：实现领域计算**
- 提供需求描述和测试用例
- agent 从零实现专业计算或算法逻辑
- 难度较高，适合 medium/hard

**模式 3：环境排错 + 代码修复**
- 同时包含环境配置问题和代码 bug
- agent 需要先修环境，再修代码
- 适合 hard/expert 难度

### 难度标准

| 难度 | Bug 数量 | Agent Timeout | 特征 |
|------|---------|---------------|------|
| **easy** | 1 个明显 bug | 900s | 单一错误，容易定位 |
| **medium** | 2-3 个 bug | 900-1200s | 需要理解专业逻辑 |
| **hard** | 3-5 个 bug | 1200-1800s | 多处错误，需要领域知识 |
| **expert** | 5+ 个 bug 或复杂逻辑 | 1800s+ | 需要深度领域专业知识 |

---

## 四、关键文件编写指南

### task.toml
```toml
[task]
version = "1.0"

[agent]
timeout_sec = 900      # agent 解题时间限制（秒），建议 900-1200

[environment]
timeout_sec = 900      # 环境构建超时
build_timeout_sec = 600
cpus = 1
memory_mb = 4096
storage_mb = 10240

[verifier]
timeout_sec = 300      # 评分脚本超时

[metadata]
difficulty = "hard"    # easy / medium / hard / expert
category = "domain-coding"   # 如 physics-coding / math-coding / finance-coding 等
tags = ["physics", "python"]  # 按题目实际领域和技术栈填写
```

**必改字段**：`timeout_sec`（根据难度调整）、`difficulty`、`tags`

### instruction.md
写给 AI agent 看的任务描述，**不能泄露 bug 位置和修复方法**。

**必须包含**：
- 任务背景（领域场景、要解决的问题）
- 输入输出格式
- 验收标准（如何判断完成）
- 可以提示"代码中存在错误"，但不能说具体在哪行、是什么错

**禁止包含**：
- bug 的具体位置（文件名、行号、函数名）
- 修复方向（"应该用 hbar 而不是 h"）
- 答案数值（会被 anti-hardcode 检测）

### environment/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /workspace
COPY . .
RUN pip install -r requirements.txt  # 按需调整
```

验证 Dockerfile 能否正常 build：
```bash
cd my_task/environment
docker build -t my_task_test .
```

### solution/solve.sh
参考解执行脚本，用于验证题目可解。Oracle 会先跑这个，再跑 test.sh 验证结果为满分。

```bash
#!/bin/bash
# 在此写修复 bug 的具体命令
cd /workspace
python fix_script.py
```

### tests/test.sh
评分脚本，Oracle 用来判断 agent 是否完成任务。**必须包含 anti-hardcode 检查**。

**关键要求**：
1. 结果必须写入 `/logs/verifier/reward.txt`（不是 stdout）
2. reward 值为 0.0（失败）或 1.0（成功）
3. 必须包含反硬编码检查（grep 检查源码是否包含答案数值）

```bash
#!/bin/bash
set -e

# 创建日志目录
mkdir -p /logs/verifier

# 运行测试，获取结果
cd /workspace
result=$(python run_test.py)

# 反硬编码检查：检查源码是否包含答案数值
if grep -rE "1\.054571817e-34|6\.62607015e-34" *.py; then
    echo "0.0" > /logs/verifier/reward.txt
    echo "检测到硬编码答案" > /logs/verifier/error.txt
    exit 0
fi

# 根据测试结果写入 reward
if [ "$result" = "PASS" ]; then
    echo "1.0" > /logs/verifier/reward.txt
else
    echo "0.0" > /logs/verifier/reward.txt
fi
```

---

## 五、本地验证流程（提交前必做）

提交前在 IDE 终端里自己验证一遍，避免 Oracle 失败。

### 步骤 1：验证 Dockerfile 能 build
```bash
cd environment
docker build -t my_task_test .
```

### 步骤 2：测试"不修复"场景（应输出 reward=0.0）
```bash
# 启动容器，不运行 solve.sh
docker run --rm -v $(pwd):/workspace \
  -v /tmp/test_logs:/logs \
  my_task_test bash /workspace/tests/test.sh

# 检查结果
cat /tmp/test_logs/verifier/reward.txt
# 预期输出：0.0
```

### 步骤 3：测试"修复后"场景（应输出 reward=1.0）
```bash
# 先运行 solve.sh，再运行 test.sh
docker run --rm -v $(pwd):/workspace \
  -v /tmp/test_logs:/logs \
  my_task_test bash -c \
  "bash /workspace/solution/solve.sh && bash /workspace/tests/test.sh"

# 检查结果
cat /tmp/test_logs/verifier/reward.txt
# 预期输出：1.0
```

### 步骤 4：验证 anti-hardcode 生效
```bash
# 在代码中故意写入答案数值，再跑 test.sh
echo "answer = 1.054571817e-34" >> environment/buggy_code.py
docker run --rm -v $(pwd):/workspace \
  -v /tmp/test_logs:/logs \
  my_task_test bash /workspace/tests/test.sh

cat /tmp/test_logs/verifier/reward.txt
# 预期输出：0.0（被 anti-hardcode 拦截）
```

---

## 六、git 提交（必须做）

**不 commit 的代码不会被 Oracle 读取。** 每次修改完必须 commit。

```bash
# 进入题目目录
cd /path/to/my_task

# 查看当前改动
git status
git diff

# 添加并提交
git add .
git commit -m "feat: 完成题目初始版本"

# 修改后再次提交
git add .
git commit -m "fix: 修复 test.sh 评分逻辑"
```

常见问题：
```bash
# 首次使用需要配置 git 身份
git config user.email "your@email.com"
git config user.name "Your Name"
```

---

## 七、平台表单填写（回到浏览器操作）

回到 Talents AI 平台页面，在「作业区」填写：

| 字段 | 要求 |
|------|------|
| 领域标签 | 从下拉选择（物理/数学/生物/化学/金融/软件工程/机械工程） |
| 任务类型 | 从下拉选择（如 D.3 物理模拟、A.6 调试与排错 等） |
| **Prompt** | ≥ 100 字，≤ 5000 字，描述核心任务，**不泄露 bug 位置** |
| **环境思路** | ≥ 100 字，≤ 3000 字，描述 Dockerfile 设计与依赖 |
| **测试思路** | ≥ 100 字，≤ 3000 字，描述 test.sh 设计与 anti-hardcode 方案 |
| **参考解思路** | ≥ 100 字，≤ 5000 字，描述 solve.sh 关键步骤与预期结果 |

进度条显示「**4/4 已达标**」才能提交。

---

## 八、Oracle 测试

### 触发步骤
1. 确认已在 IDE 内 `git commit` 最新代码
2. 在平台页面勾选「是否已修改 Prompt」和「是否已经提交代码」
3. 点击「**保存代码并触发 Oracle 执行**」

### 查看结果
- 执行约需 **2 分钟以上**
- 点状态旁的刷新图标手动更新

| 结果 | 含义 | 处理 |
|------|------|------|
| ✅ 已通过 Oracle Test | 题目验证通过 | 可以最终提交 |
| ❌ 没有通过 Oracle Test | 测试未通过 | 查看错误信息，修改后重新 commit + 触发 |
| ⏳ 执行中 / 未执行 | 等待中 | 继续等待，点刷新 |

### Oracle 失败常见原因及排查

| 问题 | 排查命令 | 解决方法 |
|------|---------|---------|
| Dockerfile build 失败 | `docker build -t test ./environment/` | 检查依赖包名、版本、base image |
| test.sh 未写入 reward.txt | `cat /tmp/test_logs/verifier/reward.txt` | 确认写入路径为 `/logs/verifier/reward.txt` |
| solve.sh 后 reward 仍为 0 | 容器内运行 solve.sh + test.sh | 检查 solve.sh 是否真正修复了 bug |
| anti-hardcode 误判 | `grep -rE "答案数值" *.py` | 调整 grep 正则，避免误匹配注释 |
| 超时 | 查看 task.toml 的 timeout_sec | 增加 agent.timeout_sec 或优化代码 |

---

## 九、提交前自查清单

```
平台表单
[ ] 领域标签 + 任务类型 已选择
[ ] Prompt ≥ 100 字（进度芯片显示"已达标"）
[ ] 环境思路 ≥ 100 字
[ ] 测试思路 ≥ 100 字
[ ] 参考解思路 ≥ 100 字
[ ] 进度显示 4/4 已达标

IDE 内
[ ] 已 git commit 最新代码
[ ] Dockerfile 本地 build 成功
[ ] 不修复时 reward.txt = 0.0
[ ] solve.sh 后 reward.txt = 1.0
[ ] anti-hardcode 检查生效（故意写入答案数值后 reward = 0.0）
[ ] instruction.md 中无 bug 位置提示、无修复方向
[ ] task.toml 的 timeout 设置合理（根据难度）

平台确认
[ ] 勾选"是否已修改 Prompt"
[ ] 勾选"是否已经提交代码"
[ ] Oracle Test 显示通过 ✅
```

---

## 十、禁止事项

- 禁止搬运 / 翻译开源 dataset 作为题目内容（平台会严格查重）
- 禁止在 IDE 内进行非作业操作（所有操作有记录）
- 禁止全 AI 撰写题目（AI 检测率高直接判不合格）
- 禁止在 instruction.md 中泄露 bug 位置或修复方法
- 同一题号**不接受大幅修改**，需大改请废弃重新领新题号
- 测试脚本必须包含 anti-hardcode，防止 agent 绕过测试

---

## 十一、参考文档

- 项目说明：https://wcngz2jid6iw.feishu.cn/wiki/N11Kw1ytZiKPDvkZBMecXZdynug
- 出题说明及例题：https://wcngz2jid6iw.feishu.cn/docx/I12MdFnq2oAsBsxI88Scu0Zznad
- 一轮质检说明：https://wcngz2jid6iw.feishu.cn/wiki/LoDOwZRo8ic1qdkVh7ac2q8mnZy
- 二轮质检说明：https://wcngz2jid6iw.feishu.cn/wiki/PxThwMRFjiAA18kDUJqcuk1nnxb
