#!/bin/bash

set -euo pipefail

LABEL=$1
BASE_PYTHON=$2
CHECKOUT=$3
VENV=$4
EVIDENCE=$5
WHEELHOUSE=$6
IMPLEMENTATION_SHA=14a57fb3eeaf7c38f136a5e82151f8d3c738af5b
AUXILIARY="$(dirname "$VENV")/${LABEL}-auxiliary"

mkdir -p "$AUXILIARY"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export COVERAGE_FILE="$AUXILIARY/.coverage"
export MYPY_CACHE_DIR="$AUXILIARY/mypy-cache"
export RUFF_CACHE_DIR="$AUXILIARY/ruff-cache"
unset ANTHROPIC_API_KEY OPENAI_API_KEY GITHUB_TOKEN GH_TOKEN || true

STATUS_FILE="$EVIDENCE/${LABEL}-step-status.tsv"
printf 'step\texit_code\n' > "$STATUS_FILE"

run_step() {
    step=$1
    shift
    log="$EVIDENCE/${LABEL}-${step}.log"
    printf 'label=%s\nstep=%s\ncheckout=%s\ncallable=%s\n' \
        "$LABEL" "$step" "$CHECKOUT" "$*" > "$log"
    printf '%s %s START\n' "$LABEL" "$step"
    set +e
    (
        cd "$CHECKOUT"
        "$@"
    ) >> "$log" 2>&1
    code=$?
    set -e
    printf 'exit_code=%s\n' "$code" > "$EVIDENCE/${LABEL}-${step}.exit"
    printf '%s\t%s\n' "$step" "$code" >> "$STATUS_FILE"
    printf '%s %s EXIT %s\n' "$LABEL" "$step" "$code"
    if [ "$code" -ne 0 ]; then
        printf 'exit_code=%s\nfailed_step=%s\n' "$code" "$step" \
            > "$EVIDENCE/${LABEL}-overall.exit"
        exit "$code"
    fi
}

provenance_step() {
    echo '$ git rev-parse HEAD HEAD^ HEAD^{tree}'
    git rev-parse HEAD HEAD^ 'HEAD^{tree}'
    echo '$ git symbolic-ref -q HEAD (detached is expected)'
    if git symbolic-ref -q HEAD; then
        return 1
    else
        test "$?" -eq 1
    fi
    echo '$ base interpreter and platform'
    "$BASE_PYTHON" --version
    "$BASE_PYTHON" -c 'import platform, sys; print(sys.executable); print(platform.platform()); print(platform.machine())'
    sw_vers
    uname -a
    echo '$ lock and wheelhouse digests'
    shasum -a 256 requirements-toolchain.lock
    (cd "$WHEELHOUSE" && shasum -a 256 * | shasum -a 256)
    test "$(git rev-parse HEAD)" = "$IMPLEMENTATION_SHA"
}

status_before_step() {
    echo '$ git diff --check'
    git diff --check
    echo '$ git status --porcelain=v1'
    git status --porcelain=v1
    test -z "$(git status --porcelain=v1)"
}

v1_integrity_step() {
    receipt_expected=e8cabb89471bb369a93ce82399a342eaddbf7ed8994d5420aef66256d013ce40
    results_expected=e90b2acfb9753db196cd7d2cf999dc2fa24bbd91bb84d908b476682c1b441288
    protocol_expected=2a6019533a1c01abbf905e57b0b15017b806aeeee6028e496b0149a4a1f2246c
    receipt_actual=$(shasum -a 256 benchmarks/attest-v1/receipt.json | awk '{print $1}')
    results_actual=$(shasum -a 256 benchmarks/attest-v1/validation-results.json | awk '{print $1}')
    protocol_actual=$(shasum -a 256 benchmarks/attest-v1/protocol.md | awk '{print $1}')
    printf 'receipt expected=%s actual=%s\n' "$receipt_expected" "$receipt_actual"
    printf 'results expected=%s actual=%s\n' "$results_expected" "$results_actual"
    printf 'protocol expected=%s actual=%s\n' "$protocol_expected" "$protocol_actual"
    test "$receipt_actual" = "$receipt_expected"
    test "$results_actual" = "$results_expected"
    test "$protocol_actual" = "$protocol_expected"
}

install_step() {
    echo '$ BASE_PYTHON -m venv VENV'
    "$BASE_PYTHON" -m venv "$VENV"
    echo '$ python -m pip install --no-index --find-links WHEELHOUSE -r requirements-toolchain.lock'
    "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" \
        -r "$CHECKOUT/requirements-toolchain.lock"
    echo '$ python -m pip install --no-index --find-links WHEELHOUSE --no-deps --no-build-isolation -e CHECKOUT'
    "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" \
        --no-deps --no-build-isolation -e "$CHECKOUT"
    echo '$ python -m pip check'
    "$VENV/bin/python" -m pip check
}

freeze_step() {
    echo '$ python -m pip freeze --all'
    "$VENV/bin/python" -m pip freeze --all
}

runtime_step() {
    echo '$ python --version'
    "$VENV/bin/python" --version
    echo '$ current_runtime_identity()'
    "$VENV/bin/python" -c \
        'import json, platform, sys; from dataclasses import asdict; from attest.benchmark.api import current_runtime_identity; print(json.dumps({"executable": sys.executable, "version": sys.version, "platform": platform.platform(), "machine": platform.machine(), "runtime_identity": asdict(current_runtime_identity())}, sort_keys=True))'
}

focused_step() {
    echo '$ pytest focused M-02 corpus/artifact/report files'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q \
        tests/benchmark/test_corpus.py \
        tests/benchmark/test_artifacts.py \
        tests/benchmark/test_report.py
}

gcode002_step() {
    echo '$ pytest G-CODE-002 mutation/guard-removal corpus'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q \
        tests/benchmark/test_artifacts.py::test_verify_rejects_unknown_or_mistyped_manifest_fields \
        tests/benchmark/test_corpus.py::test_validation_v2_exclusion_attempt_fields_have_semantic_teeth \
        tests/benchmark/test_corpus.py::test_validation_v2_binding_artifact_fields_have_semantic_teeth \
        tests/benchmark/test_corpus.py::test_validation_v2_artifact_record_fields_fail_closed_at_exact_path \
        tests/benchmark/test_corpus.py::test_validation_v2_attempt_and_run_field_mutations_remove_authority
}

m03_regressions_step() {
    echo '$ pytest M-03 role/checkpoint/live/stability/comparison regressions'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q \
        tests/test_phase3_acceptance.py \
        tests/benchmark/test_checkpoints.py \
        tests/benchmark/test_live.py \
        tests/benchmark/test_stability.py \
        tests/benchmark/test_api.py \
        tests/benchmark/test_baselines.py
}

benchmark_step() {
    echo '$ pytest all benchmark tests'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q tests/benchmark
}

full_step() {
    echo '$ pytest full repository'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q
}

coverage_step() {
    echo '$ pytest full repository with source coverage'
    "$VENV/bin/python" -m pytest -p no:cacheprovider -q \
        --cov=src/attest --cov-report=term-missing
    echo '$ coverage report for attest.core with fail-under=99'
    "$VENV/bin/python" -m coverage report --include='src/attest/core/*' \
        --fail-under=99
}

ruff_step() {
    echo '$ ruff check .'
    "$VENV/bin/python" -m ruff check .
}

mypy_step() {
    echo '$ mypy src/attest'
    "$VENV/bin/python" -m mypy src/attest
}

pip_check_step() {
    echo '$ python -m pip check'
    "$VENV/bin/python" -m pip check
}

diff_check_step() {
    echo '$ git diff --check'
    git diff --check
}

status_after_step() {
    echo '$ git rev-parse HEAD'
    git rev-parse HEAD
    echo '$ git status --porcelain=v1'
    git status --porcelain=v1
    test "$(git rev-parse HEAD)" = "$IMPLEMENTATION_SHA"
    test -z "$(git status --porcelain=v1)"
}

run_step provenance provenance_step
run_step status-before status_before_step
run_step v1-integrity v1_integrity_step
run_step install install_step
run_step freeze freeze_step
run_step runtime runtime_step
run_step focused focused_step
run_step gcode002 gcode002_step
run_step m03-regressions m03_regressions_step
run_step benchmark benchmark_step
run_step full full_step
run_step coverage coverage_step
run_step ruff ruff_step
run_step mypy mypy_step
run_step pip-check pip_check_step
run_step diff-check diff_check_step
run_step status-after status_after_step
printf 'exit_code=0\n' > "$EVIDENCE/${LABEL}-overall.exit"
printf '%s COMPLETE\n' "$LABEL"
