#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: python src/03_run_plot_module.py <RunID>")
        print("Example: python src/03_run_plot_module.py Run0009_2025-06-06_Test")
        sys.exit(1)

    run_id = sys.argv[1]
    cfg = Path("config") / f"{run_id}.yml"
    if not cfg.is_file():
        print(f"❌ Config file not found: {cfg}")
        sys.exit(1)

    # the two R scripts we just refactored
    r_scripts = [
        Path("src/R/03.04_P1_ptmiptm_combi.R"),
        Path("src/R/03.05_P2_ptmtoiptm.R"),
        Path("src/R/03.06_P3_heatmap.R"),
    ]

    # sanity-check they exist
    for r in r_scripts:
        if not r.is_file():
            print(f"❌ R script not found: {r}")
            sys.exit(1)

    # run them in sequence
    for r in r_scripts:
        cmd = ["Rscript", str(r), str(cfg)]
        print(f"🔧 Running: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ {r.name} failed (exit code {e.returncode})")
            sys.exit(e.returncode)

    print("✅ All plotting modules completed successfully.")

if __name__ == "__main__":
    main()
