#!/usr/bin/env python3
# Copyright (c) 2025 The Dogecoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Reorder the testScripts list in rpc-tests.py by measured duration.

rpc-tests.py runs tests in list order across parallel workers, so starting the
longest tests first minimizes total wall time. After adding or changing tests,
run the suite, save the results table it prints, then:

    qa/pull-tester/rpc-tests.py | tee /tmp/rpc-times.txt
    qa/pull-tester/order-tests.py /tmp/rpc-times.txt

Reads the table from FILE (or stdin if omitted) and rewrites testScripts in
place. Sorting is stable, so ties keep their current relative order. Tests
with no timing (new tests) are placed first and reported, so that they are
assumed long until measured. Commented-out (disabled) tests are kept at the
end of the list. Use --check to exit non-zero if the file is not in order
instead of rewriting it.
"""
import argparse
import os
import re
import sys

RPC_TESTS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'rpc-tests.py')

ANSI = re.compile(r'\x1b\[[0-9;]*m')
TIMING = re.compile(r'^(?P<name>\S.*?)\s*\|\s*(?:True|False)\s*\|\s*(?P<secs>\d+) s(?:\s*\|\s*(?P<cpu>[\d.]+) s cpu)?\s*$')
ENTRY = re.compile(r"^\s*'(?P<name>[^']+)',\s*$")
DISABLED = re.compile(r"^\s*#\s*'(?P<name>[^']+)',\s*$")
# Comments this tool generates (or that went stale when order stopped being
# hand-maintained); they are dropped and regenerated.
GENERATED = re.compile(r'^\s*#\s*(Ordered by|Disabled tests:|vv Tests)')


def parse_timings(text):
    timings = {}
    for line in text.splitlines():
        m = TIMING.match(ANSI.sub('', line))
        if m and m.group('name') != 'ALL':
            timings[m.group('name')] = int(m.group('secs'))
    return timings


def find_block(source):
    start = source.index('testScripts = [\n')
    end = source.index('\n]\n', start) + 1
    return start + len('testScripts = [\n'), end


def parse_block(block):
    """Return (entries, disabled); entries is a list of (comments, name)."""
    entries, disabled, pending = [], [], []
    for line in block.splitlines():
        if ENTRY.match(line):
            entries.append((pending, ENTRY.match(line).group('name')))
            pending = []
        elif DISABLED.match(line):
            disabled.append(line)
        elif GENERATED.match(line) or not line.strip():
            continue
        elif line.lstrip().startswith('#'):
            pending.append(line)
        else:
            raise ValueError('unrecognized line in testScripts: %r' % line)
    return entries, disabled, pending


def render(entries, disabled, trailing):
    out = ['    # Ordered by measured duration, longest first, to favor running tests in parallel']
    for comments, name in entries:
        out.extend(comments)
        out.append("    '%s'," % name)
    out.extend(trailing)
    if disabled:
        out.append('    # Disabled tests:')
        out.extend('    ' + line.strip() for line in disabled)
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('timings', nargs='?', help='file containing rpc-tests.py results table (default: stdin)')
    parser.add_argument('--rpc-tests', default=RPC_TESTS, help='rpc-tests.py to rewrite')
    parser.add_argument('--check', action='store_true', help='report whether the list is ordered; do not rewrite')
    args = parser.parse_args()

    text = open(args.timings).read() if args.timings else sys.stdin.read()
    timings = parse_timings(text)
    if not timings:
        sys.exit('error: no timing rows found (expected "name | True | N s")')

    source = open(args.rpc_tests).read()
    start, end = find_block(source)
    entries, disabled, trailing = parse_block(source[start:end])

    names = [name for _, name in entries]
    unknown = [n for n in names if n not in timings]
    # Unmeasured tests sort first; sorted() is stable so ties keep their order.
    ordered = sorted(entries, key=lambda e: -timings.get(e[1], float('inf')))

    if unknown:
        print('warning: no timing for %d test(s), placing them first: %s' % (len(unknown), ', '.join(unknown)), file=sys.stderr)
    stale = sorted(set(timings) - set(names))
    if stale:
        print('note: timings for tests not in testScripts ignored: %s' % ', '.join(stale), file=sys.stderr)

    if [n for _, n in ordered] == names:
        print('testScripts is already in order')
        return
    if args.check:
        print('testScripts is out of order; run without --check to fix', file=sys.stderr)
        sys.exit(1)

    new_source = source[:start] + render(ordered, disabled, trailing) + source[end:]
    with open(args.rpc_tests, 'w') as f:
        f.write(new_source)
    print('reordered %d tests in %s' % (len(ordered), args.rpc_tests))


if __name__ == '__main__':
    main()
