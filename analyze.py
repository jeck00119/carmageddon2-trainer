#!/usr/bin/env python3
"""
Offline analysis helper for CARMA2_HW.EXE.

Reads the local binary copy at carma2_tools/carma2hw.bin and provides three
subcommands for static exploration:

  disasm  <VA> [LEN]     disassemble LEN bytes (hex) starting at VA
  callers <VA>           find every `call VA` instruction in .text
  xrefs   <VA>           find every 32-bit absolute reference to VA

All VAs are decimal or hex (0xNNNN). LEN defaults to 0x100.

Examples:
  py -3 analyze.py disasm 0x46a934 0x80
  py -3 analyze.py callers 0x46c970
  py -3 analyze.py xrefs 0x5bf280
"""
import struct
import sys
import os

from capstone import Cs, CS_ARCH_X86, CS_MODE_32

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carma2hw.bin')


def parse_int(s):
    return int(s, 0)


class Binary:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = f.read()
        e_lfanew = struct.unpack_from('<I', self.data, 0x3c)[0]
        opt = e_lfanew + 4 + 20
        self.image_base = struct.unpack_from('<I', self.data, opt + 28)[0]
        num_sections = struct.unpack_from('<H', self.data, e_lfanew + 4 + 2)[0]
        size_optional = struct.unpack_from('<H', self.data, e_lfanew + 4 + 16)[0]
        sections_off = e_lfanew + 4 + 20 + size_optional
        self.sections = []
        for i in range(num_sections):
            so = sections_off + i * 40
            name = self.data[so:so+8].rstrip(b'\x00').decode('ascii', errors='replace')
            vsize = struct.unpack_from('<I', self.data, so + 8)[0]
            va = struct.unpack_from('<I', self.data, so + 12)[0]
            raw_size = struct.unpack_from('<I', self.data, so + 16)[0]
            raw_off = struct.unpack_from('<I', self.data, so + 20)[0]
            self.sections.append({
                'name': name, 'va': va, 'vsize': vsize,
                'raw_off': raw_off, 'raw_size': raw_size,
            })
        # Fast access to .text (first code section)
        self.text = next(s for s in self.sections if s['name'] == '.text')

    def va_to_off(self, va):
        rva = va - self.image_base
        for s in self.sections:
            if s['va'] <= rva < s['va'] + s['vsize']:
                return s['raw_off'] + (rva - s['va'])
        return None

    def off_to_va(self, off):
        for s in self.sections:
            if s['raw_off'] <= off < s['raw_off'] + s['raw_size']:
                return self.image_base + s['va'] + (off - s['raw_off'])
        return None

    def in_text(self, off):
        t = self.text
        return t['raw_off'] <= off < t['raw_off'] + t['raw_size']


def cmd_disasm(bin_, argv):
    if not argv:
        print('usage: analyze.py disasm <VA> [LEN]')
        return 1
    start = parse_int(argv[0])
    length = parse_int(argv[1]) if len(argv) > 1 else 0x100
    off = bin_.va_to_off(start)
    if off is None:
        print(f'VA 0x{start:08x} not in any section')
        return 1
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    chunk = bin_.data[off:off + length]
    for insn in cs.disasm(chunk, start):
        mark = ''
        if insn.mnemonic == 'call':
            mark = '  <-- CALL'
        elif insn.mnemonic.startswith('ret'):
            mark = '  <-- RET'
        print(f'  0x{insn.address:08x}  {insn.mnemonic:<7} {insn.op_str}{mark}')
    return 0


def cmd_callers(bin_, argv):
    if not argv:
        print('usage: analyze.py callers <VA>')
        return 1
    target = parse_int(argv[0])
    t = bin_.text
    hits = []
    for off in range(t['raw_off'], t['raw_off'] + t['raw_size'] - 5):
        if bin_.data[off] == 0xe8:  # call rel32
            disp = struct.unpack_from('<i', bin_.data, off + 1)[0]
            call_va = bin_.off_to_va(off)
            if call_va is None:
                continue
            dest = (call_va + 5 + disp) & 0xffffffff
            if dest == target:
                hits.append(call_va)
    print(f'{len(hits)} caller(s) of 0x{target:08x}:')
    for va in hits:
        print(f'  0x{va:08x}')
    return 0


def cmd_xrefs(bin_, argv):
    if not argv:
        print('usage: analyze.py xrefs <VA>')
        return 1
    target = parse_int(argv[0])
    needle = struct.pack('<I', target)
    hits_text = []
    hits_data = []
    off = 0
    while True:
        idx = bin_.data.find(needle, off)
        if idx < 0:
            break
        off = idx + 1
        ref_va = bin_.off_to_va(idx)
        if ref_va is None:
            continue
        if bin_.in_text(idx):
            hits_text.append((idx, ref_va))
        else:
            hits_data.append((idx, ref_va))
    print(f'{len(hits_text)} reference(s) in .text:')
    for file_off, va in hits_text[:50]:
        # Identify likely instruction type by looking at the preceding byte
        prev = bin_.data[file_off - 2:file_off]
        kind = ''
        if prev == b'\xc7\x05':
            kind = 'mov [mem32], imm32 (preceding bytes)'
        elif bin_.data[file_off - 1:file_off] == b'\xa1':
            kind = 'mov eax, [mem32]'
        elif bin_.data[file_off - 1:file_off] == b'\xa3':
            kind = 'mov [mem32], eax'
        elif prev in (b'\x8b\x0d', b'\x8b\x1d', b'\x8b\x15', b'\x8b\x35', b'\x8b\x3d'):
            kind = 'mov reg, [mem32]'
        elif prev in (b'\x89\x0d', b'\x89\x1d', b'\x89\x15', b'\x89\x35', b'\x89\x3d'):
            kind = 'mov [mem32], reg'
        print(f'  0x{va:08x}  {kind}')
    if len(hits_text) > 50:
        print(f'  ... {len(hits_text) - 50} more not shown')
    print(f'\n{len(hits_data)} reference(s) in .rdata/.data:')
    for file_off, va in hits_data[:20]:
        print(f'  0x{va:08x}')
    if len(hits_data) > 20:
        print(f'  ... {len(hits_data) - 20} more not shown')
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    bin_ = Binary(BIN)
    cmd = sys.argv[1].lower()
    rest = sys.argv[2:]
    if cmd == 'disasm':
        return cmd_disasm(bin_, rest)
    if cmd == 'callers':
        return cmd_callers(bin_, rest)
    if cmd == 'xrefs':
        return cmd_xrefs(bin_, rest)
    print(f'unknown command: {cmd}')
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main())
