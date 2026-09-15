from pathlib import Path
import pkg_resources
pins = Path('/requirements.txt').read_text().splitlines()
assert pins and all(line.count('==') == 1 for line in pins)
for line in pins:
    pkg_resources.require(line)
print('Verified original exact pins:', len(pins), flush=True)
