# Resolution of the single independent pass

Reviewed driver: `7e37a41`. Corrected measured driver: `40308c5`.

- Isolated build versions: confirmed by command dataflow. The corrected command
  uses `--no-clean --verbose`, retains distribution METADATA from the isolated
  environment, and exports it alongside the wheel and outer environment record.
  The first successful build's archive contains the actual backend distributions;
  it includes NumPy 1.21.6 and Cython 0.29.30, unlike an outer pip freeze.
- Per-case manifest exceptions: confirmed from dictionary indexing. KeyError and
  TypeError are now case refusals and do not stop subsequent attempts. This was a
  harness diagnosis, not a claim that selected manifests were malformed.

Both changes affect evidence collection only. No dependency constraints, source,
selection, certification or runtime permissions changed. The interrupted first
invocation is retained; no behavioral outcome was used for a repair. There was no
second independent review. Ruff and diff checks passed on the corrected script;
the subsequent actual builds validate the metadata retention path. No full product
gate is claimed for this diagnostic-only work.
