#!/usr/bin/env python3
import os
import sys
import glob
import yaml
import shutil
import pandas as pd
import subprocess

from _011_InputJSONBot import make_json_from_df

# Base directories
BASE_DIR       = os.path.abspath(os.path.join(__file__, "..", ".."))
EXCEL_PATH     = os.path.join(BASE_DIR, "af3_input.xlsx")
CONFIG_DIR     = os.path.join(BASE_DIR, "config")
INPUT_DIR      = os.path.join(BASE_DIR, "input")
AF3_OUTPUT_DIR = os.path.join(BASE_DIR, "AF3_output")

# Paths to helper scripts
RESMAP_BOT = os.path.join(BASE_DIR, "src", "_012_ResidueMapBot.py")
MSA_BOT    = os.path.join(BASE_DIR, "src", "_013_AlignBot.py")

# Optional non-interactive override (set to "1" to force overwrite)
FORCE = os.environ.get("AF3_FORCE", "").strip() == "1"


# ---------------------- helpers: overwrite + I/O ----------------------

def _yesno(prompt: str, default_no: bool = True) -> bool:
    """
    Ask a yes/no question via input(). Returns True for yes.
    Default is 'no' unless user explicitly types y/yes.
    """
    if FORCE:
        return True
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    resp = input(prompt + suffix).strip().lower()
    return resp in ("y", "yes") if default_no else resp not in ("n", "no", "")

def _safe_rmtree(path: str) -> None:
    """Remove a directory tree if it exists."""
    if os.path.isdir(path):
        shutil.rmtree(path)

def _safe_rm(path: str) -> None:
    """Remove a file if it exists."""
    if os.path.isfile(path):
        os.remove(path)

def _dir_has_files(path: str) -> bool:
    """True if dir exists and has any files/subdirs."""
    return os.path.isdir(path) and any(True for _ in os.scandir(path))


# ---------------------- external steps ----------------------

def _run_residue_map_bot(input_json_path: str) -> None:
    """Run _012_ResidueMapBot.py for the given input JSON."""
    if not os.path.isfile(RESMAP_BOT):
        print(f"[warn] ResidueMapBot not found at {RESMAP_BOT}. Skipping residue-map generation.", file=sys.stderr)
        return
    if not os.path.isfile(input_json_path):
        print(f"[warn] Input JSON not found at {input_json_path}. Skipping residue-map generation.", file=sys.stderr)
        return
    cmd = [sys.executable, RESMAP_BOT, input_json_path]
    try:
        print(f"[info] Running residue-map bot: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[warn] ResidueMapBot exited with nonzero status ({e.returncode}). See logs above.", file=sys.stderr)
    except Exception as e:
        print(f"[warn] Could not run ResidueMapBot: {e}", file=sys.stderr)

def _run_msa_bot(cfg_path: str) -> None:
    """Run _013_AlignBot.py on the given YAML."""
    if not os.path.isfile(MSA_BOT):
        print(f"[warn] MSA bot not found at {MSA_BOT}. Skipping MSA generation.", file=sys.stderr)
        return
    if not os.path.isfile(cfg_path):
        print(f"[warn] Config YAML not found at {cfg_path}. Skipping MSA generation.", file=sys.stderr)
        return
    cmd = [sys.executable, MSA_BOT, cfg_path]
    try:
        print(f"[info] Running MSA bot: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[warn] _013_AlignBot exited with nonzero status ({e.returncode}). See logs above.", file=sys.stderr)
    except FileNotFoundError as e:
        print(f"[warn] Could not locate required alignment binary (mafft/clustalo/muscle): {e}", file=sys.stderr)
    except Exception as e:
        print(f"[warn] Could not run _013_AlignBot: {e}", file=sys.stderr)


# ---------------------- main per-config pipeline ----------------------

def process_one_config(cfg_path):
    """
    Order (fixed):
      1) Create/overwrite input JSON
      2) Create/overwrite residue maps
      3) Create/overwrite alignments
    """
    run_name = os.path.splitext(os.path.basename(cfg_path))[0]
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        print(f"[{run_name}] ERROR parsing {cfg_path}: {e}", file=sys.stderr)
        return

    sheet_name  = cfg.get("sheet")
    output_json = cfg.get("output_json", f"{run_name}_input.json")
    ion_default = cfg.get("default_ion", 4)
    model_seeds = cfg.get("modelSeeds", [])
    alignment_tool = (cfg.get("alignment_algo")
                      or cfg.get("alignment", {}).get("tool", "auto"))

    # Verify Excel file
    if not os.path.isfile(EXCEL_PATH):
        print(f"[{run_name}] ERROR: Excel file not found at {EXCEL_PATH}", file=sys.stderr)
        return

    try:
        xls = pd.ExcelFile(EXCEL_PATH, engine="openpyxl")
    except Exception as e:
        print(f"[{run_name}] ERROR loading Excel: {e}", file=sys.stderr)
        return

    if sheet_name not in xls.sheet_names:
        print(f"[{run_name}] WARNING: sheet '{sheet_name}' not found. Skipping.", file=sys.stderr)
        return

    # Read sheet
    df = pd.read_excel(xls, sheet_name=sheet_name, engine="openpyxl")

    # SimID (width 4)
    if "SimID" in df.columns and not df["SimID"].isna().all():
        try:
            sim_int = int(df["SimID"].iloc[0])
            sim_id = f"{sim_int:04d}"
        except Exception:
            sim_id = str(df["SimID"].iloc[0]).zfill(4)
    else:
        sim_id = run_name  # fallback

    # Ensure AF3_output/<SimID>
    sim_output_dir = os.path.join(AF3_OUTPUT_DIR, sim_id)
    os.makedirs(sim_output_dir, exist_ok=True)
    print(f"[{run_name}] Ensured AF3_output/{sim_id}/ exists")

    # Ensure input/
    os.makedirs(INPUT_DIR, exist_ok=True)

    # Paths we might overwrite
    full_output_json = os.path.join(INPUT_DIR, output_json)
    residuemap_dir   = os.path.join(INPUT_DIR, "residue_maps", sim_id)
    alignments_dir   = os.path.join(INPUT_DIR, "alignments",   sim_id)  # tool subdirs live inside here

    # ---------------- 1) JSON ----------------
    if os.path.isfile(full_output_json):
        if _yesno(f"[{run_name}] Input JSON already exists at {full_output_json}. Overwrite?"):
            _safe_rm(full_output_json)
            print(f"[{run_name}] Regenerating input JSON → {full_output_json}")
            make_json_from_df(
                df=df,
                run_name=run_name,
                ion_default=ion_default,
                model_seeds=model_seeds,
                output_json=full_output_json
            )
        else:
            print(f"[{run_name}] Keeping existing input JSON, skipping regeneration.")
    else:
        print(f"[{run_name}] Creating input JSON → {full_output_json}")
        make_json_from_df(
            df=df,
            run_name=run_name,
            ion_default=ion_default,
            model_seeds=model_seeds,
            output_json=full_output_json
        )

    # ---------------- 2) Residue maps ----------------
    # (We treat presence of any files/dirs under residue_maps/<SimID> as “exists”.)
    if _dir_has_files(residuemap_dir):
        if _yesno(f"[{run_name}] Residue maps exist at {residuemap_dir}. Overwrite?"):
            _safe_rmtree(residuemap_dir)
            print(f"[{run_name}] Rebuilding residue maps in {residuemap_dir}")
            _run_residue_map_bot(full_output_json)
        else:
            print(f"[{run_name}] Keeping existing residue maps, skipping regeneration.")
    else:
        print(f"[{run_name}] Building residue maps in {residuemap_dir}")
        _run_residue_map_bot(full_output_json)

    # ---------------- 3) Alignments ----------------
    # (Likewise, any content under alignments/<SimID> triggers a prompt.)
    if _dir_has_files(alignments_dir):
        if _yesno(f"[{run_name}] Alignments exist at {alignments_dir}. Overwrite?"):
            _safe_rmtree(alignments_dir)
            print(f"[{run_name}] Rebuilding alignments (tool={alignment_tool}) in {alignments_dir}")
            _run_msa_bot(cfg_path)
        else:
            print(f"[{run_name}] Keeping existing alignments, skipping regeneration.")
    else:
        print(f"[{run_name}] Building alignments (tool={alignment_tool}) in {alignments_dir}")
        _run_msa_bot(cfg_path)


def main():
    """
    If no args: process all .yaml/.yml in config/.
    If one arg: treat as run-name or path, process only that.
    """
    if len(sys.argv) == 1:
        yaml_files = sorted(glob.glob(os.path.join(CONFIG_DIR, "*.yaml"))) + \
                     sorted(glob.glob(os.path.join(CONFIG_DIR, "*.yml")))
        if not yaml_files:
            print("ERROR: No config/*.yaml or config/*.yml found.", file=sys.stderr)
            sys.exit(1)
        for cfg_file in yaml_files:
            process_one_config(cfg_file)
    elif len(sys.argv) == 2:
        raw_arg = sys.argv[1]
        if os.path.isabs(raw_arg) and (raw_arg.lower().endswith(".yaml") or raw_arg.lower().endswith(".yml")):
            cfg_path = raw_arg
        elif os.path.isfile(raw_arg) and (raw_arg.lower().endswith(".yaml") or raw_arg.lower().endswith(".yml")):
            cfg_path = raw_arg
        else:
            if not (raw_arg.lower().endswith(".yaml") or raw_arg.lower().endswith(".yml")):
                candidate = raw_arg + ".yaml"
                path1 = os.path.join(CONFIG_DIR, candidate)
                raw_arg = candidate if os.path.isfile(path1) else raw_arg + ".yml"
            cfg_path = os.path.join(CONFIG_DIR, raw_arg)

        if not os.path.isfile(cfg_path):
            print(f"ERROR: Could not find config file '{cfg_path}'.", file=sys.stderr)
            sys.exit(1)

        process_one_config(cfg_path)
    else:
        print("Usage:", file=sys.stderr)
        print("  python src/01.0_run_create_input.py            # process all configs", file=sys.stderr)
        print("  python src/01.0_run_create_input.py Run0009   # only Run0009_*.yaml/.yml", file=sys.stderr)
        print("  python src/01.0_run_create_input.py <path/to/config>.yaml", file=sys.stderr)
        sys.exit(1)

    print("Done.")

if __name__ == "__main__":
    main()
