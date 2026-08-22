#!/usr/bin/env python3
"""Verify the test suite has teeth, by breaking detect.py on purpose.

A suite that never fails proves nothing. Each mutation below reintroduces a
bug that was actually shipped and fixed, or disables a deliberate behaviour.
Every one must cause at least one test to fail. A mutation that survives means
the suite does not cover that behaviour — which is how the clustering gap was
found: mixed_draft.md passed with the fix reverted, because another fix
independently supplied the same paragraph's third pattern.

    python3 tests/mutate.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
TARGET = os.path.join(SCRIPTS, "detect.py")

# (description, needle, replacement)
MUTATIONS = [
    ("clustering ignores low document-rate patterns",
     'if f.key in WEAK_FOR_CONVERGENCE:',
     'if f.severity == "info" or f.key in WEAK_FOR_CONVERGENCE:'),

    ("citation window crosses paragraph breaks",
     'window = re.split(r"\\n\\s*\\n", window)[0]',
     'window = window'),

    ("tricolon accepts any three-item list",
     'if sum(_is_rhetorical_item(p) for p in parts) < 2:',
     'if False:'),

    ("tricolon stops excluding proper nouns",
     'if parts[1][0].isupper() or parts[2][0].isupper():',
     'if False:'),

    ("tricolon stops excluding list items",
     'if doc.line_of(m.start()) in list_item_lines:',
     'if False:'),

    ("code fences are no longer masked",
     'r"^(```|~~~).*?(?:\\n(?:.*?)\\n\\1\\s*$|\\Z)"',
     'r"(?!x)x"'),

    ("inline code is no longer masked",
     'for m in re.finditer(r"`[^`\\n]+`", raw):',
     'for m in re.finditer(r"(?!x)x", raw):'),

    ("rhythm uses stdev instead of spread",
     'spread = (max(lens) - min(lens)) / statistics.mean(lens)',
     'spread = _burstiness(lens) or 0.0'),

    ("hedge check drops its clause-boundary guard",
     'r"(?:^|(?<=[.!?]\\s)|(?<=\\n))\\s*That (?:being )?said,"',
     'r"\\bthat (?:being )?said\\b"'),

    ("negative parallelism loses uncontracted forms",
     'r"\\b(?:is|are|was|were|am|be|been|being)\\s+not\\s+"',
     'r"(?!x)x" + "" or '),

    ("scan_regexes keeps the first match rather than the longest",
     'if prev is None or len(text) > len(prev.group(0)):',
     'if prev is None:'),
]


def run_suite():
    r = subprocess.run([sys.executable, os.path.join(HERE, "run_tests.py")],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip().split("\n")[-1]


def main():
    backup = tempfile.mktemp(suffix=".py")
    shutil.copy(TARGET, backup)
    original = open(TARGET).read()

    code, line = run_suite()
    if code != 0:
        print(f"baseline is already failing: {line}")
        print("fix the suite before running mutations")
        return 2
    print(f"baseline: {line}\n")

    survived, skipped = [], []
    try:
        for desc, needle, repl in MUTATIONS:
            if needle not in original:
                skipped.append(desc)
                print(f"  SKIP    {desc} (target not found)")
                continue
            with open(TARGET, "w") as fh:
                fh.write(original.replace(needle, repl, 1))
            code, line = run_suite()
            if code == 0:
                survived.append(desc)
                print(f"  SURVIVED {desc}")
            else:
                print(f"  caught  {desc}")
    finally:
        shutil.copy(backup, TARGET)
        os.unlink(backup)

    total = len(MUTATIONS) - len(skipped)
    print(f"\n{total - len(survived)}/{total} mutations caught")
    if skipped:
        print(f"{len(skipped)} skipped — detect.py has drifted from the "
              f"mutation targets; update them.")
    if survived:
        print("\nUncovered behaviour:")
        for d in survived:
            print(f"  {d}")
        return 1
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
