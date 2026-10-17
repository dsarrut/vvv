#!/usr/bin/env python3
"""
Compare two saved vvv benchmark results of THIS machine (no benchmark is run).

    python tests/bench_compare.py                    # previous vs latest core result
    python tests/bench_compare.py 9f08fb5            # latest run of a commit vs latest
    python tests/bench_compare.py 9f08fb5 c992214    # two commits
    python tests/bench_compare.py a.json b.json      # two files
    python tests/bench_compare.py --bench startup    # startup results instead of core
    python tests/bench_compare.py --list             # list this machine's results

OLD/NEW are a commit prefix (its latest run) or a json path. Exit code 1 if
NEW has regressions (median above OLD's p90 and > 10 % and > 2 ms slower),
so it can be scripted.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench_common as bc  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Compare two saved vvv benchmark results.")
    p.add_argument("old", nargs="?", help="commit prefix or json (default: previous result)")
    p.add_argument("new", nargs="?", help="commit prefix or json (default: latest result)")
    p.add_argument("--bench", default="core", help="core (default) or startup")
    p.add_argument("--host", help="machine name (default: this machine)")
    p.add_argument("--list", action="store_true", help="list available results")
    args = p.parse_args()

    files = bc.list_reports(args.bench, args.host)
    if args.list or len(files) < 1:
        print(f"{len(files)} '{args.bench}' result(s) for {args.host or bc.machine_name()}:")
        for f in files:
            print("  " + os.path.relpath(f, bc.REPO))
        return 0

    new = bc.resolve_ref(args.new, args.bench, args.host) if args.new else files[-1]
    old = (bc.resolve_ref(args.old, args.bench, args.host) if args.old
           else bc.resolve_ref(None, args.bench, args.host, before=new))
    for name, ref, path in [("old", args.old, old), ("new", args.new, new)]:
        if path is None:
            print(f"no {name} result found{f' for {ref!r}' if ref else ''} (try --list)")
            return 2
    print(f"  old: {os.path.relpath(old, bc.REPO)}\n  new: {os.path.relpath(new, bc.REPO)}")
    n_reg = bc.compare(bc.load_report(old), bc.load_report(new))
    return 1 if n_reg else 0


if __name__ == "__main__":
    sys.exit(main())
