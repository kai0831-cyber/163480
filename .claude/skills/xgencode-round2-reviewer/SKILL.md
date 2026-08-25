---
name: xgencode-round2-reviewer
description: xGenCode 二轮质检专家指南。代码审查视角，覆盖环境完整性、Dockerfile构建、单元测试规范、端到端验证、一轮问题修复复核、代码注释泄露检查。
---

# xGenCode 二轮质检专家指南

你是二轮质检专家的助手，在 Web IDE 的终端中运行。二轮质检由**代码审查专家**负责，从工程规范角度审查题目的技术实现质量。

---

## 一、二轮质检职责

**负责**：
1. 环境依赖是否完整（Dockerfile 能否正常 build 和启动）
2. 单元测试（test.sh）是否符合规范
3. 端到端验证（solve.sh + test.sh 联跑）
4. 一轮质检发现的问题是否已修复
5. 代码注释是否泄露 bug 信息

**不负责**：物理/数学正确性（这是一轮质检的工作）

---

## 二、质检流程（15 个 Checklist 项）

```
环境检查（3项）
├── env_dependencies_complete   环境依赖完整性
├── env_dockerfile_build_ok     Dockerfile 能否 build
└── env_container_boot_ok       容器能否正常启动

单元测试规范（5项）
├── unit_reward_always_written      reward.txt 必须写入
├── unit_has_anti_hardcode          包含反硬编码检查
├── unit_uses_relative_tolerance    使用相对容差
├── unit_cover_all_required_metrics 覆盖所有必要指标
└── unit_timeout_or_crash_reward_zero 超时/崩溃时 reward=0

端到端验证（2项）
├── e2e_solve_then_test_reward_one   solve.sh + test.sh → reward=1
└── e2e_without_solve_reward_zero    仅 test.sh → reward=0

一轮问题修复复核（2项）
├── round1_fail_fixed_or_explained  一轮 FAIL 项已修复或有说明
└── round1_fix_revalidated          修复项已重新验证

安全检查（3项）
├── security_no_copy_tests_solution  tests/ 和 solution/ 未互相复制
├── security_no_answer_or_bug_hint   代码中无答案或 bug 提示
└── security_instruction_no_fix_leak instruction.md 无修复方向泄露
```

---

## 三、逐项检查指南

### 环境检查

#### env_dependencies_complete：环境依赖完整性
检查 `instruction.md` 中提及的所有依赖是否都在 Dockerfile 里安装了。

```bash
# 查看 instruction.md 提到的依赖
cat instruction.md | grep -E "pip|install|import|require|package"

# 查看 Dockerfile 安装了什么
cat environment/Dockerfile

# 对照检查：instruction 里提到的包，Dockerfile 里是否都有
```

填写依赖对照表：
| 依赖项 | 是否提及 | 容器内可用 | 故意缺失 | 结论 |
|--------|---------|-----------|---------|------|
| numpy  | 是      | 否        | 是      | PASS |
| ...    |         |           |         |      |

**判定规则**：
- 故意缺失（题目要求 agent 安装）→ PASS
- 非故意缺失（出题人漏写）→ FAIL

---

#### env_dockerfile_build_ok：Dockerfile 能否 build

```bash
cd environment
docker build -t round2_test .
```

**常见失败原因**：
- 基础镜像不存在（镜像名拼写错误、私有镜像无权限）
- 网络下载超时（pip install 超时）
- 安装命令错误（包名错误、版本冲突）

**处理方式**：网络问题可重试一次；其他问题标记 FAIL 并记录完整错误日志。

---

#### env_container_boot_ok：容器能否正常启动

```bash
# 验证容器能正常启动并进入工作目录
docker run --rm round2_test bash -c "echo 'boot ok' && ls /workspace"
```

---

### 单元测试规范

#### unit_reward_always_written：reward.txt 必须写入

test.sh 在**任何情况下**（成功、失败、崩溃）都必须写入 `/logs/verifier/reward.txt`。

```bash
# 检查 test.sh 是否有 reward.txt 写入逻辑
grep -n "reward.txt" tests/test.sh

# 验证异常情况下也会写入（模拟崩溃）
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs round2_test \
  bash -c "bash /workspace/tests/test.sh; echo exit_code=$?"
cat /tmp/logs/verifier/reward.txt
```

**不合格示例**：test.sh 在某个 if 分支里忘记写 reward.txt，导致文件不存在。

---

#### unit_has_anti_hardcode：包含反硬编码检查

test.sh 必须用 grep 检查源码，防止 agent 直接写死答案数值。

```bash
# 检查 test.sh 里是否有 grep 反硬编码逻辑
grep -n "grep" tests/test.sh

# 验证反硬编码是否真的生效
echo "answer = 0.4524" >> environment/buggy_code.py
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs round2_test \
  bash /workspace/tests/test.sh
cat /tmp/logs/verifier/reward.txt
# 预期：0.0
```

**注意**：grep 模式必须足够严格。如果只 grep `0.4524`，agent 可以用 `0.45240001` 绕过，应该标记为需改进。

---

#### unit_uses_relative_tolerance：使用相对容差

数值比较必须用相对容差（`rtol`），不能用绝对容差（`atol`）或精确匹配。

```bash
# 检查 test.sh 或测试 Python 脚本中的容差设置
grep -n "atol\|rtol\|tolerance\|isclose\|allclose" tests/test.sh
grep -rn "atol\|rtol\|tolerance\|isclose\|allclose" tests/
```

**不合格示例**：
```python
# ❌ 绝对容差，在不同量级下不可靠
assert abs(result - expected) < 1e-6

# ✅ 相对容差
assert abs(result - expected) / abs(expected) < 1e-4
# 或
np.testing.assert_allclose(result, expected, rtol=1e-4)
```

---

#### unit_cover_all_required_metrics：覆盖所有必要指标

检查 test.sh 是否测试了 instruction.md 中提到的所有验收指标。

```bash
# 对照 instruction.md 的验收标准
cat instruction.md | grep -E "输出|结果|验收|指标|metric|output"

# 检查 test.sh 覆盖了哪些指标
cat tests/test.sh
```

---

#### unit_timeout_or_crash_reward_zero：超时/崩溃时 reward=0

模拟超时和崩溃场景，确认 reward 为 0。

```bash
# 模拟崩溃：让测试脚本提前 exit 1
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs round2_test \
  bash -c "timeout 1 bash /workspace/tests/test.sh; \
           [ -f /logs/verifier/reward.txt ] || echo '0.0' > /logs/verifier/reward.txt"
cat /tmp/logs/verifier/reward.txt
```

---

### 端到端验证

#### e2e_solve_then_test_reward_one：solve.sh + test.sh → reward=1

```bash
rm -rf /tmp/logs && mkdir -p /tmp/logs/verifier
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs round2_test bash -c \
  "bash /workspace/solution/solve.sh && bash /workspace/tests/test.sh"
cat /tmp/logs/verifier/reward.txt
# 必须是：1.0
```

**如果不是 1.0**：这是严重问题，说明参考解或测试脚本有 bug。标记 FAIL，在 IDE 中让 Claude 帮分析 solve.sh 的修复是否正确、test.sh 的期望值是否有误。

---

#### e2e_without_solve_reward_zero：仅 test.sh → reward=0

```bash
rm -rf /tmp/logs && mkdir -p /tmp/logs/verifier
docker run --rm -v $(pwd):/workspace -v /tmp/logs:/logs round2_test \
  bash /workspace/tests/test.sh
cat /tmp/logs/verifier/reward.txt
# 必须是：0.0
```

---

### 一轮问题修复复核

#### round1_fail_fixed_or_explained：一轮 FAIL 项已修复或有说明

先读取一轮质检报告，逐条核对：

```bash
# 查看一轮质检报告（通常在项目目录或平台下载）
cat round1_report.md
```

填写修复复核表：
| 一轮 FAIL 项 | 是否已修复 | 说明 |
|-------------|-----------|------|
|             |           |      |

**没有一轮质检报告时**：跳过此项，在报告中注明"无一轮报告，直接进行二轮质检"。

---

#### round1_fix_revalidated：修复项已重新验证

对一轮标记为 FAIL 并已修复的项，重新运行相关验证命令确认修复有效。

---

### 安全检查

#### security_no_copy_tests_solution：tests/ 和 solution/ 未互相复制

```bash
# 检查 tests/ 里是否包含 solution/ 的内容（或反之）
diff tests/test.sh solution/solve.sh

# 检查是否有直接 import 或 source 对方文件
grep -rn "solution\|solve" tests/
grep -rn "tests\|test\.sh" solution/
```

---

#### security_no_answer_or_bug_hint：代码中无答案或 bug 提示

检查容器内所有文件（包括注释）是否泄露了答案数值或 bug 位置。

```bash
# 检查代码注释中是否有泄露信息
grep -rn "# Bug\|# bug\|# 这里\|# fix\|# 应该\|# should\|# answer\|# 答案" \
  environment/

# 检查是否有中文注释泄露
grep -rn "错误\|修复\|改成\|应为" environment/
```

**注意**：任何形式的"这里是 bug"、"应该改成 xxx" 都算泄露，包括中文注释。

---

#### security_instruction_no_fix_leak：instruction.md 无修复方向泄露

```bash
# 检查 instruction.md 是否包含修复方向
grep -E "应该|should|改为|replace|fix|修复方向|正确值|correct value" instruction.md
```

---

## 四、质检报告模板

**保存路径**：`/review/quality-report-round2.md`

**保存命令**：
```bash
# 创建 review 目录（如果不存在）
mkdir -p /review

# 保存报告
cat > /review/quality-report-round2.md << 'EOF'
[在此粘贴下方报告模板内容]
EOF
```

质检报告模板：

```markdown
# 二轮质检报告

## 题目信息
- 题目 ID: [填写]
- 难度: [easy/medium/hard/expert]
- 一轮质检结论: [通过/不通过/无报告]

## 环境检查
| 依赖项 | 是否提及 | 容器内可用 | 故意缺失 | 结论 |
|--------|---------|-----------|---------|------|
|        |         |           |         |      |

## 端到端验证
| 测试 | 期望 | 实际 | 通过 |
|------|------|------|------|
| solve.sh + test.sh | 1 | | |
| 仅 test.sh | 0 | | |

## test.sh 审查
| 检查项 | 结果 | 说明 |
|--------|------|------|
| reward.txt 写入保证 | PASS/FAIL | |
| 反硬编码检查 | PASS/FAIL | |
| 数值容差 | PASS/FAIL | |
| 指标覆盖 | PASS/FAIL | |
| 崩溃兜底 | PASS/FAIL | |

## 一轮问题修复复核
| 一轮 FAIL 项 | 是否已修复 | 说明 |
|-------------|-----------|------|
|             |           |      |

## 代码注释泄露检查
- 结果: PASS / FAIL
- 说明:

## 最终验收
- [ ] 环境内包含 instruction.md 所提及的全部依赖
- [ ] 单元测试完善
- [ ] 一轮质检报告中问题已修复

**总体结论**: 通过 / 需修改 / 不通过
```

---

## 五、常见问题 Q&A

**Q: Docker build 失败怎么办？**
记录完整错误日志，标记 FAIL。常见原因：基础镜像不存在、网络下载超时、安装命令错误。网络问题可重试一次。

**Q: solve.sh 跑完 reward 不是 1 怎么办？**
这是严重问题，说明参考解或测试脚本有 bug。标记 FAIL 并详细记录。在 IDE 中可以让 Claude 帮分析 solve.sh 的修复是否正确、test.sh 的期望值是否有误。

**Q: 代码注释中有中文写的 "# Bug: ..." 算泄露吗？**
算。agent 能看到容器内所有文件的内容，包括注释。任何形式的"这里是 bug"、"应该改成 xxx"都算泄露。正确做法是代码注释不暴露任何错误信息。

**Q: 没有一轮质检报告怎么办？**
跳过"一轮问题修复复核"部分，其余步骤照常执行。在报告中注明"无一轮报告，直接进行二轮质检"。

**Q: 我不确定某个 bug 是"故意的"还是"出题失误"？**
对照 solve.sh——如果 solve.sh 中修复了这个问题，那就是故意设计的 bug。如果 solve.sh 也没修复它，那很可能是出题失误，需要标记。

**Q: test.sh 中的反硬编码 grep 模式不够严格怎么办？**
记录具体绕过方式。例如，如果只 grep 了 `0.4524` 但 agent 可以用 `0.45240001` 绕过，应该标记为需改进。

---

## 六、平台 Checklist 对应说明

| 平台 Checklist 项 | 对应章节 |
|------------------|---------|
| env_dependencies_complete | 三-环境：依赖完整性 |
| env_dockerfile_build_ok | 三-环境：Dockerfile build |
| env_container_boot_ok | 三-环境：容器启动 |
| unit_reward_always_written | 三-单元测试：reward.txt 写入 |
| unit_has_anti_hardcode | 三-单元测试：反硬编码 |
| unit_uses_relative_tolerance | 三-单元测试：相对容差 |
| unit_cover_all_required_metrics | 三-单元测试：指标覆盖 |
| unit_timeout_or_crash_reward_zero | 三-单元测试：超时/崩溃兜底 |
| e2e_solve_then_test_reward_one | 三-端到端：solve+test=1 |
| e2e_without_solve_reward_zero | 三-端到端：仅test=0 |
| round1_fail_fixed_or_explained | 三-一轮复核：已修复或说明 |
| round1_fix_revalidated | 三-一轮复核：重新验证 |
| security_no_copy_tests_solution | 三-安全：未互相复制 |
| security_no_answer_or_bug_hint | 三-安全：无答案提示 |
| security_instruction_no_fix_leak | 三-安全：instruction 无泄露 |

---

## 七、参考文档

- 二轮质检说明（代码审查）：https://wcngz2jid6iw.feishu.cn/wiki/PxThwMRFjiAA18kDUJqcuk1nnxb
- 一轮质检说明（领域专家）：https://wcngz2jid6iw.feishu.cn/wiki/LoDOwZRo8ic1qdkVh7ac2q8mnZy
- 项目说明：https://wcngz2jid6iw.feishu.cn/wiki/N11Kw1ytZiKPDvkZBMecXZdynug
