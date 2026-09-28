# 评论可读性与格式回退验证（D-256）

本轮完成展示层改进，并用已有记录重放评论。**这不是新的缺陷召回或误报评估。**
最终本地门禁在 `a7d51cc` 上通过：**2,498 passed、0 failed、0 skipped，
认证与执行覆盖率 93.42%**。本轮展示工作收尾，未达到发布级或 1.0 验收。

## 范围与版本

- 用户要求继续开发，并在合适的阶段实测；本轮选定此前提出的评论可读性任务。
- 基线：`b776fb5704a67ada9c2ec4ea7cfefaedec0abb44`。
- 实现：`31b5eea`；最终产品代码：`3f49cfffeab4cf551b4c573284fbe9a7b56f7adb`。
  `a7d51cc` 仅更新黄色标题的测试期望，产品源代码树与 `3f49cff` 完全相同。
- 分支：`fix/readable-review-comments`。只做本地提交，没有远程写入或付费调用。
- 主线关联：`docs/mainline.md` 条件 7；验证 `G-CODE-001`、`INV-PRESENT-001`、
  `INV-CERT-001` 和混合 DEFER 下已发布结果不能消失的约束。不宣称 L-01 或 1.0 完成。
- 输出格式版本为 `attest.output-contract.v1.1`，保留旧格式读取。
  意图默认仍是 v5.1，实验规则与契约发现、认证、排序、去重、发布上限均未改变。

产品文件：`src/attest/github/presentation.py`、`src/attest/review/output_contract.py`、
`src/attest/review/ci.py`。复用并更新 `test_github_presentation.py`、`test_green_channel.py`、
`test_ci_flow.py`、`test_impact_scope.py`；驱动、规范文档和证据一并保存。

## 改了什么

1. **每条评论分段。** 核心结论、复现事实和操作说明之间有空行。
   测试节点、finding ID、完整收据、测试代码和运行日志默认折叠。
2. **摘要按证据类别分节。** 每节一个标题，只统计这一节实际显示的条目；
   空节不出现。多条结构观察不再各自重复节标题。
3. **部分审查明确显示范围。** 有已认证发现时，预算导致的未验证数量和未读完的
   单元范围仍在正文显示。不能因为已经找到一个问题，就让读者以为全库已检查。
4. **格式拒绝保留发布身份。** 原来摘要格式失败会替换为静默行，导致已声明的
   发布成员与正文不一致。现在用同一发布名单重建简洁摘要，再检查一次。
   第二次仍不合格式时明确失败，不伪造静默结论。

## 可直接阅读的成品

这些文件是产品 renderer 的实际输出，没有人工改写结论。

- [单条红色评论](evidence/2026-09-15-readable-comments/final/inline-1.md)
- [真实 PR 的黄色评论](evidence/2026-09-15-readable-comments/final/inline-5.md)
- [结构观察](evidence/2026-09-15-readable-comments/final/inline-12.md)
- [多条、多个证据类别的摘要](evidence/2026-09-15-readable-comments/final/multiple.md)
- [部分完成的审查](evidence/2026-09-15-readable-comments/final/partial.md)
- [静默审查](evidence/2026-09-15-readable-comments/final/silent.md)

**样例限制：** 红色输入来自 D-255 的冻结提案，标题中的 `frozen…` 是此前驱动重建
候选时保存的占位文本，不是自然语言标题。没有为了让截图好看而替换它。
多条摘要组合了不同任务的数据，是布局检查，不是真实的单个 PR。
样例花费和时长统一显示为 0，表示本次纯展示调用，不是历史模型或容器执行成本。

## 实测协议和结果

驱动 `scripts/acceptance/presentation_replay.py` 先在 `31b5eea` 提交，然后运行。
基线 renderer 从 `b776fb5` 的 Git archive 读取，文件摘要与该提交完全一致；
两次重放使用同一输入、同一驱动，不调用模型、容器执行器或 GitHub API。

| 输入或检查 | 结果 | 正确的计数含义 |
|---|---:|---|
| 保存的缺陷 receipt | 4 份全部重新通过 bundle 检查 | 4 个已有注入缺陷案例；未重新执行 |
| 真实 PR 的黄色观察 | 7 条，来自 4 个 PR | 不是 7 个独立 PR，也没有新语义标签 |
| 静态结构检查 | 1 对重复实现 | 重新读取本仓库两个脚本计算；不等于语义等价 |
| 摘要布局 | 6/6 通过格式检查 | 单条、多条、仅黄、仅绿、部分完成、静默 |
| 逐条评论 | 12/12 通过格式检查 | 4 红、7 黄、1 绿；不是 12 个缺陷 |
| 改前／改后身份、坐标和收据 | 一致 | 只证明本次重放没有丢失或替换成员 |

重放的 bundle 检查没有载入控制器密钥，不能称为重新验证了签名来源。
离线检查重判记录的观察，不重建 D-255 契约源码绑定。

结构检查读取 `scripts/corpus/impact_scan.py` 和 `scripts/corpus/qualify_controls.py`，
复用现有 `functions_of`、`find_duplicate_implementations`、`structural_note`。
清单写入复用 `benchmark.artifacts.write_canonical_json` 和 `sha256_bytes`；
没有新增序列化、摘要或评分工具。

## 测试与门禁

- 改前 RED：缺少评论段落和计数标题；注入摘要格式拒绝导致
  `publication body does not match declared members`；部分审查没有可见覆盖范围。
- 对应测试在修复后通过。交付兼容性检查覆盖真实临时仓库、mock GitHub HTTP
  接口、receipt-only 发布、去重、硬上限、已有评论与混合结果。
- 全量门禁：`a7d51cc`，2,498 通过、0 失败、0 跳过；耗时约 36 分 47 秒。
  Ruff 通过，Mypy 检查 97 个源文件通过。认证与执行的合并覆盖率为 93.42%。
  其他模块仅作观察：review 90%、CLI 92%、GitHub 93%、benchmark 89%、core 99%
  （覆盖率工具的整数显示，无额外门槛）。环境、命令、锁文件摘要见
  [environment-a7d51cc.json](evidence/2026-09-15-readable-comments/environment-a7d51cc.json)。
- 这是当前 Python 3.12.2 环境的工作单门禁；未运行发布级的双 Python 版本整合验证。
- 自查适用：仅改展示及 CI 摘要拼装，没有修改认证或执行包；按 `G-CODE-001`
  不要求另行独立代理评审。

第一次重放发现绿色列表出现 `- -`。修正为单个列表符号并增加断言后，最终重放
全部通过。`after/` 保留这个中间结果；`final/` 才是最终成品。
`31b5eea` 上刚启动的全量门禁因该修正而中止，退出码 2，日志保留；不计作通过。

`3f49cff` 的完整门禁得到 **2,497 passed、1 failed、0 skipped，覆盖率 93.42%**。
失败是 `test_the_summary_carries_the_yellow_line_when_the_level_speaks`：仍期望
不含数量的节标题。`a7d51cc` 将期望改为计数标题，并增加空行和单一标题检查；
没有删除它对黄色结论、格式准入和红黄区分的断言。随后 93 项相邻测试通过。
这次失败记录保留，不把修正前的全量结果描述为通过。

复验时另有一次测试未能收集：Python 报告跳过了带 `UF_HIDDEN` 标志的 editable
安装路径文件，因而无法导入 `attest`。仅清除本仓库 `.venv` 内该文件的隐藏标志后
导入和测试恢复；文件内容未改。不推测该标志是谁设置的，也不把它算成产品故障。

完整的检查结果见 [checks-a7d51cc.json](evidence/2026-09-15-readable-comments/checks-a7d51cc.json)，
文件摘要和各次运行身份见 [manifest.json](evidence/2026-09-15-readable-comments/manifest.json)。

## 结论与后续边界

这轮解决评论排版及一种交付不一致，**没有证明召回提升**。不把历史 19/40
改写成当前完整 forty 结果，不从这些已挑选的案例估算精确率，更不宣称普遍零误报。

下一次提高检测能力前，仍需解决契约的隐式上下文边界，以及首个不可认证差分
遮住后续探针的选择问题。之后应在未参与规则开发、预先固定的缺陷与合理变化
集合上实测；不能用此次评论重放代替独立评估。付费、默认规则提升和发布仍需
相应的明确授权。

回退：可回退本分支的两个展示提交及其测试跟进提交；旧 receipt、意图版本和发布策略无需迁移。

## 归档说明

`de55957` 的归档包含 pytest 原始错误输出中的行尾填充空格，暂存差异检查曾报告这些
空格。为保持原始字节及清单摘要，未重写输出；`.gitattributes` 仅对本次目录的原始
门禁日志和生成的 Markdown 样例关闭 `blank-at-eol` 检查。源码、测试、手写报告及
其他证据目录仍使用普通检查。此规则不影响 pytest、类型检查、覆盖率或 receipt 验证。
