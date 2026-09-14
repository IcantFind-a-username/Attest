# 以"行为契约与证据"为中心的改进方案

Status: **decision package；Phase 0 已完成（2026-09-15，D-249 / D-250 / D-251，$0.00）；Phase 1 的离线部分已完成（2026-09-15，D-252：实验性 v6 与新旧规则配对，[报告](../acceptance/2026-09-15-v6-pairing.md)），付费重跑与默认规则切换仍等 §8 的决定 B、C**
基线：`main@a66324b`，2026-09-15。全程未改产品代码，未发起付费调用。
回应：owner 于 2026-09-15 给出的架构评审（下称"评审"）。
上位文档：`AGENTS.md` §3 北极星、§6 不变量、§16 停下来问；`docs/architecture/target-algorithm.md`；`docs/mainline.md` §1.1 四级发言规则。本文不改动任何一条，只在它们之下排工作。

---

## 0. 结论

**同意评审的主方向：保留认证内核、隔离执行和 receipt，把投入放在"正确性依据"上。** 但把"大重构"拆成四段，每段有退出条件，前两段几乎免费；付费只在第二段结束时买一次 forty 重跑（约 $3，在剩余额度内）。

核对评审引用的代码和三臂账本后，有三个补充判断改变了排序：

1. **评审说的"证明了变了、证明不了违反了要求"是对的，而且比评审写的更机械。** arm C 的 27 个未认证案例里，**4 个**不是缺少契约，而是被一个规模上限判成"无可关联符号"：`symbol_ranges` 在一个文件的 def/class 超过 `MAX_SYMBOLS = 200` 时返回 `None`，`more_itertools/more.py` 有 225 个，于是该文件上的任何值类 receipt 都永远进抽屉（[`intent.py:71`](../../src/attest/review/intent.py)、[`intent.py:865`](../../src/attest/review/intent.py)）。我在 tip `9ed3dbb0` 的 `more.py` 上本地复现：`symbol_ranges(...) -> None`，`anchored_symbols(...) -> ()`。这是一个上限变成了裁决，修复免费。
2. **规格匹配只认字面常量。** `assertion_pinned_values` 只读比较式里的 `ast.Constant`（[`intent.py:390`](../../src/attest/review/intent.py)）。基线测试写 `assert _parse_musl_version(s) == _MuslVersion(1, 2)` 时，`_MuslVersion(1, 2)` 是调用表达式，对规则不可见；而探针 pin 住的正是 `'_MuslVersion(major=1, minor=2)'`。arm C 里 7 个"独特值无人断言"的案例中至少 2 个 pin 的是对象 repr。这就是评审第一条"契约表达能力"在代码里的具体位置。
3. **发现阶段的理解确实没传给探针。** 探针提示词的共享前缀是 `_generation_prompt → planner.generation_context`（[`executor.py`](../../src/attest/review/executor.py) 的 `_generation_prompt`，[`planner.py:914`](../../src/attest/review/planner.py)）：围绕锚点重取 head/base 定义、签名、最近测试模块的 helper。D-246 索引解析出的调用者（`review_plan` 行的 `callers`，含 `exact`/`attribute` 解析等级）只进了发现阶段的 `prompt_context()`，**没有进探针**。B/C 臂"第一探针选了 `parse_stream` 入口"是模型从 claim 的散文里读到的，不是从事实里。

因此顺序是：先修判决性的上限和匹配器（免费、可回放验证），再做契约类型和证据包，最后才是定向反例搜索。目标口径按评审：**在固定、独立的评测人口上正确命中缺陷的比例 > 50%，错误诊断 0，另报不确定性**。本文不承诺这个数能达到；第一阶段的审计负责说出上限。

---

## 1. 评审判断的核对

### 1.1 数字（全部一致）

| 评审的数字 | 核对来源 | 结果 |
|---|---|---|
| A/B/C = 12/14/13 of 40；并集 15；B 在 13 个边界案例中 12 个造出差异、1 个认证；三臂 value class 17/17/16 | [`2026-09-14-probe-arms.md`](../acceptance/2026-09-14-probe-arms.md) §1 | 一致 |
| C 因单位认证成本最低当选；没有证明任何一臂召回更高 | 同上 §3；[`pricing.toml:4`](../../src/attest/data/pricing.toml) 的 D-248 注释 | 一致 |
| 真实 PR 14 条输出全是 yellow；4 有用 / 3 真实不可行动 / 7 待评；另 6 条撤回不计入 | [`receipts.md`](../receipts.md) | 一致 |
| 变异分类器：案例内出现一条 accepted certification 即计 certified，不做诊断与植入缺陷的语义匹配 | [`mutation_recall.py:363`](../../scripts/corpus/mutation_recall.py) `classify` | 一致 |
| score bar 已移除，不能再当召回杠杆 | D-199；[`evidence.md`](../evidence.md) | 一致 |
| 观察是 `("value", repr(x))` 或异常类型 | [`probe.py:38`](../../src/attest/review/probe.py) | 一致 |
| 预算：每单元先预留全部 K 次提案，装不下即停后续单元；购买顺序先看簇大小再看静态可信度 | [`proposer.py:544`](../../src/attest/review/proposer.py)、[`ranking.py:152`](../../src/attest/review/ranking.py) | 一致 |

一个补充：forty 已被同一套代码的演化跑了 **7 次**（2026-09-13 的原始跑、D-238、D-240、D-245、三臂 A/B/C），按 `AGENTS.md` §9 每次重跑自有 ±2 抖动。它现在是**诊断集**，不再是验证集；这是 Phase 3 要新人口的原因。

### 1.2 arm C 的 27 个未认证案例，按"缺哪一环"分组

从 [`arm-C/*-ledger.jsonl`](../acceptance/evidence/2026-09-14-probe-arms/arm-C/) 的 `verification` 行读出，每案一次：

| 组 | 案例数 | 案例 | 缺的是什么 | 哪个杠杆能碰到 |
|---|---:|---|---|---|
| 机械 | 7 | `attrs-boundary-09`（模块导入期常量，探针在 base 上执行不到该文件）、`packaging-boundary-11`、`click-guard_raise-03`、`itsdangerous-guard_raise-04`（三探针均无差异）、`click-none_guard-15`（探针 setup 改 `sys.stdin`，D-235 卫生规则拒绝）、`more-itertools-none_guard-17`（base 上不稳定）、`packaging-none_guard-13`（两探针没碰到变更行） | 搜索没找到差异输入 | 定向反例搜索（Phase 2）；`attrs-boundary-09` 按 D-231 本就不是崩溃点 |
| 符号上限 | 4 | `more-itertools-boundary-08`、`-boundary-10`、`-guard_raise-04`、`-guard_raise-05` | `MAX_SYMBOLS` 判成"无可关联符号" | Phase 0 修复；其中 `first([])`/`last([])` 的 `ValueError` 极可能有 `pytest.raises` 指明，修复后由 D-240(b) 规则直接读 |
| 删除守卫、异常名无测试指明 | 7 | `attrs-guard_raise-03`（`UnannotatedAttributeError`）、`itsdangerous-guard_raise-01`、`click-guard_raise-05`（`ValueError`）、`urllib3-guard_raise-03`、`jinja-guard_raise-01`（`TypeError`）、`packaging-guard_raise-06`（`DirectUrlValidationError`）、`python-dotenv-guard_raise-02`（`OSError`） | base 抛、head 不抛；树里没有关于该符号的 `raises`/断言/changelog | 新的可采信规格来源：docstring 的 `Raises` 段、参数化表；否则是"树里没有要求"，该留在 yellow |
| 独特值无测试断言 | 7 | `click-boundary-07`（`'01:01:01'`）、`packaging-boundary-08`（`_MuslVersion(major=1, minor=2)`）、`python-dotenv-boundary-06`（`'#novalue'`）、`urllib3-boundary-07`、`jinja-boundary-12`、`python-dotenv-boundary-08`（`[Variable(...)]`）、`jinja-none_guard-13` | 值可能被对象式断言/参数化表指明但匹配器看不见；或树里确实没有 | 断言表达力（Phase 1）；余下的是边界输入无人规定，正确结论就是 yellow |
| 泛型常量 | 2 | `click-boundary-10`（`1`）、`urllib3-none_guard-18`（`False`） | D-132(b) 按值排除 | 契约按 (符号, 输入, 关系) 成立后不再按值排除 |

**没有一组能靠"更多思考/更多采样"解决**，这与评审的读法一致。四组之和 20 例中，能被"树里已有但看不见的规格"救回的上限要靠 Phase 0 的审计给出，不在这里预估。

### 1.3 评审中我不完全同意或需要限定的地方

- **"`None`、`0`、`True` 常因缺乏独特性被拒"**：arm C 只有 2 例是这个原因。它是真问题，但不是主损耗；主损耗是"树里没有关于这个输入的规定"和"规定存在但匹配器读不到"。
- **"保留原测试、fixture 和数据依赖"**：D-206/D-211/D-212 关闭的 derived probe 只提取字面参数的模块级调用。评审要的"完整保留断言与 fixture 语义"是另一件事，但要说清它对**自然流量**的价值：合并 PR 的 CI 已经跑过 head 的测试；base 测试与 head 测试不同只在 PR 改了测试时，而那正是 D-132(c) 的意图证据、进抽屉。所以"自测回放"主要是**测量工具**（把 forty 分成"库自己的测试能抓到"和"静默变异"两半，D-231 明说这没测过）和**契约来源**，不是产品杠杆。评审要求分开统计，本文照办。
- **调度学习**：`docs/mainline.md` 把 S-* 排在 L-01 之后。本文只做透明的覆盖优先启发式，不碰 bandit。

---

## 2. 不动的东西

- 认证内核不调用模型、fail-closed、按记录的策略版本判定（`attest.certification`，`INV-CERT-001`、`INV-VERSION-001`）。
- "LLM 思考，算法决定能否发言"（mainline §1.1）。契约的**来源可信度由规则判定**，模型推断出的规则只驱动搜索。
- 发布句只表达证明链实际支持的内容（D-142 输出契约）。
- 隔离执行与 receipt（X-01/X-02/V-03）。Hypothesis/CrossHair 若引入，只在 `linux-container-v1` 内运行；CrossHair 自己的执行保护不算隔离。
- 不新增模型臂、不恢复 score bar、不放宽 GENERIC 规则本身、不重包装 derived probe。
- 新的证据类或规格来源是 §16 的 owner 决定（D-240 就是这样批的）。

---

## 3. 目标口径

沿用 target-algorithm §10 的三个分母，并按评审补充：

| 指标 | 分母 | 备注 |
|---|---|---|
| 缺陷语义召回 | 评测人口中的植入/已知缺陷 | 诊断必须命中植入位置与机制（修 `classify`，见 Phase 0） |
| 认证命中率 | 同上 | 今天的 32.5% 是这个，不是自然流量召回 |
| 可交付召回 | 同上 | 受每 PR 上限 3 条压制后作者实际看到的 |
| 错误诊断数；至少一条错误诊断的 PR 数 | 输出行；PR | 零错误观察不证明未来零错误，只报计数与区间 |
| 未运行 / 弃权 / 待裁决 / 被上限压制 | 案例 | 分开列 |
| 相同预算下成本、延迟；逐例 gained/lost | 案例 | `AGENTS.md` §9 的 ±2 规则 |
| **库自身测试能否抓到该缺陷** | 变异案例 | 新列；分开报"原测试本来就能发现"与"新方法才发现" |

---

## 4. 设计：契约作为证据对象

### 4.1 `BehaviorContract`（新类型，`attest.contract.v1`）

一条契约至少含：

| 字段 | 含义 | 今天对应的碎片 |
|---|---|---|
| `subject` | `module:qualname` | `anchored_symbols`（受 §1.2 的上限之害） |
| `input` | 一个具体调用（imports/setup/expression，即 `ProbeSpec`）及其来源；若来源声明了输入域则记录 | 探针 |
| `relation` | `returns_equal` / `raises` / `predicate` / `relation_between_calls` | `pinned_values`、D-240(b) 的异常名 |
| `source` | `base_test_assert` / `base_test_raises` / `base_test_parametrized` / `docstring_raises` / `changelog` / `explicit_invariant` / `model_hypothesis` | `value_specified` 的路径 |
| `site` | `path:line` | 同上 |
| `standing_at_head` | 这条改动没有重写该来源 | `value_respecified`、`intent_evidence` |
| `trust` | `admissible`（可认证）/ `hypothesis`（只驱动搜索） | 不存在 |

**可采信来源的规则**：能机械保留语义的基线测试断言（含对象式比较、参数化表）、`pytest.raises`/`assertRaises`（已有）、docstring 的 `Raises`/`:raises X:` 段、changelog 条目（已有）、显式前后置条件。模型从文档推断的规则和"在 base 上通过很多次"都只是 `hypothesis`。**契约按 (subject, input, relation) 整体成立，值本身是否泛型不再单独排除**——这是对 D-132(b) 的替代而不是放宽：`None` 作为孤立字面值仍不算规格，作为"`f(x)` 在 `x` 上返回 `None`"的完整关系才算。

### 4.2 `EvidencePacket` 贯穿发现、搜索与认证

复用 `TreeIndex`（D-245/246）和 `review_plan` 行已有的 `callers`。一个候选从发现起携带：变更符号；真实入口（调用者，带 `exact`/`attribute`）；树传给符号的字面量；相关断言；消费者；已找到的契约。每条事实标注 **已解析 / 执行见证 / 模型推测**。

具体改动点：`_probe_hint` 增加"树通过这些入口到达该符号"一段（事实，不是指令，沿 D-216 的措辞）；反馈携带同一段；`probe_observation` 行记录本次探针用了哪个入口、命中了哪条契约。认证观察增加 `contract_id`，使"失败是否对应最初的主张"可从账本回答。

### 4.3 证明义务 → 动作

| 已有证据 / 问题形态 | 优先动作 | 落点 |
|---|---|---|
| 基线测试对该符号有断言 | 保留原断言与 fixture 语义，在 head/base 上精确执行该测试节点 | 新的执行器动作 `own_test_replay`；只作测量与契约来源 |
| 比较边界发生变化（D-240 的 `changed_conditions`） | 从字面量与边界值构造邻近输入（`b-1, b, b+1`、空、负），先确定性再符号求解 | 现有 `boundary.py` + 探针提示；CrossHair 排 Phase 2 |
| 底层 API 差异难解释（`read_regex` 的形状） | 从 `callers` 的公开入口构造端到端见证 | §4.2 的入口传递；gate 级的 through-caller 机制（D-223）可复用 |
| 多次操作后才出问题 | 状态机序列，检查树里**声明的**不变量 | Phase 2，Hypothesis stateful，仅当树声明了不变量 |
| 编解码、转换等关系 | 在明确适用域内检查已有关系 | Phase 2，MR-Scout 式提取，`hypothesis` 级 |

调度规则先用透明启发式：**先覆盖不同影响区域，再加深有契约机会的候选**——在 `rank` 的键里于簇大小之前加"该单元是否已有候选被购买"和"是否存在可采信契约"。学习型调度不在本方案内。

### 4.4 认证链与发布句

回归类的完整链：**契约可采信 → 输入合法且可达 → base 满足契约 → head 违反契约 → 失败可归因于相关变更**。前四环由契约类型和差分 receipt 提供；第五环今天是变更行覆盖（V-02），跨文件案例补数据依赖与失败路径，补丁消融只作归因证据、不判意图。

发布句按链的深度分级：证明了某输入下的契约失败，就只说这个失败；影响面的话需要额外见证。"真实的行为变化"（今天的 yellow value）与"缺陷诊断"继续分开计量。

**这需要 `attest.intent.v6`**：字段与 v5 相同，新增 `contract` 记录；规则从"pinned 值是否被字面断言"改为"是否存在可采信契约覆盖该输入"。按 D-121 旧 receipt 按旧版本判。这是 §16 的 owner 决定，见 §8。

---

## 5. 分阶段计划

每阶段一个退出条件；失败即产出决策包，不降门槛（roadmap §3 规则 8）。

### Phase 0 — 免费，先把"上限当判决"和"看不见的规格"量出来（约 2 个工作日）

**已完成，2026-09-15（[报告](../acceptance/2026-09-15-evidence-supply.md)）。** 0.1 → D-249：`symbol_ranges` 不再按定义数量拒绝，`anchored_symbols` 只约束记录；more-itertools 的 4 例重新关联到符号，其中 3 例按现行规则在重建的基线树上已被指明；真实 PR 三个批次的 95 条 verification 行里该标签出现 0 次。0.2 → D-250：分类器要求 receipt 落在变异 hunk 上；8 轮记录重算，0 条落在别处，计数不变。0.3/0.4 → D-251：27 个未认证案例里，**9** 例树里有可采信契约但链条读不到（符号上限 3、对象式断言 3、经公共调用者或 helper 才关联到的异常 3），**5** 例树的自身测试里有判别输入而搜索没找到，**13** 例树里没有要求（docstring Raises 段 0/40）；库自身命名该符号的测试能抓到 **21/40**（未认证案例中 14 例），而 Attest 认证了 **5** 例这些测试抓不到的缺陷。**退出条件 9 ≥ 8 成立，Phase 1 保持原形。** 原表如下。


| # | 工作 | 交付 | RED |
|---|---|---|---|
| 0.1 | 修 `symbol_ranges` 的 `MAX_SYMBOLS`：超限时不再返回 `None`，改为只对变更行附近的定义求范围（或提高上限并记录截断） | 一个 `fix:` 提交；`scripts/corpus/intent_replay.py` 在已提交的 verification 行上回放，报告 forty 的 4 例与 68 个真实 PR 抽屉行的类别变化 | 一个 225 定义的文件，锚在其中一个 def 内，`anchored_symbols` 非空 |
| 0.2 | 修 `mutation_recall.classify`：certified 需要 accepted receipt 的锚定文件与符号命中变异位置 | 对已有 8 次 forty 的 trials 重算，报告"计数一致 / 因位置不符而降级"的案例 | 一个锚在别处的 accepted receipt 不计 certified |
| 0.3 | **证据供给审计**（评审的第一步）：在本地重建的 40 棵树上（`mutate.py`，$0），逐案记录：库自身与该符号相关的测试在 head 上是否失败（只跑 `_test_references` 找到的节点，分钟级；全量套件在 runner 后台跑一次作对照）；树里关于该符号存在哪些可采信来源（字面断言 / 对象式断言 / 参数化表 / `raises` / docstring Raises / changelog）；今天断在链的哪一环 | `docs/acceptance/<date>-evidence-supply.md`，每案一行，末列写"哪个杠杆最多能救回 / 树里没有要求" | 无（测量类，AGENTS.md §11） |
| 0.4 | 断言表达力离线测：在 0.3 的树上，用 `ast.unparse` 的比较式而非常量去匹配 7 个独特值案例的 pinned repr | 数字并入 0.3 的报告 | 无 |

**退出条件**：0.3 给出两个数——(a) 库自身测试本来就能抓到的案例数；(b) 可采信来源存在但今天读不到的案例数。**若 (b) + 0.1 的恢复数 < 8**，则 C 臂 13/40 靠契约达不到 20/40，Phase 1 仍做（它是正确性的修复，不是召回的赌注），但 Phase 2 的重心改为"树里没有要求的边界输入应留在 yellow"与新评测人口，并如实写入 README 的限制条。

### Phase 1 — 契约类型、表达力、入口传递；一次付费重跑

**离线部分已完成，2026-09-15（[报告](../acceptance/2026-09-15-v6-pairing.md)，D-252）。** 1.1/1.2 以实验性 `attest.intent.v6` 落地：对象式断言、参数化行、经调用者的 `raises` 作为契约记录，只有同时绑定具体输入、可机械推导的值、同一入口（或探针确实经由该调用者）时才采信；四个反例测试钉住不得误关联。在 arm C 的 33 个冻结探针上配对：**新增 0、丢失 0**，找到的 23 条契约全部因输入不同或入口不同被拒并记录理由；真实 PR 的 4 条可回放对照全部保持 yellow。D-249 单独测得 3/4。结论：契约的价值取决于探针是否使用契约自己的输入与入口，这是 1.3 与 Phase 2 的搜索问题，需要付费重跑才能量到。Docker 下的全量门禁与容器回放在本机被阻塞（报告 §4）。原表如下。


| # | 工作 | 依赖 | 边界 |
|---|---|---|---|
| 1.1 | `BehaviorContract` 类型与 finder：对象式断言、参数化表、docstring Raises 作为来源；`hypothesis` 级来源只进搜索提示 | 0.3 的数字；owner 决定 B | 证据类规则，§16 |
| 1.2 | `attest.intent.v6`：观察增加 `contract`；规则改为契约覆盖；离线验证器同步；旧版本按旧规则 | 1.1 | kernel 路径，需独立评审（`G-CODE-001`） |
| 1.3 | 入口传递：`callers` 进探针提示与反馈；`probe_observation` 记录入口与契约 | 无（可先于 1.1） | 检索类，agent 决定 |
| 1.4 | `own_test_replay` 执行器动作，只用于测量列与契约来源，不进发布 | 0.3 | 执行路径 |
| 1.5 | **付费**：同一 forty、arm C 默认配置、$1.00/case、p95 预留，一次 | 1.1–1.4 合入 `main` | 预登记：逐例 gained/lost 并按杠杆归因；±2 抖动内不算变化；分开报"原测试本能发现"与"新方法才发现" |

预算：arm C 跑 forty 花了 $1.99，D-245 那次 $2.82。`DEVSPEND.md` 2026-09-14 索引窗口前累计 $137.73，三臂 $7.72，加自审滞后约 $0.4，**约 $146 of $150，剩余约 $4**。这一次跑得下；再多一次就要 owner 提高上限（决定 C）。

**退出条件**：新认证的每一例都能从账本命名机制（契约来源、入口、base 记录）；0 例错误认证（用 68 个真实 PR 的 value 行做对照回放：其中被裁为"真实但不可行动"的 3 条是已合并 PR 里有意或无害的行为变化，v6 在它们上必须仍是 yellow）。

### Phase 2 — 定向反例搜索（需要提高付费上限）

按 0.3 的需求数排序，只做有需求的：

- 边界邻近输入的确定性生成（从 `changed_conditions` 与字面量），先于任何求解器；
- through-caller 端到端见证复用 gate 级机制，对"底层 API 差异难解释"的案例；
- Hypothesis stateful 只在树声明了不变量的符号上；CrossHair 只在容器内、只对 `admissible` 契约求反例，找不到反例不作任何结论；
- 关系型 oracle（MR-Scout/MR-Coupler 思路）作为 `hypothesis`，认证仍需可采信来源。

每一项单独一个工作单，单独归因；探索与最终验证分开记录（搜索过程、冻结的选择规则、最终测试），新鲜重放只检验稳定性。

### Phase 3 — 独立评测人口与冻结流程

- 新的 forty：不同种子、至少两个未用过的库；同时纳入**合理行为变化对照**（真实 PR 中有意改变行为的提交，68 个真实 PR 的 value 行已提供 3 条已裁决样本）；
- 冻结整套流程后盲审：诊断与目标缺陷的语义对应由不看产品输出的人裁决（`INV-TRUTH-001`）；
- 报告 §3 的全部指标；旧 forty 只作诊断附录。

Conformal / 选择性预测在这一阶段之后才有意义，且只校准整套搜索程序。

---

## 6. 与路线图的关系

- 不新增 CLI 子命令、不新增产品表面；改动落在 `attest.review`（检索、探针、执行器动作）和 `attest.certification.intent`（v6）。
- 遵循 R 族工作单的家族默认：新 seam 可关闭，回退到上一条安全路径（`contract_sources = "v5"` 即恢复今天的规则）。
- 每个工作单一条 ≤ 6 行的 `DECISIONS.md` 记录；v6 与来源规则在 `target-algorithm.md` §8.3a 同一提交更新。

---

## 7. 风险与明确不做的事

| 风险 | 处理 |
|---|---|
| 契约来源错误导致错误认证 | 只接受机械可保留语义的来源；`hypothesis` 永不认证；68 个真实 PR 的 value 行作为对照回放，任何一条从 yellow 变红即停（RISK-CERT-01 规则） |
| 在 forty 上过拟合 | forty 降为诊断集；Phase 3 才报数字 |
| "自测回放"被当成新能力 | 单独一列，永不并入"新方法才发现" |
| 入口传递让探针更长更贵 | 入口段有界（≤ 4 条），预留按最长提示计算（D-248 的算术） |
| §16 边界 | v6、新来源、付费上限、Phase 2 的容器内依赖（Hypothesis/CrossHair 进镜像）都先问 |

不做：更大模型或多模型讨论臂；恢复 score bar；直接放宽 GENERIC 规则；重新包装 derived probe；bandit 调度；全程序形式化验证。

---

## 8. 需要 owner 决定的三件事（各一个默认）

| | 决定 | 默认 |
|---|---|---|
| A | Phase 0 四项（全部 $0）现在开始；`MAX_SYMBOLS` 按缺陷处理 | **是** |
| B | `attest.intent.v6` 与新的可采信来源（对象式断言、参数化表、docstring Raises）作为 §16 证据类规则批准 | **在 0.3 的数字出来后批准**；数字 < 8 也批（它修的是正确性），但 README 的限制条同步改写 |
| C | 付费：Phase 1 的一次 forty 重跑（≈ $3，现有约 $4 余额内）；Phase 2/3 需把累计上限从 $150 提到约 $180 | **重跑：是；提额：等 Phase 1 的逐例归因** |
