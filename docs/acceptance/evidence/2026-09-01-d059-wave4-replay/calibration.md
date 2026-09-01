# Attest live calibration report

- run: `d059-wave4-replay-9b`
- mode: `live`
- manifest SHA-256: `8f9f90f1ff442d4639f6959faf7701d9e3d05c5863ed48ade6b02e595a8d72d9`
- preregistration SHA-256: `564a87586782db4100ae7a4bceeeaef59cd6e987e53818bcbed007581358965b`
- evaluated cases: 9
- report digest: `674873ba548da752be68bafcc513664da344803a03282992957262e8b6027da7`

## Limitations

- live observation: model responses were sampled from a provider during this run; every figure is one observation under one configuration, not a replayable regression.
- calibration_scope: this report recommends and never mutates production behaviour. Alpha, the S/T/V likelihood ratios, correlation schedules, channel caps, and every other factory statistical constant are untouched by construction; adopting any recommendation is a separate owner decision.
- channel_outcomes: figures conditioned on differential evidence class are empirical counts, not likelihood ratios; they price nothing and must not be read as a channel schedule.
- sample_sufficiency: 0 globally labeled finding(s) are below the 500 minimum, so every output is recommendation_only and a constants patch is prohibited (red line 5).
- accuracy_withheld (validation_receipt_missing): no accuracy figure is published in this report; operational measurements claim no correctness.
- abstentions: 8 case(s) were deferred by the tool. Task state does not erase published precision/harm, positive misses remain deployment misses, and silent non-completed controls are not true negatives.

## Accuracy

no accuracy figure is published (validation_receipt_missing); operational measurements claim no correctness.

## Channel-conditioned outcomes

| evidence class | predictions | surfaced | withheld | matched |
| --- | --- | --- | --- | --- |
| regression_reproduced | 3 | 3 | 0 | null |
| unfaithful | 1 | 1 | 0 | null |

## Differential V fidelity

| measurement | value |
| --- | --- |
| confirmed | 3 |
| confirmed_interval | [0.300642, 0.954413] |
| confirmed_share | 0.75 |
| oracle_receipts | 4 |
| status_counts | {"buggy_fail_fixed_fail": 1, "buggy_fail_fixed_pass": 3} |

## Strata

| source | role | cases | surfaced | abstained |
| --- | --- | --- | --- | --- |
| `source-ace4efb05d87` | historical_bug_replay | 4 | 4 | 8 |

## Latency and cost

| measurement | value |
| --- | --- |
| max_s | 53.389211 |
| mean_s | 41.291788 |
| oracle_spend_total_usd | 0.061592 |
| p50_s | 36.561188 |
| p95_s | 53.389211 |
| per_case_spend_usd | {"case-1e2261dcc6e9": 0.159406, "case-2dad0cb4c5b5": 0.092228, "case-3efff8123ae7": 0.10209, "case-794b97290785": 0.09081, "case-81039ffa0c1e": 0.089118, "case-99a012693940": 0.05368, "case-a8dfb35be49f": 0.15858, "case-c22190aa4fc9": 0.09036, "case-c6f141a2be09": 0.097182} |
| reserved_total_usd | 2.88 |
| spend_total_usd | 0.933454 |
| total_spend_usd | 0.995046 |

## Sample sufficiency

| measurement | value |
| --- | --- |
| constants_patch | prohibited |
| globally_labeled_findings | 0 |
| minimum_required | 500 |
| status | recommendation_only |

## Abstentions

| case | reason |
| --- | --- |
| `case-1e2261dcc6e9` | verification deferred: generation failed: ValueError: generator output does not match the reproduction schema; raw="{}" (1 candidate); generation failed: BudgetExceeded: call 'verify-26f0909dfe-attempt-1' estimated $0.0356; projected total $0.1950 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-b00b8103e8-attempt-1' estimated $0.0358; projected total $0.1952 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-3d189d969f-attempt-1' estimated $0.0357; projected total $0.1951 exceeds budget $0.16 (1 candidate) |
| `case-2dad0cb4c5b5` | verification deferred: generation failed: BudgetExceeded: call 'verify-2e40c12d56-attempt-2' estimated $0.0353; projected total $0.1629 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-709091e9cf-attempt-2' estimated $0.0353; projected total $0.1628 exceeds budget $0.16 (1 candidate) |
| `case-3efff8123ae7` | verification deferred: generation failed: BudgetExceeded: call 'verify-556aeee3f0-attempt-2' estimated $0.0358; projected total $0.1737 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-d39d40325c-attempt-2' estimated $0.0364; projected total $0.1748 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-4c1a894044-attempt-2' estimated $0.0358; projected total $0.1736 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-a8b2174fc5-attempt-2' estimated $0.0358; projected total $0.1737 exceeds budget $0.16 (1 candidate) |
| `case-794b97290785` | verification deferred: generation failed: BudgetExceeded: call 'verify-0d8ee856e5-attempt-2' estimated $0.0364; projected total $0.1636 exceeds budget $0.16 |
| `case-81039ffa0c1e` | verification deferred: indeterminate on head in 3/3 runs; run 1/3: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s)) (1 candidate); unfaithful generated test: fails on base as well (1 candidate) |
| `case-a8dfb35be49f` | verification deferred: generation failed: BudgetExceeded: call 'verify-3fe9882b5b-attempt-1' estimated $0.0353; projected total $0.1938 exceeds budget $0.16 |
| `case-c22190aa4fc9` | verification deferred: generation failed: BudgetExceeded: call 'verify-bdc435222c-attempt-2' estimated $0.0350; projected total $0.1603 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-a7ac85be64-attempt-2' estimated $0.0354; projected total $0.1612 exceeds budget $0.16 (1 candidate); generation failed: BudgetExceeded: call 'verify-2326de620b-attempt-2' estimated $0.0350; projected total $0.1604 exceeds budget $0.16 (1 candidate) |
| `case-c6f141a2be09` | verification deferred: unfaithful generated test: fails on base as well (1 candidate); generation failed: BudgetExceeded: call 'verify-441032dfac-attempt-2' estimated $0.0361; projected total $0.1693 exceeds budget $0.16 (1 candidate) |

## Exclusions

| case | reason |
| --- | --- |
| `case-053ad50c030e` | not_selected |
| `case-0dfad8e3490a` | not_selected |
| `case-14cd88d556a7` | not_selected |
| `case-1e11edb83454` | not_selected |
| `case-33c384091a07` | not_selected |
| `case-3974cec9063e` | not_selected |
| `case-3fa22f0007b2` | not_selected |
| `case-4a83abc6fb64` | not_selected |
| `case-4c3e19ecfc34` | not_selected |
| `case-539065952011` | not_selected |
| `case-643c6f67257c` | not_selected |
| `case-654c1349fddb` | not_selected |
| `case-6739f6f91803` | not_selected |
| `case-689f1f6ba5cd` | not_selected |
| `case-83b8dfb3e08d` | not_selected |
| `case-90f82e09d6ec` | not_selected |
| `case-960455c77ce4` | not_selected |
| `case-aec9f5d922e8` | not_selected |
| `case-afc708bea605` | not_selected |
| `case-ba0769bb4991` | not_selected |
| `case-c09e135b2ac4` | not_selected |
| `case-cb64c2bbd005` | not_selected |
| `case-d36fa1b0fafc` | not_selected |
| `case-d59a6e183767` | not_selected |
| `case-e4ddbad5fcf1` | not_selected |
| `case-e7018060beea` | not_selected |
| `case-e87b0fa4bb23` | not_selected |
| `case-ec15628da25c` | not_selected |
| `case-f3faa30862b2` | not_selected |
| `case-fcbf694e524d` | not_selected |
| `case-fed4a3ef597c` | not_selected |
