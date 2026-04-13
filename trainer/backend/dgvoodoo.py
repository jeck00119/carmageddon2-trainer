"""dgVoodoo 2 wrapper management — detection, installation, verification."""
import os
import shutil

DGVOODOO_BUNDLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deps', 'dgvoodoo')
DGVOODOO_FILES = [
    ('Glide.dll',       'glide.dll'),
    ('Glide2x.dll',     'glide2x.dll'),
    ('Glide3x.dll',     'glide3x.dll'),
    ('dgVoodoo.conf',   'dgVoodoo.conf'),
    ('dgVoodooCpl.exe', 'dgVoodooCpl.exe'),
]

_DGVOODOO_MAGIC = 'dgVoodoo'.encode('utf-16-le')


def is_dgvoodoo_glide(path: str) -> bool:
    """Check if a glide2x.dll is dgVoodoo's by looking for its VERSIONINFO signature."""
    try:
        if not os.path.isfile(path):
            return False
        size = os.path.getsize(path)
        if not (100_000 <= size <= 400_000):
            return False
        with open(path, 'rb') as f:
            data = f.read()
        return _DGVOODOO_MAGIC in data
    except Exception:
        return False


def check_wrapper(game_dir: str) -> dict:
    """Detect which Glide wrapper is installed in the game folder."""
    result = {'type': 'none', 'ok': False, 'path': ''}
    if not game_dir:
        return result
    dll = os.path.join(game_dir, 'glide2x.dll')
    if not os.path.isfile(dll):
        return result
    result['path'] = dll
    if is_dgvoodoo_glide(dll):
        result['type'] = 'dgvoodoo'
        result['ok'] = True
    else:
        result['type'] = 'other'
        result['ok'] = os.path.getsize(dll) > 100_000
    return result


def ensure_dgvoodoo(game_dir: str) -> bool:
    """Install the bundled dgVoodoo 2 Glide wrapper into the game folder.

    Idempotent: if the installed glide2x.dll already matches the bundled
    version (by dgVoodoo signature), only restores missing companion files.
    Backs up existing glide*.dll to glide*.dll.bak_nglide before overwriting.
    """
    if not game_dir or not os.path.isdir(game_dir):
        return False
    src_dir = os.path.abspath(DGVOODOO_BUNDLED_DIR)
    if not os.path.isdir(src_dir):
        return False

    for src_name, _ in DGVOODOO_FILES:
        if not os.path.isfile(os.path.join(src_dir, src_name)):
            return False

    dst_glide2x = os.path.join(game_dir, 'glide2x.dll')
    if is_dgvoodoo_glide(dst_glide2x):
        for src_name, dst_name in DGVOODOO_FILES:
            dst = os.path.join(game_dir, dst_name)
            if not os.path.isfile(dst):
                try:
                    shutil.copy2(os.path.join(src_dir, src_name), dst)
                except Exception:
                    pass
        return True

    for glide_name in ('glide.dll', 'glide2x.dll', 'glide3x.dll'):
        existing = os.path.join(game_dir, glide_name)
        if os.path.isfile(existing):
            backup = existing + '.bak_nglide'
            if not os.path.isfile(backup):
                try:
                    shutil.copy2(existing, backup)
                except Exception:
                    pass

    try:
        for src_name, dst_name in DGVOODOO_FILES:
            shutil.copy2(os.path.join(src_dir, src_name),
                         os.path.join(game_dir, dst_name))
        return True
    except Exception:
        return False
