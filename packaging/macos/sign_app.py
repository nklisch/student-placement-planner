#!/usr/bin/env python3
"""Sign nested Mach-O files inside-out, then sign the application bundle."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("identity", help="Developer ID identity, or - for ad-hoc signing")
    args = parser.parse_args()

    options = [] if args.identity == "-" else ["--options", "runtime", "--timestamp"]
    files = sorted(
        (path for path in args.app.rglob("*") if path.is_file()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in files:
        kind = subprocess.check_output(["file", "-b", str(path)], text=True)
        if "Mach-O" not in kind:
            continue
        subprocess.run(
            ["codesign", "--force", *options, "--sign", args.identity, str(path)],
            check=True,
        )
    frameworks = sorted(
        (path for path in args.app.rglob("*.framework") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for framework in frameworks:
        subprocess.run(
            [
                "codesign",
                "--force",
                *options,
                "--sign",
                args.identity,
                str(framework),
            ],
            check=True,
        )
    subprocess.run(
        ["codesign", "--force", *options, "--sign", args.identity, str(args.app)],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
