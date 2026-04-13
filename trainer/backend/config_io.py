"""
Read/write dgVoodoo.conf and data/OPTIONS.TXT.

Both use surgical line replacement to preserve comments, formatting,
and sections the trainer doesn't manage.
"""
import os
import re


# ---------------------------------------------------------------------------
# dgVoodoo.conf — INI-style with [Section] headers
# ---------------------------------------------------------------------------

def read_dgvoodoo(game_dir: str) -> dict[str, dict[str, str]]:
    """Read dgVoodoo.conf into {section: {key: value}}."""
    path = os.path.join(game_dir, 'dgVoodoo.conf')
    result: dict[str, dict[str, str]] = {}
    if not os.path.isfile(path):
        return result
    section = ''
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n\r')
            s = line.strip()
            if s.startswith('[') and ']' in s:
                section = s[1:s.index(']')]
                result.setdefault(section, {})
            elif '=' in s and not s.startswith(';'):
                key, _, val = s.partition('=')
                result.setdefault(section, {})[key.strip()] = val.strip()
    return result


def write_dgvoodoo(game_dir: str, changes: dict[str, dict[str, str]]) -> bool:
    """Write changes to dgVoodoo.conf with surgical line replacement.

    changes = {section: {key: new_value}}. Only touched keys are modified.
    Preserves all comments, blank lines, and alignment.
    """
    path = os.path.join(game_dir, 'dgVoodoo.conf')
    if not os.path.isfile(path):
        return False
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    section = ''
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('[') and ']' in s:
            section = s[1:s.index(']')]
        elif '=' in s and not s.startswith(';') and section in changes:
            key, _, _ = s.partition('=')
            key = key.strip()
            if key in changes[section]:
                # Find the '=' position and preserve left-side alignment
                eq_pos = line.index('=')
                new_val = changes[section][key]
                lines[i] = line[:eq_pos + 1] + ' ' + new_val + '\n'

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except (PermissionError, OSError):
        return False


# Also update the bundled copy so ensure_dgvoodoo doesn't overwrite
def write_dgvoodoo_bundled(trainer_dir: str, changes: dict[str, dict[str, str]]) -> bool:
    """Write same changes to the bundled deps/dgvoodoo/dgVoodoo.conf."""
    bundled = os.path.join(trainer_dir, 'deps', 'dgvoodoo', 'dgVoodoo.conf')
    if not os.path.isfile(bundled):
        return False
    game_dir_fake = os.path.dirname(bundled)
    # Temporarily copy to match write_dgvoodoo's path expectation
    return write_dgvoodoo(os.path.dirname(bundled), changes)


# ---------------------------------------------------------------------------
# data/OPTIONS.TXT — line-based "Key Value" format
# ---------------------------------------------------------------------------

def read_options_txt(game_dir: str) -> dict[str, str]:
    """Read OPTIONS.TXT into {key: value}. Stops at first NETSETTINGS block."""
    path = os.path.join(game_dir, 'data', 'OPTIONS.TXT')
    result: dict[str, str] = {}
    if not os.path.isfile(path):
        return result
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.strip()
            if s.startswith('NETSETTINGS'):
                break
            parts = s.split(None, 1)
            if len(parts) == 2 and not s.startswith('//'):
                result[parts[0]] = parts[1]
    return result


def write_options_txt(game_dir: str, changes: dict[str, str]) -> bool:
    """Write changes to OPTIONS.TXT with surgical line replacement.

    Only modifies lines before the first NETSETTINGS block.
    """
    path = os.path.join(game_dir, 'data', 'OPTIONS.TXT')
    if not os.path.isfile(path):
        return False
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    in_net = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('NETSETTINGS'):
            in_net = True
        if in_net:
            continue
        parts = s.split(None, 1)
        if len(parts) >= 1 and parts[0] in changes:
            new_val = changes[parts[0]]
            lines[i] = f'{parts[0]} {new_val}\n'

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except (PermissionError, OSError):
        return False
