#!/usr/bin/env python3
"""Fetch a URL bypassing basic bot detection, print readable text.

Usage:  py -3 webfetch.py <url> [search_term]

Sends a real browser User-Agent + Accept headers so sites like cwaboard,
fandom, etc. don't return 403/503. Strips HTML/scripts/styles and prints
the readable text. If search_term is given, prints a window around the
first match.
"""
import re
import ssl
import sys
import urllib.request

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',  # no gzip so we get plain HTML
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT')
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        raw = resp.read()
    # Try UTF-8 first, fallback to latin-1
    for enc in ('utf-8', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def strip_html(html: str) -> str:
    text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|div|tr|h[1-6]|li)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    # HTML entities
    entities = {'&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
                '&quot;': '"', '&#39;': "'", '&#91;': '[', '&#93;': ']',
                '&mdash;': '—', '&ndash;': '–', '&rsquo;': '\u2019',
                '&lsquo;': '\u2018', '&hellip;': '...'}
    for k, v in entities.items():
        text = text.replace(k, v)
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    lines = [ln.strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    search = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        html = fetch(url)
    except Exception as e:
        print(f'fetch failed: {e}', file=sys.stderr)
        sys.exit(2)

    text = strip_html(html)

    if search:
        # Case-insensitive find all occurrences, print a 2000-char window around first
        m = re.search(re.escape(search), text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 200)
            end = min(len(text), m.start() + 4000)
            print(text[start:end])
        else:
            print(f'"{search}" not found in {len(text)} chars of text')
            print('--- first 2000 chars ---')
            print(text[:2000])
    else:
        print(text)


if __name__ == '__main__':
    main()
