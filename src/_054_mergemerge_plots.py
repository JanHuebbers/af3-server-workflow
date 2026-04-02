#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_054_mergemerge_plots.py
Run one or more R plotting scripts using a YAML *mergemerge* config.

Usage
-----
# by config path
python src/_054_mergemerge_plots.py config/MergemergeAtMLOvsAtEXO70.yml

# by config name (auto-resolves config/<NAME>.yml)
python src/_054_mergemerge_plots.py MergemergeAtMLOvsAtEXO70

# add extra R scripts (can repeat --script)
python src/_054_mergemerge_plots.py MergemergeAtMLOvsAtEXO70 --script src/R/04.99_other.R

Notes
-----
- The mergemerge output folder is: ./Mergemerge/<merge_name>/
- Default R script run is: src/R/04.02_P7_heat.R
- The YAML path is passed as arg1 to each R script: Rscript <script> <config.yml>
- Env vars provided to R scripts:
    MERGEMERGE_CFG = path to yaml
    MERGEMERGE_DIR = path to ./Mergemerge/<merge_name>
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
import subprocess

try:
    import yaml  # PyYAML
except Exception:
    print("Missing dependency 'PyYAML'. Install with: pip install pyyaml")
    sys.exit(2)

DEFAULT_SCRIPTS = [
    Path("src/R/05.02_P7_heat.R"),
]

def resolve_config(arg: str) -> Path:
    """'NAME' -> config/NAME.yml, or use direct .yml/.yaml path."""
    p = Path(arg)
    if p.suffix.lower() in {".yml", ".yaml"}:
        cfg = p
    else:
        cfg = Path("config") / f"{arg}.yml"
    if not cfg.is_file():
        print(f"❌ Config file not found: {cfg}")
        sys.exit(1)
    return cfg.resolve()

def load_merge_name(cfg_path: Path) -> str:
    with cfg_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    mname = (data.get("merge_name") or "").strip()
    if not mname:
        print("❌ Config is missing a non-empty 'merge_name' key.")
        sys.exit(1)
    return mname

def check_rscript() -> str:
    exe = shutil.which("Rscript")
    if not exe:
        print("❌ 'Rscript' not found on PATH. Please install R and ensure Rscript is available.")
        sys.exit(2)
    return exe

def main():
    ap = argparse.ArgumentParser(description="Run R plotting modules using a YAML mergemerge config.")
    ap.add_argument("config", help="Config name (uses config/<name>.yml) or a path to a YAML file.")
    ap.add_argument("--script", action="append", default=[],
                    help="Additional R scripts to run (can be used multiple times).")
    ap.add_argument("--continue-on-error", action="store_true",
                    help="If set, continue running remaining scripts even if one fails.")
    ap.add_argument("--fail-fast", action="store_true",
                    help="If set, stop immediately when a script fails (default behavior).")
    args = ap.parse_args()

    # Resolve fail policy (default: fail-fast)
    continue_on_error = bool(args.continue_on_error) and not bool(args.fail_fast)

    cfg_path = resolve_config(args.config)
    merge_name = load_merge_name(cfg_path)

    mergemerge_dir = (Path(".") / "Mergemerge" / merge_name).resolve()
    mergemerge_dir.mkdir(parents=True, exist_ok=True)

    # Build script list
    scripts = [*DEFAULT_SCRIPTS, *[Path(s) for s in args.script]]
    if not scripts:
        print("❌ No R scripts specified.")
        sys.exit(1)

    # Sanity-check scripts exist
    for r in scripts:
        if not r.is_file():
            print(f"❌ R script not found: {r}")
            sys.exit(1)

    rscript = check_rscript()

    # Env hints for R
    env = os.environ.copy()
    env["MERGEMERGE_CFG"] = str(cfg_path)
    env["MERGEMERGE_DIR"] = str(mergemerge_dir)

    failures = []

    # Run each script, passing the YAML path as arg1
    for r in scripts:
        cmd = [rscript, str(r), str(cfg_path)]
        print(f"🔧 Running: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, env=env)
        except subprocess.CalledProcessError as e:
            msg = f"❌ {r.name} failed (exit code {e.returncode})"
            print(msg)
            failures.append((r, e.returncode))
            if not continue_on_error:
                sys.exit(e.returncode)
        except Exception as e:
            msg = f"❌ {r.name} crashed (exception: {e})"
            print(msg)
            failures.append((r, 999))
            if not continue_on_error:
                sys.exit(999)

    if failures:
        print("⚠️  Some plotting modules failed:")
        for r, code in failures:
            print(f"   - {r.name}: {code}")
        print(f"   MERGEMERGE_DIR: {mergemerge_dir}")
        sys.exit(max(code for _, code in failures))

    print("✅ All plotting modules completed successfully.")
    print(f"   MERGEMERGE_DIR: {mergemerge_dir}")

if __name__ == "__main__":
    main()
