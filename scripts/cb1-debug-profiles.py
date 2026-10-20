#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package already-built Debug pairs; this does not build a standard kernel.

--evidence is JSON: {"build": BUILD, "profiles": {"modified": PAIR,
"standard": PAIR}}. BUILD must be embedded identically in both SYSTEMs at
/usr/share/cb1/driver-profile-build.json, alongside /etc/cb1-debug. It contains
id, linux_version, linux_source_sha256, ordinary_patches_sha256 and userspace
{kodi,cb1,mesa} source identities (SHA256). PAIR contains kernel/system input
paths, independently recorded kernel_sha256/system_sha256, kernel_release and
the actual applied patches map {repo-relative-path:sha256}. Relative input
paths resolve against the evidence file. Source-policy provenance must come
from the build; it cannot be inferred from the resulting kernel binary.

--policy defaults to config/cb1-driver-profiles.json: {schema:1,
linux_source_sha256:HASH, ordinary_patches:{path:HASH}, graphics_patches:{path:HASH}}.
Standard's applied map must exactly match ordinary_patches; modified's map must
exactly match ordinary+graphics. BUILD.ordinary_patches_sha256 is SHA256 of the
ordinary map encoded by json.dumps(sort_keys=True,separators=(',',':')).
BUILD.linux_source_sha256 must match the independently pinned policy.

Checks all non-module file contents, modes, owners and symlink targets for
equality. Checks each uncompressed module's vermagic against kernel_release.
Requires unsquashfs, never extracts whole SYSTEM images. Output is a new flash
payload tree: KERNEL, SYSTEM, cb1/{KERNEL.standard,SYSTEM.standard,driver-profiles.json}.
The image builder must copy that tree to the FAT boot partition. Both complete
SYSTEMs must have been built with their own matching module overlays.
--check DIR revalidates a packaged tree and both embedded identities. Optional
--kernel/--system compare the modified pair with image-builder inputs; --capacity
checks the partition size without resizing it. It never creates a disk image.

Install the complete Debug disk image before using paired TAR updates. An older
normal updater cannot enforce these guards and may copy only the modified pair.
Mixed normal/Debug TAR conversions are refused by the new initramfs. Updates
retain LibreELEC's sequential-write guarantee, not power-loss-safe A/B recovery.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

RUNTIME = Path(__file__).resolve().parents[1] / "projects/Generic/filesystem/usr/bin/cb1-driver-profile"
DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "config/cb1-driver-profiles.json"
COMMON = runpy.run_path(str(RUNTIME))
require = COMMON["require"]
digest = COMMON["digest"]


def cat(system, path):
    return subprocess.run(["unsquashfs", "-cat", "-no-wildcards", str(system), path],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def module_path(path):
    return (path.startswith("usr/lib/kernel-overlays/") and "/lib/modules/" in path or
            path.startswith(("usr/lib/modules/", "lib/modules/")))


def policy_check(build, profiles, policy_path):
    policy = json.loads(policy_path.read_text())
    require(policy["schema"] == 1 and bool(policy["graphics_patches"]), "Missing pinned graphics patch policy")
    ordinary, graphics = policy["ordinary_patches"], policy["graphics_patches"]
    require(not set(ordinary).intersection(graphics), "Ordinary and graphics patch policies overlap")
    for name, value in {**ordinary, **graphics}.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts and
                re.fullmatch("[0-9a-f]{64}", value), "Invalid pinned patch identity")
    require(build["linux_source_sha256"] == policy["linux_source_sha256"], "Linux source disagrees with pinned policy")
    ordinary_hash = hashlib.sha256(json.dumps(ordinary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(build["ordinary_patches_sha256"] == ordinary_hash, "Ordinary patch identity disagrees with pinned policy")
    for name in ("modified", "standard"):
        expected = {**ordinary, **graphics} if name == "modified" else ordinary
        require(profiles[name]["patches"] == expected, "Applied patches disagree with pinned " + name + " policy")


def validate_tree(tree, manifest):
    COMMON["validate_manifest"](manifest)
    for pair in manifest["profiles"].values():
        for kind in ("kernel", "system"):
            item = pair[kind]
            path = tree / item["path"]
            require(path.stat().st_size == item["size"] and digest(path) == item["sha256"], "Packaged payload hash mismatch")
        system = tree / pair["system"]["path"]
        cat(system, "etc/cb1-debug")
        require(json.loads(cat(system, "usr/share/cb1/driver-profile-build.json")) == manifest["build"],
                "Embedded packaged SYSTEM identity differs")


def check(tree, policy, capacity=None, kernel=None, system=None):
    manifest = json.loads((tree / "cb1/driver-profiles.json").read_text())
    policy_check(manifest["build"], manifest["profiles"], policy)
    validate_tree(tree, manifest)
    expected = "".join(digest(tree / name) + "  " + name + "\n" for name in
                       ("KERNEL", "SYSTEM", "cb1/KERNEL.standard", "cb1/SYSTEM.standard", "cb1/driver-profiles.json"))
    require((tree / "cb1/driver-profiles.sha256").read_text() == expected, "Invalid packaged checksum companion")
    if capacity is not None:
        require(capacity >= COMMON["payload_size"](manifest), "Partition too small for paired Debug payloads")
    for kind, path in (("kernel", kernel), ("system", system)):
        if path is not None:
            require(digest(path) == manifest["profiles"]["modified"][kind]["sha256"],
                    "Image builder " + kind + " differs from modified profile")
    print(json.dumps({"build_id": manifest["build"]["id"], "bytes_required": COMMON["payload_size"](manifest)}))


def fingerprints(system, release):
    listing = subprocess.run(["unsquashfs", "-lln", "-UTC", str(system)],
                             capture_output=True, text=True, check=True).stdout
    shared = hashlib.sha256()
    modules = hashlib.sha256()
    files = []
    count = 0
    for line in listing.splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("squashfs-root"):
            continue
        mode, owner, size, _, _, path = parts
        path = path.removeprefix("squashfs-root").lstrip("/")
        is_module = module_path(path)
        target = modules if is_module else shared
        target.update((mode + " " + owner + " " + path + "\0").encode())
        if is_module:
            version = path.split("lib/modules/", 1)[1].split("/", 1)[0]
            require(version == release, "Module directory does not match kernel release: " + path)
        if mode.startswith("-"):
            require(size.isdigit(), "Unsupported squashfs size")
            files.append((path, int(size), is_module))
            target.update((size + "\0").encode())
    require(bool(files), "SYSTEM has no regular files")
    # Bound argv size; stream file bodies in the same sorted listing order.
    for offset in range(0, len(files), 128):
        group = files[offset:offset + 128]
        with subprocess.Popen(["unsquashfs", "-cat", "-no-wildcards", str(system),
                               *(path for path, _, _ in group)], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as process:
            for path, size, is_module in group:
                target = modules if is_module else shared
                remaining = size
                tail = b""
                releases = set()
                is_ko = path.endswith(".ko")
                require(not (is_module and ".ko." in path), "Compressed modules need a verified decompressor: " + path)
                while remaining:
                    data = process.stdout.read(min(1024 * 1024, remaining))
                    require(bool(data), "Short read from SYSTEM: " + path)
                    remaining -= len(data)
                    target.update(data)
                    if is_ko:
                        window = tail + data
                        releases.update(re.findall(rb"\x00vermagic=([^\x00]+)\x00", window))
                        tail = window[-512:]
                if is_ko:
                    require(is_module and bool(releases) and
                            all(value.split(b" ", 1)[0].decode() == release for value in releases),
                            "Module vermagic does not match kernel release: " + path)
                    count += 1
            require(not process.stdout.read(1) and process.wait() == 0, "Cannot stream SYSTEM files")
    require(count > 0, "SYSTEM has no matched kernel modules")
    return shared.hexdigest(), modules.hexdigest()


def package(evidence_path, output, policy_path):
    evidence = json.loads(evidence_path.read_text())
    require(not output.exists(), "Output already exists; refusing to overwrite")
    require(set(evidence["profiles"]) == {"modified", "standard"}, "Both built profiles required")
    build = evidence["build"]
    policy_check(build, evidence["profiles"], policy_path)
    manifest = {"schema": 1, "build": build, "profiles": {}}
    shared_hashes = set()
    inputs = []
    for name in ("modified", "standard"):
        source = evidence["profiles"][name]
        pair = {"kernel_release": source["kernel_release"], "patches": source["patches"]}
        for kind in ("kernel", "system"):
            path = Path(source[kind])
            if not path.is_absolute():
                path = evidence_path.parent / path
            require(digest(path) == source[kind + "_sha256"], "Input hash disagrees with build evidence: " + kind)
            destination = kind.upper() if name == "modified" else "cb1/" + kind.upper() + ".standard"
            pair[kind] = {"path": destination, "size": path.stat().st_size, "sha256": digest(path)}
            inputs.append((path, destination))
            if kind == "system":
                system = path
        cat(system, "etc/cb1-debug")
        require(json.loads(cat(system, "usr/share/cb1/driver-profile-build.json")) == build,
                "Embedded SYSTEM build identity differs")
        shared, modules = fingerprints(system, source["kernel_release"])
        shared_hashes.add(shared)
        pair["modules_sha256"] = modules
        manifest["profiles"][name] = pair
    require(len(shared_hashes) == 1, "SYSTEM userspace differs outside the matched module trees")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".cb1-profiles-", dir=output.parent))
    try:
        for source, destination in inputs:
            target = staging / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(digest(target) == digest(source), "Input changed during packaging")
        (staging / "cb1/driver-profiles.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        validate_tree(staging, manifest)
        names = ("KERNEL", "SYSTEM", "cb1/KERNEL.standard", "cb1/SYSTEM.standard", "cb1/driver-profiles.json")
        (staging / "cb1/driver-profiles.sha256").write_text(
            "".join(digest(staging / name) + "  " + name + "\n" for name in names))
        for name in ("KERNEL", "SYSTEM"):
            with (staging / name).open("rb") as stream:
                md5 = hashlib.file_digest(stream, "md5").hexdigest()
            (staging / (name + ".md5")).write_text(md5 + "  target/" + name + "\n")
        os.replace(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(json.dumps({"output": str(output), "build_id": build["id"],
                      "userspace_files_sha256": shared_hashes.pop(), "bytes_required": COMMON["payload_size"](manifest)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--evidence", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--capacity", type=int)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--system", type=Path)
    args = parser.parse_args()
    try:
        if args.check:
            check(args.check.resolve(), args.policy, args.capacity, args.kernel, args.system)
        else:
            require(args.output is not None, "--output required for packaging")
            package(args.evidence.resolve(), args.output.absolute(), args.policy)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("Driver-profile packaging refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
