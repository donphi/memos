#!/usr/bin/env python3
"""
Reads config/versions.yaml and generates requirements.txt.
Run this after editing python_packages in versions.yaml.

Usage:
    python scripts/generate_requirements.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from pathlib import Path

VERSIONS_FILE = Path(__file__).resolve().parent.parent / "config" / "versions.yaml"
REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"


def main():
    if not VERSIONS_FILE.exists():
        print(f"Error: {VERSIONS_FILE} not found")
        sys.exit(1)

    with open(VERSIONS_FILE) as f:
        versions = yaml.safe_load(f)

    packages = versions.get("python_packages", {})
    if not packages:
        print("Error: no python_packages found in versions.yaml")
        sys.exit(1)

    lines = [
        "# Auto-generated from config/versions.yaml",
        "# Do not edit manually — run: python scripts/generate_requirements.py",
        "",
    ]
    for pkg, ver in packages.items():
        lines.append(f"{pkg}=={ver}")

    REQUIREMENTS_FILE.write_text("\n".join(lines) + "\n")
    print(f"Generated {REQUIREMENTS_FILE} with {len(packages)} packages")


if __name__ == "__main__":
    main()
