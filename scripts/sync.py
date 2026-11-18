#!/usr/bin/env python3
"""Copy OCI images from a text manifest into Aliyun ACR using skopeo."""

import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9._:/@+\-]+$")
TARGET_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
REGISTRY_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.:-]*$")
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing GitHub Actions secret: {name}")
    return value


def login(registry, username, password):
    print(f"Authenticating to {registry} ...", flush=True)
    subprocess.run(
        ["skopeo", "login", "--username", username, "--password-stdin", registry],
        input=password + "\n",
        text=True,
        check=True,
    )


def parse_manifest():
    source_input = os.getenv("SOURCE_IMAGE", "").strip()
    target_input = os.getenv("TARGET_IMAGE", "").strip()
    if bool(source_input) != bool(target_input):
        raise ValueError("Manual dispatch must specify BOTH source_image and target_image, or neither")
    if source_input:
        return [(source_input, target_input)]

    entries = []
    for line_no, raw in enumerate(Path("images.txt").read_text(encoding="utf-8").splitlines(), 1):
        content = raw.split("#", 1)[0].strip()
        if not content:
            continue
        fields = content.split()
        if len(fields) != 2:
            raise ValueError(f"images.txt:{line_no}: expected 'SOURCE TARGET:TAG'")
        entries.append(tuple(fields))
    if not entries:
        raise ValueError("No images to mirror; add entries to images.txt")
    return entries


def validate(source, target):
    if not SOURCE_PATTERN.fullmatch(source) or "://" in source or source.startswith("-"):
        raise ValueError(f"Invalid source image: {source!r}")
    if not TARGET_PATTERN.fullmatch(target):
        raise ValueError(f"Invalid target (must be repository:tag, no namespace): {target!r}")


def main():
    registry = required("ALIYUN_REGISTRY").removeprefix("https://").removeprefix("http://").rstrip("/")
    namespace = required("ALIYUN_NAME_SPACE")
    username = required("ALIYUN_REGISTRY_USER")
    password = required("ALIYUN_REGISTRY_PASSWORD")
    if not REGISTRY_PATTERN.fullmatch(registry) or not NAMESPACE_PATTERN.fullmatch(namespace):
        raise ValueError("Invalid registry hostname or namespace")

    entries = parse_manifest()
    for source, target in entries:
        validate(source, target)

    # Github's mask is defense-in-depth; password is never passed as a command-line arg.
    login(registry, username, password)
    hub_user = os.getenv("DOCKERHUB_USER", "").strip()
    hub_token = os.getenv("DOCKERHUB_TOKEN", "").strip()
    if bool(hub_user) != bool(hub_token):
        raise ValueError("Set both DOCKERHUB_USER and DOCKERHUB_TOKEN, or neither")
    if hub_user:
        login("docker.io", hub_user, hub_token)

    failed = []
    results = []
    for index, (source, target) in enumerate(entries, 1):
        destination = f"{registry}/{namespace}/{target}"
        print(f"[{index}/{len(entries)}] {source} -> {destination}", flush=True)
        command = ["skopeo", "copy", "--all", "--retry-times", "3", f"docker://{source}", f"docker://{destination}"]
        try:
            subprocess.run(command, check=True)
            results.append(("PASS", source, destination))
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: mirror failed with exit status {exc.returncode}", file=sys.stderr)
            results.append(("FAIL", source, destination))
            failed.append(source)

    print("\n=== Mirror results ===")
    for status, src, dst in results:
        print(f"{status}  {src} -> {dst}")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("## Container image mirror results\n\n| Status | Source | ACR destination |\n|---|---|---|\n")
            for status, src, dst in results:
                file.write(f"| {status} | `{src}` | `{dst}` |\n")
    if failed:
        print(f"{len(failed)} of {len(entries)} images failed", file=sys.stderr)
        return 1
    print(f"Successfully mirrored {len(entries)} image(s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
