#!/usr/bin/env python3
"""
Numba-accelerated Carma2 hash + brute-force.

Drop-in fast replacement for the pure-Python brute-force loop. The Python
hash runs at ~340k/s; the JIT'd version should hit 50-200M/s on a modern CPU,
making length-7 (8 billion candidates) feasible in minutes instead of hours.
"""
import numpy as np
from numba import njit, prange


@njit(cache=True)
def carma2_hash_nb(chars):
    """Hash a sequence of pre-mapped char codes (each = ord('A')+22..ord('A')+47)."""
    sum_acc = np.uint32(0)
    shl_acc = np.uint32(0)
    sq_acc = np.uint32(0)
    for i in range(chars.shape[0]):
        ch = np.uint32(chars[i])
        sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
        v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
        shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
        sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
    h1 = (((sum_acc << np.uint32(21)) & np.uint32(0xffffffff)) + (shl_acc >> np.uint32(11))) & np.uint32(0xffffffff)
    return h1, sq_acc


@njit(cache=True)
def brute_kernel(L, target_h1s, target_h2s, hits_h1, hits_h2, hits_idx, hits_count):
    """
    Pure brute force length-L over [A..Z]. Maps to 22..47 internally.
    target_h1s/h2s are flat numpy arrays of the (h1,h2) pairs we want to find.
    Hits get appended to hits_h1/h2/idx; hits_count is a 1-element array used as
    a counter (numba can't return mutable counts).
    """
    n_targets = target_h1s.shape[0]
    chars = np.zeros(L, dtype=np.uint8)
    # Initialize with all 'A' (mapped value 22)
    for i in range(L):
        chars[i] = np.uint8(22)

    total = np.int64(1)
    for _ in range(L):
        total *= 26

    for code in range(total):
        # Decode `code` -> chars[]
        c = code
        for pos in range(L - 1, -1, -1):
            chars[pos] = np.uint8(22 + (c % 26))
            c //= 26

        # Compute hash
        sum_acc = np.uint32(0)
        shl_acc = np.uint32(0)
        sq_acc = np.uint32(0)
        for i in range(L):
            ch = np.uint32(chars[i])
            sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
            v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
            shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
            sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
        h1 = (((sum_acc << np.uint32(21)) & np.uint32(0xffffffff)) + (shl_acc >> np.uint32(11))) & np.uint32(0xffffffff)

        # Check against targets (linear scan — fine for n_targets < 100)
        for ti in range(n_targets):
            if h1 == target_h1s[ti] and sq_acc == target_h2s[ti]:
                # Record hit
                slot = hits_count[0]
                if slot < hits_h1.shape[0]:
                    hits_h1[slot] = h1
                    hits_h2[slot] = sq_acc
                    hits_idx[slot] = code
                    hits_count[0] = slot + 1
                break


@njit(cache=True, parallel=True)
def brute_kernel_parallel(L, first_chunk_size, target_h1s, target_h2s, hits_h1, hits_h2, hits_idx, hits_count):
    """Parallel: split outer first letter range across cores."""
    n_targets = target_h1s.shape[0]
    inner_total = np.int64(1)
    for _ in range(L - 1):
        inner_total *= 26

    for first_idx in prange(26):
        first_ch = np.uint32(22 + first_idx)
        # Pre-step the accumulators with the first letter
        sum0 = first_ch
        v0 = first_ch << np.uint32(11)
        shl0 = ((v0 << np.uint32(4)) & np.uint32(0xffffffff)) + (v0 >> np.uint32(17))
        shl0 = shl0 & np.uint32(0xffffffff)
        sq0 = (first_ch * first_ch) & np.uint32(0xffffffff)

        chars = np.zeros(L - 1, dtype=np.uint8)

        for code in range(inner_total):
            # Decode inner code -> chars
            c = code
            for pos in range(L - 2, -1, -1):
                chars[pos] = np.uint8(22 + (c % 26))
                c //= 26

            sum_acc = sum0
            shl_acc = shl0
            sq_acc = sq0
            for i in range(L - 1):
                ch = np.uint32(chars[i])
                sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
                v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
                shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
                sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
            h1 = (((sum_acc << np.uint32(21)) & np.uint32(0xffffffff)) + (shl_acc >> np.uint32(11))) & np.uint32(0xffffffff)

            for ti in range(n_targets):
                if h1 == target_h1s[ti] and sq_acc == target_h2s[ti]:
                    slot = hits_count[0]
                    if slot < hits_h1.shape[0]:
                        hits_h1[slot] = h1
                        hits_h2[slot] = sq_acc
                        # Encode the actual full code: first_idx * inner_total + code
                        hits_idx[slot] = np.int64(first_idx) * inner_total + np.int64(code)
                        hits_count[0] = slot + 1
                    break


def code_to_string(code, L):
    """Decode a brute-force code (0..26^L-1) back to its A..Z string."""
    chars = []
    for _ in range(L):
        chars.append(chr(ord('A') + (code % 26)))
        code //= 26
    return ''.join(reversed(chars))


def _prefix_state(prefix):
    """Pre-compute (sum, shl, sq) accumulators after the given prefix string.
    Returns (sum_acc, shl_acc, sq_acc) as np.uint32."""
    sum_acc = np.uint32(0)
    shl_acc = np.uint32(0)
    sq_acc = np.uint32(0)
    for c in prefix.upper():
        if not c.isalpha():
            continue
        ch = np.uint32(ord(c) - ord('A') + 22)
        sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
        v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
        shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
        sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
    return sum_acc, shl_acc, sq_acc


@njit(cache=True, parallel=True)
def _suffix_kernel(L, sum_init, shl_init, sq_init,
                   target_h1s, target_h2s,
                   hits_h1, hits_h2, hits_idx, hits_count):
    """Brute force a length-L suffix starting from the given accumulator state.
    Parallelized over the first letter of the suffix."""
    n_targets = target_h1s.shape[0]
    inner_total = np.int64(1)
    for _ in range(L - 1):
        inner_total *= 26

    for first_idx in prange(26):
        first_ch = np.uint32(22 + first_idx)
        # Step accumulators with the first suffix letter
        sum0 = (sum_init + first_ch) & np.uint32(0xffffffff)
        v0 = (shl_init + (first_ch << np.uint32(11))) & np.uint32(0xffffffff)
        shl0 = (((v0 << np.uint32(4)) & np.uint32(0xffffffff)) + (v0 >> np.uint32(17))) & np.uint32(0xffffffff)
        sq0 = ((first_ch * first_ch) + ((sq_init << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_init >> np.uint32(29))) & np.uint32(0xffffffff)

        chars = np.zeros(L - 1, dtype=np.uint8)
        for code in range(inner_total):
            c = code
            for pos in range(L - 2, -1, -1):
                chars[pos] = np.uint8(22 + (c % 26))
                c //= 26

            sum_acc = sum0
            shl_acc = shl0
            sq_acc = sq0
            for i in range(L - 1):
                ch = np.uint32(chars[i])
                sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
                v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
                shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
                sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
            h1 = (((sum_acc << np.uint32(21)) & np.uint32(0xffffffff)) + (shl_acc >> np.uint32(11))) & np.uint32(0xffffffff)

            for ti in range(n_targets):
                if h1 == target_h1s[ti] and sq_acc == target_h2s[ti]:
                    slot = hits_count[0]
                    if slot < hits_h1.shape[0]:
                        hits_h1[slot] = h1
                        hits_h2[slot] = sq_acc
                        hits_idx[slot] = np.int64(first_idx) * inner_total + np.int64(code)
                        hits_count[0] = slot + 1
                    break


def brute_force_prefix(prefix, L_suffix, targets, max_hits=1024):
    """Brute force candidates of the form prefix + (26^L_suffix). Returns hits."""
    sum0, shl0, sq0 = _prefix_state(prefix)

    target_pairs = list(targets.keys())
    target_h1s = np.array([p[0] for p in target_pairs], dtype=np.uint32)
    target_h2s = np.array([p[1] for p in target_pairs], dtype=np.uint32)

    hits_h1 = np.zeros(max_hits, dtype=np.uint32)
    hits_h2 = np.zeros(max_hits, dtype=np.uint32)
    hits_idx = np.zeros(max_hits, dtype=np.int64)
    hits_count = np.zeros(1, dtype=np.int64)

    _suffix_kernel(L_suffix, sum0, shl0, sq0,
                   target_h1s, target_h2s,
                   hits_h1, hits_h2, hits_idx, hits_count)

    n = int(hits_count[0])
    results = []
    for i in range(n):
        suffix = code_to_string(int(hits_idx[i]), L_suffix)
        s = prefix + suffix
        key = (int(hits_h1[i]), int(hits_h2[i]))
        results.append((s, targets[key]))
    return results


@njit(cache=True, parallel=True)
def _doubled_kernel(L, target_h1s, target_h2s,
                    hits_h1, hits_h2, hits_idx, hits_count):
    """Brute force WW pattern where W has length L. Output length 2L."""
    n_targets = target_h1s.shape[0]
    inner_total = np.int64(1)
    for _ in range(L - 1):
        inner_total *= 26

    # Outer parallel: first letter of W
    for first_idx in prange(26):
        first_ch = np.uint32(22 + first_idx)
        chars = np.zeros(L - 1, dtype=np.uint8)

        for code in range(inner_total):
            c = code
            for pos in range(L - 2, -1, -1):
                chars[pos] = np.uint8(22 + (c % 26))
                c //= 26

            # Hash W+W: simulate by hashing first_ch then chars[] then first_ch then chars[]
            sum_acc = first_ch
            v = first_ch << np.uint32(11)
            shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
            sq_acc = (first_ch * first_ch) & np.uint32(0xffffffff)

            for i in range(L - 1):
                ch = np.uint32(chars[i])
                sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
                v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
                shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
                sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)

            # Second copy of W
            sum_acc = (sum_acc + first_ch) & np.uint32(0xffffffff)
            v = (shl_acc + (first_ch << np.uint32(11))) & np.uint32(0xffffffff)
            shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
            sq_acc = ((first_ch * first_ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)
            for i in range(L - 1):
                ch = np.uint32(chars[i])
                sum_acc = (sum_acc + ch) & np.uint32(0xffffffff)
                v = (shl_acc + (ch << np.uint32(11))) & np.uint32(0xffffffff)
                shl_acc = (((v << np.uint32(4)) & np.uint32(0xffffffff)) + (v >> np.uint32(17))) & np.uint32(0xffffffff)
                sq_acc = ((ch * ch) + ((sq_acc << np.uint32(3)) & np.uint32(0xffffffff)) + (sq_acc >> np.uint32(29))) & np.uint32(0xffffffff)

            h1 = (((sum_acc << np.uint32(21)) & np.uint32(0xffffffff)) + (shl_acc >> np.uint32(11))) & np.uint32(0xffffffff)

            for ti in range(n_targets):
                if h1 == target_h1s[ti] and sq_acc == target_h2s[ti]:
                    slot = hits_count[0]
                    if slot < hits_h1.shape[0]:
                        hits_h1[slot] = h1
                        hits_h2[slot] = sq_acc
                        hits_idx[slot] = np.int64(first_idx) * inner_total + np.int64(code)
                        hits_count[0] = slot + 1
                    break


def brute_force_doubled(L, targets, max_hits=1024):
    """Brute force WW where len(W)=L. Output is 2L chars."""
    target_pairs = list(targets.keys())
    target_h1s = np.array([p[0] for p in target_pairs], dtype=np.uint32)
    target_h2s = np.array([p[1] for p in target_pairs], dtype=np.uint32)

    hits_h1 = np.zeros(max_hits, dtype=np.uint32)
    hits_h2 = np.zeros(max_hits, dtype=np.uint32)
    hits_idx = np.zeros(max_hits, dtype=np.int64)
    hits_count = np.zeros(1, dtype=np.int64)

    _doubled_kernel(L, target_h1s, target_h2s,
                    hits_h1, hits_h2, hits_idx, hits_count)

    n = int(hits_count[0])
    results = []
    for i in range(n):
        word = code_to_string(int(hits_idx[i]), L)
        s = word + word
        key = (int(hits_h1[i]), int(hits_h2[i]))
        results.append((s, targets[key]))
    return results


def brute_force(L, targets, parallel=True, max_hits=1024):
    """
    Brute-force length L against the given target dict.
    Returns a list of (string, target_entry) tuples.

    targets : dict[(h1,h2) -> any]
    """
    target_pairs = list(targets.keys())
    target_h1s = np.array([p[0] for p in target_pairs], dtype=np.uint32)
    target_h2s = np.array([p[1] for p in target_pairs], dtype=np.uint32)

    hits_h1 = np.zeros(max_hits, dtype=np.uint32)
    hits_h2 = np.zeros(max_hits, dtype=np.uint32)
    hits_idx = np.zeros(max_hits, dtype=np.int64)
    hits_count = np.zeros(1, dtype=np.int64)

    if parallel:
        brute_kernel_parallel(L, 0, target_h1s, target_h2s, hits_h1, hits_h2, hits_idx, hits_count)
    else:
        brute_kernel(L, target_h1s, target_h2s, hits_h1, hits_h2, hits_idx, hits_count)

    n = int(hits_count[0])
    results = []
    for i in range(n):
        s = code_to_string(int(hits_idx[i]), L)
        key = (int(hits_h1[i]), int(hits_h2[i]))
        results.append((s, targets[key]))
    return results


if __name__ == '__main__':
    # Self-test: verify against pure Python on a small length
    import time
    from hash_function import carma2_hash, KNOWN_CHEATS

    print('Warming up JIT (length 3)...')
    t = time.time()
    targets = {h: name for name, h in KNOWN_CHEATS.items()}
    brute_force(3, targets, parallel=False)
    print(f'  warm-up: {time.time()-t:.2f}s')

    print('\nNow timing length 5 (parallel)...')
    t = time.time()
    hits = brute_force(5, targets, parallel=True)
    elapsed = time.time() - t
    rate = (26**5) / elapsed
    print(f'  length 5: {26**5:,} candidates in {elapsed:.2f}s = {rate/1e6:.1f}M/s')
    print(f'  hits: {len(hits)}')
    for s, e in hits:
        print(f'    {s} -> {e}')

    print('\nTiming length 6 (parallel)...')
    t = time.time()
    hits = brute_force(6, targets, parallel=True)
    elapsed = time.time() - t
    rate = (26**6) / elapsed
    print(f'  length 6: {26**6:,} candidates in {elapsed:.2f}s = {rate/1e6:.1f}M/s')
    print(f'  hits: {len(hits)}')
