# Existing font-cache preparation in the source runtime

This is a collection repair before any original behavioral outcome. Preserve the
prior original-test failure record: four executions collected zero tests because
font initialization attempted a disabled thread; one pair lacked its original
upstream test module. No original parent PASS/head FAIL witness was obtained.

Use swebench_source_runtime.py --study remainder-font-cache once, committed and
independently reviewed first. Fresh output is remainder-font-cache-runtime. Reuse
all twelve frozen revisions, wheels, constraints, images and source-only transfer
from setup-declaration-runtime.md; no new sample or dependency recipe.

Reuse the existing D-214/MPL_SEED_DIR mechanism. For a source tree providing the
matplotlib package, copy the materialized original tree into the build image at
its runtime path, and import matplotlib.font_manager during image preparation
with the source root on sys.path. This step has Docker build networking disabled,
uses no oracle overlay, and must succeed. Use a disposable build stage: retain only the generated font cache at the
existing seed location, make it readable, and copy only that cache into the clean
dependency image. Source execution cannot carry interpreter or dependency changes
from the warm-up stage into the runtime image. The runtime
still mounts fresh original source, contains no installed project distribution,
and uses the existing launcher to copy the seed to writable scratch. Do not mock
threading or allow threads/processes during evidence execution. No source patch.

Record bounded regular cache file digests; refuse links, empty or excessive cache
artifacts. Images bind the prepared cache. The native fixture runs first under the
same arm; non-matplotlib trees use their unchanged recipe. All twelve readiness
rows and errors remain. This does not repair Django's subprocess restriction.
Runtime readiness is not a behavioral witness, receipt, recall or paid evaluation.
