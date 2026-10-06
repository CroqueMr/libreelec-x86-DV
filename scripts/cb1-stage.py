#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage matched CB1 sources in LibreELEC's native package directories."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


def checked(root, name):
    parts = PurePosixPath(name).parts
    if (not parts or name.startswith("/") or "\\" in name or ":" in name
            or any(part in ("..", ".git") for part in parts)):
        raise ValueError("Unsafe path: " + name)
    path = root / name
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
           for p in (path, *path.parents)):
        raise ValueError("Unsafe path: " + name)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(tree, engine, check=False):
    tree, engine = tree.absolute(), engine.absolute()
    lock = json.loads((tree / "config/cb1-source-lock.json").read_text(encoding="utf-8"))
    commit = lock["engine"]["commit"]
    if commit:
        git = ["git", "-C", str(engine)]
        if subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != commit:
            raise ValueError("Wrong CB1 commit")
        if subprocess.check_output(git + ["status", "--porcelain"]):
            raise ValueError("Dirty pinned CB1 checkout")
    for name, expected in lock.get("integration_files", {}).items():
        if digest(checked(tree, name)) != expected:
            raise ValueError("Integration mismatch: " + name)
    files = []
    for destination, record in lock["staging"].items():
        source, target = checked(engine, record["source"]), checked(tree, destination)
        if digest(source) != record["sha256"]:
            raise ValueError("Source mismatch: " + record["source"])
        if target.exists() and digest(target) != record["sha256"]:
            raise ValueError("Destination differs: " + destination)
        files.append((source, target))
    if not check:
        for source, target in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    print(f"{'Checked' if check else 'Staged'} {len(files)} matched CB1 files.")
    if not commit and lock["engine"].get("source") != "CB1/":
        print("Local source snapshot. Publication requires a committed CB1 revision.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, help="Override the bundled CB1 source directory")
    parser.add_argument("--tree", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        stage(args.tree, args.engine or args.tree / "CB1", args.check)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
