#!/usr/bin/env python3
"""
Parse powerup.txt (extracted from data/DATA.TWT) into a powerup id -> name mapping.

Format per entry:
  // Powerup N
  <blank>
  <description text>
  <icon name>   // Icon
  ... more fields ...

We just need the id and the description line.
"""
import os
import re

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'powerup.txt')

def main():
    with open(PATH) as f:
        text = f.read()

    lines = text.splitlines()
    powerups = {}

    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'//\s*Powerup\s+(\d+)', line)
        if m:
            idx = int(m.group(1))
            # Next non-blank non-comment line is the description
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('//')):
                j += 1
            if j < len(lines):
                desc = lines[j].strip()
                powerups[idx] = desc
            i = j
        i += 1

    print(f'Parsed {len(powerups)} powerups')
    for idx in sorted(powerups):
        print(f'  [{idx:3d}] {powerups[idx]}')

    # Save as python dict
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'powerup_names.py')
    with open(out_path, 'w') as f:
        f.write('# Auto-generated from data/DATA.TWT/POWERUP.TXT.\n')
        f.write('# Powerup id -> description (the text shown on-screen when triggered).\n')
        f.write('\n')
        f.write('POWERUP_NAMES = {\n')
        for idx in sorted(powerups):
            desc = powerups[idx].replace("'", "\\'")
            f.write(f'    {idx:3d}: {repr(powerups[idx])},\n')
        f.write('}\n')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
