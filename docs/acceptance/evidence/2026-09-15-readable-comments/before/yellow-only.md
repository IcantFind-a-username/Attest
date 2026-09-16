Observed behaviour changes — the same call run on both revisions; no defect is claimed and nothing in the base tree pins either value:
- [yellow] loguru/_string_parsers.py:162 — for _string_parsers.parse_duration('1e400s'), the merge base raised OverflowError and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 377e1f399cab

- [yellow] loguru/_datetime.py:112 — for format(dt, 'x'), the merge base returned '-500000' and head returns '-1500000' (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 19dbf722bdfb
Spend $0.0000; 0.0s.
