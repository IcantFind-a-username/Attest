# The gate level's shadow, extended — 2026-09-06c

Owner instruction 6 of this window: **run the gate level in shadow, head-only, on the 11 forward
pairs and on the most recent 10 commits of each of the three owner repositories; record the shadow
in the ledger with the witness type (`through_caller` / `direct`); give a table of candidates,
reachability and shadow findings, each with its three coordinates; and add the total to
`G-NEWCODE-001`'s pilot progress.**

**Spend `$0.2803` of a `$2.50` reservation**, all of it `corum`'s ten commits. The 11 forward
pairs cost **`$0.00`** — the witness is a free static read over the candidates the 2026-09-06b
probe run already recorded, so nothing is bought twice — and `attest` and `us-stock-helper` are
covered by [the four-level run](2026-09-06c-four-levels.md)'s own units.

**Nothing on this path is author-visible** (D-137). The output is a grade, three coordinates and
a ledger row; no `CertifiedFinding` is constructed and no GitHub client exists.

Data: [forward pairs](evidence/2026-09-06c-gate-shadow-forward.json) ·
[`attest`](evidence/2026-09-06c-four-levels-attest.json) ·
[`us-stock-helper`](evidence/2026-09-06c-four-levels-us-stock-helper.json) ·
[`corum`](evidence/2026-09-06c-four-levels-corum.json).

## 1. Candidates, reachability, shadow findings

| population | units | new-code candidates | admissible | **`through_caller`** | `direct` |
|---|---|---|---|---|---|
| 11 forward pairs | 11 | 25 | 12 | **3** | 0 |
| `attest`, most recent 10 (of the 20 reviewed) | 20 | 41 | 15 | **3** | 0 |
| `us-stock-helper`, most recent 10 (of the 20 reviewed) | 20 | 20 | 0 | **0** | 0 |
| `corum`, most recent 10 | 10 | 4 | 3 | **3** | 0 |
| **this window** | **61** | **90** | **30** | **9** | **0** |

`attest` and `us-stock-helper` are reported over all 20 commits each rather than the 10 the
instruction names, because the four-level run bought 20 and reporting only half of a population
that is already paid for would throw away evidence for no reason. The instruction's 10 are a
prefix of these.

## 2. `G-NEWCODE-001`'s pilot progress, cumulatively

| population | new-code candidates | **`through_caller`** | `direct` |
|---|---|---|---|
| E-04 stratum v2 (2026-09-05, [report](2026-09-05-gate-shadow.md)) | 224 | **0** | 0 |
| this window (above) | 90 | **9** | 0 |
| **cumulative** | **314** | **9** (2.9%) | **0** |

**The 2026-09-05 run's "0 of 224" is retired as the whole record, and the reason it was zero is
now visible.** That run reached a reproduction on nothing — every attempt DEFERred on the host
container fault — so `through_caller` could not be graded at all; what it measured was the
*static* half. This window's 9 are the first observations at the publishing grade.

**2.9% is a ceiling on how often the gate level could speak if it were live**, not a rate at
which it would be right. Nine observations decide nothing about precision.

## 3. What the nine `through_caller` grades actually say

Three of the nine are on one `corum` commit and enter through a **test**
(`tests/test_fusion.py:859`), not through production code. The grade does not distinguish "a
caller outside the added lines" from "a caller that is itself a test", and it should: a new
function reached only by its own new test has a caller in the letter of D-137 and not in its
spirit — the whole point of the through-caller rule is that *something the change did not add*
depends on the new code.

**Recorded as an open question, not fixed**, for the same reason §4 of the value-class
adjudication gives: inventing a clause inside a measurement is how a rule ends up with a
condition nobody measured. It is a one-line change (`site.is_test` is already computed) and it
would take the cumulative count from 9 to 6.

## 4. Every candidate, with its three coordinates

| population | commit | candidate | symbol | witness | admissible | why |
|---|---|---|---|---|---|---|
| forward pair `click` | `0585f456ba` | `src/click/termui.py:145` | `_is_expected_type` | — | no | no call site of `_is_expected_type` outside the added lines and no documented  |
| forward pair `click` | `cd4674a6de` | `src/click/_termui_impl.py:391` | `__init__` | **through-caller** | yes | the reproduction enters at src/click/_compat.py:69 and `__init__` runs underne |
| forward pair `click` | `cd4674a6de` | `src/click/_termui_impl.py:424` | `_pager_contextmanager` | — | no | no call site of `_pager_contextmanager` outside the added lines and no documen |
| forward pair `click` | `cd4674a6de` | `src/click/_termui_impl.py:439` | `get_pager_file` | — | yes | the reproduction neither calls `get_pager_file` nor enters at a call site of i |
| forward pair `click` | `cd4674a6de` | `src/click/_textwrap.py:108` | `_wrap_chunks` | — | yes | the reproduction neither calls `_wrap_chunks` nor enters at a call site of it |
| forward pair `click` | `cd4674a6de` | `src/click/_textwrap.py:118` | `_wrap_chunks` | — | yes | the reproduction neither calls `_wrap_chunks` nor enters at a call site of it |
| forward pair `click` | `cd4674a6de` | `src/click/exceptions.py:26` | `_format_possibilities` | — | no | no call site of `_format_possibilities` outside the added lines and no documen |
| forward pair `click` | `cd4674a6de` | `src/click/exceptions.py:258` | `__init__` | **through-caller** | yes | the reproduction enters at src/click/_compat.py:69 and `__init__` runs underne |
| forward pair `click` | `cd4674a6de` | `src/click/exceptions.py:264` | `__init__` | **through-caller** | yes | the reproduction enters at src/click/_compat.py:69 and `__init__` runs underne |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:63` | `_mask_hidden_input` | — | yes | the reproduction neither calls `_mask_hidden_input` nor enters at a call site  |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:68` | `_mask_hidden_input` | — | yes | the reproduction neither calls `_mask_hidden_input` nor enters at a call site  |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:69` | `_mask_hidden_input` | — | yes | the reproduction neither calls `_mask_hidden_input` nor enters at a call site  |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:73` | `_mask_hidden_input` | — | yes | the reproduction neither calls `_mask_hidden_input` nor enters at a call site  |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:91` | `_readline_prompt` | — | yes | the reproduction neither calls `_readline_prompt` nor enters at a call site of |
| forward pair `click` | `cd4674a6de` | `src/click/termui.py:301` | `get_pager_file` | — | yes | the reproduction neither calls `get_pager_file` nor enters at a call site of i |
| forward pair `click` | `cd4674a6de` | `src/click/types.py:516` | `` | — | no | the failing line is not inside a definition, or the head source does not parse |
| forward pair `click` | `cd4674a6de` | `tests/test_commands.py:591` | `test_suggest_possible_commands` | — | no | unannotated parameter(s) runner, value, expect of `test_suggest_possible_comma |
| forward pair `click` | `cd4674a6de` | `tests/test_options.py:3211` | `test_flag_group_unset_vs_none_vs_explicit` | — | no | unannotated parameter(s) runner, default_a, default_b, args, expected of `test |
| forward pair `click` | `cd4674a6de` | `tests/test_options.py:3238` | `test_flag_group_competition_duplicate_option_name` | — | no | unannotated parameter(s) runner of `test_flag_group_competition_duplicate_opti |
| forward pair `click` | `cd4674a6de` | `tests/test_options.py:3247` | `test_flag_group_competition_duplicate_option_name` | — | no | unannotated parameter(s) runner of `test_flag_group_competition_duplicate_opti |
| forward pair `click` | `cd4674a6de` | `tests/test_testing.py:574` | `test_capture_fd_stale_reference` | — | no | `test_capture_fd_stale_reference` takes no parameter: there is no domain to be |
| forward pair `click` | `cd4674a6de` | `tests/test_testing.py:576` | `test_capture_fd_stale_reference` | — | no | `test_capture_fd_stale_reference` takes no parameter: there is no domain to be |
| forward pair `click` | `cd4674a6de` | `tests/test_testing.py:602` | `test_capture_fd_logging_handler` | — | no | unannotated parameter(s) tmp_path of `test_capture_fd_logging_handler`: an inp |
| forward pair `click` | `cd4674a6de` | `tests/test_testing.py:631` | `test_capture_fd_logging_handler` | — | no | unannotated parameter(s) tmp_path of `test_capture_fd_logging_handler`: an inp |
| forward pair `click` | `cd4674a6de` | `tests/test_testing.py:707` | `outer_cli` | — | no | `outer_cli` takes no parameter: there is no domain to be inside |
| attest `attest` | `eede42194d` | `src/attest/review/impact.py:226` | `_raised_types` | — | no | no call site of `_raised_types` outside the added lines and no documented doma |
| attest `attest` | `eede42194d` | `src/attest/review/impact.py:515` | `arity_breaks_of` | — | no | no call site of `arity_breaks_of` outside the added lines and no documented do |
| attest `attest` | `eede42194d` | `src/attest/review/impact.py:522` | `arity_breaks_of` | — | no | no call site of `arity_breaks_of` outside the added lines and no documented do |
| attest `attest` | `eede42194d` | `src/attest/review/impact.py:528` | `arity_breaks_of` | — | no | no call site of `arity_breaks_of` outside the added lines and no documented do |
| attest `attest` | `150804a34b` | `src/attest/github/presentation.py:186` | `_anchored` | **through-caller** | yes | the reproduction enters at src/attest/review/executor.py:2216 and `_anchored`  |
| attest `attest` | `150804a34b` | `src/attest/github/presentation.py:188` | `_anchored` | **through-caller** | yes | the reproduction enters at src/attest/review/executor.py:2216 and `_anchored`  |
| attest `attest` | `48b418c895` | `src/attest/review/executor.py:980` | `generate_probe` | — | yes | the reproduction neither calls `generate_probe` nor enters at a call site of i |
| attest `attest` | `48b418c895` | `src/attest/review/executor.py:1854` | `_record_on_base` | — | yes | the reproduction neither calls `_record_on_base` nor enters at a call site of  |
| attest `attest` | `48b418c895` | `src/attest/review/executor.py:1856` | `_record_on_base` | — | yes | the reproduction neither calls `_record_on_base` nor enters at a call site of  |
| attest `attest` | `48b418c895` | `src/attest/review/executor.py:1876` | `_record_on_base` | — | yes | the reproduction neither calls `_record_on_base` nor enters at a call site of  |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1050` | `_changed_line_numbers` | — | no | no call site of `_changed_line_numbers` outside the added lines and no documen |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1080` | `_base_source` | — | no | no call site of `_base_source` outside the added lines and no documented domai |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1082` | `_base_source` | — | no | no call site of `_base_source` outside the added lines and no documented domai |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1091` | `impact_notes` | — | yes | the reproduction neither calls `impact_notes` nor enters at a call site of it |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1093` | `impact_notes` | — | yes | the reproduction neither calls `impact_notes` nor enters at a call site of it |
| attest `attest` | `c88f67e599` | `src/attest/review/ci.py:1123` | `impact_notes` | — | yes | the reproduction neither calls `impact_notes` nor enters at a call site of it |
| attest `attest` | `820b973d09` | `src/attest/review/impact.py:385` | `_addressable_name` | — | no | no call site of `_addressable_name` outside the added lines and no documented  |
| attest `attest` | `820b973d09` | `src/attest/review/impact.py:388` | `_addressable_name` | — | no | no call site of `_addressable_name` outside the added lines and no documented  |
| attest `attest` | `820b973d09` | `src/attest/review/impact.py:391` | `_addressable_name` | — | no | no call site of `_addressable_name` outside the added lines and no documented  |
| attest `attest` | `8c0ceaf22d` | `src/attest/review/output_contract.py:147` | `_pattern` | — | yes | the reproduction neither calls `_pattern` nor enters at a call site of it |
| attest `attest` | `8c0ceaf22d` | `src/attest/review/output_contract.py:148` | `_pattern` | — | yes | the reproduction neither calls `_pattern` nor enters at a call site of it |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:160` | `is_test_path` | **through-caller** | yes | the reproduction enters at src/attest/review/structural.py:263 and `is_test_pa |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:176` | `_signature` | — | no | no call site of `_signature` outside the added lines and no documented domain |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:274` | `build_call_graph` | — | no | no call site of `build_call_graph` outside the added lines and no documented d |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:304` | `read_tree` | — | no | no call site of `read_tree` outside the added lines and no documented domain |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:316` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:327` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:342` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:345` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:358` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:361` | `changed_functions` | — | no | no call site of `changed_functions` outside the added lines and no documented  |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:371` | `_named_by_test` | — | yes | the reproduction neither calls `_named_by_test` nor enters at a call site of i |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:380` | `_named_by_test` | — | yes | the reproduction neither calls `_named_by_test` nor enters at a call site of i |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:384` | `_named_by_test` | — | yes | the reproduction neither calls `_named_by_test` nor enters at a call site of i |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:396` | `callers_of` | — | no | no call site of `callers_of` outside the added lines and no documented domain |
| attest `attest` | `84c75985a0` | `src/attest/review/impact.py:397` | `callers_of` | — | no | no call site of `callers_of` outside the added lines and no documented domain |
| attest `attest` | `6579a8fec7` | `tests/test_null_study_stop_rule.py:30` | `null_study` | — | no | `null_study` takes no parameter: there is no domain to be inside |
| attest `attest` | `6579a8fec7` | `tests/test_null_study_stop_rule.py:54` | `test_a_probe_on_one_interpreter_is_not_an_adjudication` | — | no | no call site of `test_a_probe_on_one_interpreter_is_not_an_adjudication` outsi |
| attest `attest` | `6579a8fec7` | `tests/test_null_study_stop_rule.py:60` | `test_a_probe_on_one_interpreter_is_not_an_adjudication` | — | no | no call site of `test_a_probe_on_one_interpreter_is_not_an_adjudication` outsi |
| attest `attest` | `6579a8fec7` | `tests/test_null_study_stop_rule.py:62` | `test_a_probe_on_one_interpreter_is_not_an_adjudication` | — | no | no call site of `test_a_probe_on_one_interpreter_is_not_an_adjudication` outsi |
| attest `attest` | `6579a8fec7` | `tests/test_null_study_stop_rule.py:76` | `_log` | — | no | no call site of `_log` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `3f6b67b0b6` | `services/information_layer/information_layer/feeds/nasdaq.py:79` | `_parse_eastern_stamp` | — | no | no call site of `_parse_eastern_stamp` outside the added lines and no document |
| us-stock-helper `us-stock-helper` | `3f6b67b0b6` | `services/information_layer/information_layer/feeds/nasdaq.py:80` | `_parse_eastern_stamp` | — | no | no call site of `_parse_eastern_stamp` outside the added lines and no document |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:134` | `_load_runtime_environment` | — | no | `_load_runtime_environment` takes no parameter: there is no domain to be insid |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:138` | `_load_runtime_environment` | — | no | `_load_runtime_environment` takes no parameter: there is no domain to be insid |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:142` | `_warn_if_outside_market_hours` | — | no | no call site of `_warn_if_outside_market_hours` outside the added lines and no |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:155` | `_measure` | — | no | no call site of `_measure` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:180` | `recording_extract` | — | no | unannotated parameter(s) args, kwargs of `recording_extract`: an input outside |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:199` | `_measure` | — | no | no call site of `_measure` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:205` | `_measure` | — | no | no call site of `_measure` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:216` | `_measure` | — | no | no call site of `_measure` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `540b0a8154` | `.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py:217` | `_measure` | — | no | no call site of `_measure` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:50` | `load_coordinator` | — | no | `load_coordinator` takes no parameter: there is no domain to be inside |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:60` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:70` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:76` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:78` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:80` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `4ef2226bcf` | `services/analysis_api/src/us_stock_helper_analysis_api/coordinator_state.py:80` | `save` | — | no | no call site of `save` outside the added lines and no documented domain |
| us-stock-helper `us-stock-helper` | `8cfab6c5a7` | `services/information_layer/tests/test_adapters.py:747` | `fixture_bytes` | — | no | no call site of `fixture_bytes` outside the added lines and no documented doma |
| us-stock-helper `us-stock-helper` | `8cfab6c5a7` | `services/information_layer/tests/test_adapters.py:847` | `test_a_filed_by_entry_claims_no_symbol_even_when_the_holder_is_listed` | — | no | `test_a_filed_by_entry_claims_no_symbol_even_when_the_holder_is_listed` takes  |
| corum `corum` | `14c363ddf1` | `src/corum/fusion.py:106` | `_validated_joint_likelihood` | — | no | no call site of `_validated_joint_likelihood` outside the added lines and no d |
| corum `corum` | `14c363ddf1` | `src/corum/fusion.py:494` | `fuse_known_pair_likelihoods` | **through-caller** | yes | the reproduction enters at tests/test_fusion.py:859 and `fuse_known_pair_likel |
| corum `corum` | `14c363ddf1` | `src/corum/fusion.py:505` | `fuse_known_pair_likelihoods` | **through-caller** | yes | the reproduction enters at tests/test_fusion.py:859 and `fuse_known_pair_likel |
| corum `corum` | `14c363ddf1` | `src/corum/fusion.py:511` | `fuse_known_pair_likelihoods` | **through-caller** | yes | the reproduction enters at tests/test_fusion.py:859 and `fuse_known_pair_likel |

rows: 90
