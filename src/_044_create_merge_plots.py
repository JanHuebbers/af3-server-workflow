#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_044_create_merge_plots.py
Run one or more R plotting scripts using a YAML merge config.

Usage
-----
multiProt
python src/_044_create_merge_plots.py config/Merge3AtMpHvMLO.yml
seedSweep
python src/_044_create_merge_plots.py config/Merge1MLOvsH4.yml

python src/_044_create_merge_plots.py config/Merge3AtMpHvMLO.yml
python src/_044_create_merge_plots.py Merge3AtMpHvMLO --script src/R/04.02_P1_ipTM.R --script src/R/04.03_something_else.R
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
import subprocess

try:
    import yaml  # PyYAML
except Exception as e:
    print("Missing dependency 'PyYAML'. Install with: pip install pyyaml")
    sys.exit(2)

DEFAULT_SCRIPTS = [
    Path("src/R/04.02_P4_ipTM.R"),
    Path("src/R/04.03_P5_ptmtoiptm.R"),
    Path("src/R/04.04_P6_heatmap.R"),
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

def check_rscript():
    exe = shutil.which("Rscript")
    if not exe:
        print("❌ 'Rscript' not found on PATH. Please install R and ensure Rscript is available.")
        sys.exit(2)
    return exe

def main():
    ap = argparse.ArgumentParser(description="Run R plotting modules using a YAML merge config.")
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
    merge_dir = (Path(".") / "Merge" / merge_name).resolve()
    merge_dir.mkdir(parents=True, exist_ok=True)

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

    # Env hints for R (optional to use inside your R scripts)
    env = os.environ.copy()
    env["MERGE_CFG"] = str(cfg_path)
    env["MERGE_DIR"] = str(merge_dir)

    failures = []

    # Run each script, passing the YAML path as arg1
    for r in scripts:
        cmd = [rscript, str(r), str(cfg_path)]
        print(f"🔧 Running: {' '.join(cmd)}")
        try:
            # capture_output=False to stream R output live; keeps behavior similar to before
            subprocess.run(cmd, check=True, env=env)
        except subprocess.CalledProcessError as e:
            msg = f"❌ {r.name} failed (exit code {e.returncode})"
            print(msg)
            failures.append((r, e.returncode))
            if not continue_on_error:
                # keep old behavior unless user explicitly asks to continue
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
        print(f"   MERGE_DIR: {merge_dir}")
        # return non-zero so pipelines notice; use max code for convenience
        sys.exit(max(code for _, code in failures))

    print("✅ All plotting modules completed successfully.")
    print(f"   MERGE_DIR: {merge_dir}")

if __name__ == "__main__":
    main()