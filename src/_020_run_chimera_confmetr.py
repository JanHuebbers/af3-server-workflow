#!/usr/bin/env python
import os
import sys
import shutil
import subprocess
import yaml
import time
import logging
import gc
import platform
import ctypes
import argparse

from perm_helper import ensure_writable, sweep_fix_outputs


def setup_logging(project_root):
    # Create logs directory
    logs_dir = os.path.join(project_root, "src", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    # Timestamp for log filename
    timestamp = time.strftime("%Y%m%d%H%M")
    log_filename = f"{timestamp}_02_run_chimera_confmetr.log"
    log_path = os.path.join(logs_dir, log_filename)
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    # File handler
    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger, log_path


def trim_memory(logger):
    """Force GC and (on Linux/glibc) return freed heap to the OS."""
    try:
        gc.collect()
    except Exception as e:
        logger.debug(f"gc.collect() failed: {e}")
    try:
        if platform.system() == "Linux":
            libc = ctypes.CDLL("libc.so.6")
            res = libc.malloc_trim(0)
            logger.debug(f"malloc_trim(0) => {res}")
    except Exception as e:
        logger.debug(f"malloc_trim not available/failed: {e}")


def ask_yes_no(prompt: str, assume_yes: bool, logger=None) -> bool:
    """
    Ask a y/n question and return True if 'y'.

    If assume_yes=True, automatically returns True and (optionally) logs.
    """
    if assume_yes:
        if logger:
            logger.info(f"[--yes] {prompt} -> auto-yes")
        return True
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        # e.g. running under a scheduler / redirected stdin
        if logger:
            logger.warning(f"No stdin available for prompt: {prompt} -> defaulting to 'no'")
        return False


def load_config(run_name, project_root):
    config_path = os.path.join(project_root, "config", f"{run_name}.yml")
    if not os.path.isfile(config_path):
        logger.error(f"Cannot find config file {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_global_config(project_root):
    global_path = os.path.join(project_root, "config", "global.yml")
    if not os.path.isfile(global_path):
        logger.error(f"Global config file not found at {global_path}")
        sys.exit(1)
    with open(global_path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        prog="python src/_020_run_chimera_confmetr.py",
        description="Run ChimeraX + confidence + per-residue metrics + minScoresperMSA"
    )
    parser.add_argument("RunName", help="Run name (config/<RunName>.yml)")
    parser.add_argument(
        "--avg-only",
        action="store_true",
        help="Pass --avg-only to downstream per-residue metric scripts (_023_ and _024_)."
    )
    parser.add_argument(
        "--yes", "--assume-yes", "--non-interactive",
        dest="assume_yes",
        action="store_true",
        help="Non-interactive mode: automatically answer 'y' to all prompts."
    )
    args = parser.parse_args()

    run_name = args.RunName
    avg_only = args.avg_only
    assume_yes = args.assume_yes

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    global logger
    logger, log_path = setup_logging(project_root)
    logger.info(f"Log file initialized at: {log_path}")
    if assume_yes:
        logger.info("Running in non-interactive mode (--yes): all prompts will be auto-confirmed.")

    cfg = None
    try:
        cfg = load_config(run_name, project_root)
        global_cfg = load_global_config(project_root)
    except Exception:
        logger.exception("Failed to load config")
        sys.exit(1)

    # ChimeraX step configuration
    if "cx_script" not in cfg:
        logger.error(f"In config/{run_name}.yml, no 'cx_script' key found.")
        sys.exit(1)

    cx_filename = cfg["cx_script"]
    cx_scripts_dir = os.path.join(project_root, "ChimeraX", "cx_scripts")
    chosen_cxc = os.path.join(cx_scripts_dir, cx_filename)

    if not os.path.isfile(chosen_cxc):
        logger.error(f"ChimeraX script {chosen_cxc} does not exist.")
        sys.exit(1)

    # Derive sim_id (e.g., '0009')
    sim_id = None
    if run_name.lower().startswith("run") and len(run_name) >= 7:
        sim_id = run_name[3:7]
    logger.info(f"Parsed sim_id = {sim_id!r} from run_name = {run_name!r}")

    # === Module 2, Step 1: Run ChimeraX ===
    cx_base = os.path.splitext(os.path.basename(chosen_cxc))[0]
    chimx_run_dir = os.path.join(project_root, "ChimeraX", sim_id, cx_base)
    if os.path.isdir(chimx_run_dir):
        existing_cxs = [f for f in os.listdir(chimx_run_dir) if f.endswith(".cxs")]
        if existing_cxs:
            logger.info(f"Found existing .cxs in {chimx_run_dir}: {existing_cxs}")
            if not ask_yes_no("Overwrite all existing ChimeraX sessions? (y/n): ", assume_yes, logger):
                logger.info("Skipping ChimeraX-modeling step entirely.")
                goto_chimx = False
            else:
                shutil.rmtree(chimx_run_dir)
                os.makedirs(chimx_run_dir, exist_ok=True)
                goto_chimx = True
        else:
            goto_chimx = True
    else:
        os.makedirs(chimx_run_dir, exist_ok=True)
        goto_chimx = True

    if goto_chimx:
        logger.info(f"=== [Module 2] Step 1: Running ChimeraX with: {chosen_cxc}")
        chimerax_py = os.path.join(project_root, "src", "_021_ChimeraXBot.py")
        script_arg = f"\"{chimerax_py}\" \"{chosen_cxc}\" \"{sim_id}\""
        chimerax_exe = global_cfg.get("chimerax_path")
        if not chimerax_exe or not os.path.isfile(chimerax_exe):
            logger.error(f"ChimeraX executable not found or not specified in global config: {chimerax_exe}")
            sys.exit(1)
        cmd = [chimerax_exe, "--nogui", "--offscreen", "--script", script_arg]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            out, err = proc.communicate()
            logger.info("=== ChimeraX stdout ===")
            logger.info(out)
            logger.info("=== ChimeraX stderr ===")
            logger.info(err)
            if proc.returncode != 0:
                logger.error(f"ChimeraX exited with code {proc.returncode}")
                sys.exit(proc.returncode)
        except FileNotFoundError:
            logger.error("'ChimeraX-console' not found in PATH. Make sure ChimeraX's bin folder is on your PATH.")
            sys.exit(1)
    else:
        logger.info("=== ChimeraX step was skipped ===")

    # === Module 2, Step 2: Generate model_confidences.csv ===
    af3_run_dir = os.path.join(project_root, "AF3_output", sim_id) if sim_id else project_root
    os.makedirs(af3_run_dir, exist_ok=True)
    csv_path = os.path.join(af3_run_dir, "model_confidences.csv")
    # also generated by _022_ if ProtNames found
    map_path = os.path.join(af3_run_dir, "model_trivia_map.csv")
    skip_conf_step = False
    if os.path.exists(csv_path):
        logger.warning(f"CSV metrics file already exists at {csv_path}.")
        if not ask_yes_no("Overwrite existing model_confidences.csv? (y/n): ", assume_yes, logger):
            logger.info("Skipping confidence-metrics step (will continue to next steps).")
            skip_conf_step = True
        else:
            os.remove(csv_path)
            logger.info(f"Deleted old CSV: {csv_path}")
            # clean the mapping too, if present
            try:
                if os.path.exists(map_path):
                    os.remove(map_path)
                    logger.info(f"Deleted old CSV: {map_path}")
            except Exception as e:
                logger.warning(f"Could not delete old mapping CSV {map_path}: {e}")

    if not skip_conf_step:
        os.chdir(af3_run_dir)
        logger.info(f"Current working directory is now: {os.getcwd()!r}")
        getconf_script = os.path.join(project_root, "src", "_022_GlobalMetrBot.py")
        try:
            # Call _022_ WITH the config path (this version of _022_ accepts it).
            cfg_path = os.path.join(project_root, "config", f"{run_name}.yml")
            logger.info(f"Running _022_GlobalMetrBot.py with config: {cfg_path}")
            subprocess.run([sys.executable, getconf_script, cfg_path], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"_022_GlobalMetrBot.py failed with exit code {e.returncode}.")
            # continue to next steps anyway

    # === Module 2, Step 3: Generate per-residue metrics (average/annotated) ===
    logger.info("=== [Module 2] Step 3: Generate per-residue metrics ===")

    existing = []
    for root, _, files in os.walk(af3_run_dir):
        if "per_residue_metrics.xlsx" in files:
            existing.append(root)
    skip_res_step = False
    if existing:
        logger.warning("Found existing per_residue_metrics.xlsx in the following folders:")
        for folder in existing:
            logger.warning(f"  - {folder}")
        if not ask_yes_no("Proceed and OVERWRITE these files? (y/n): ", assume_yes, logger):
            logger.info("Skipping per-residue metrics extraction (will continue to next steps).")
            skip_res_step = True

    if not skip_res_step:
        if not ask_yes_no("Per-residue metrics extraction can take some time. Proceed? (y/n): ", assume_yes, logger):
            logger.info("User opted to skip per-residue metrics extraction (continuing).")
            skip_res_step = True

    if not skip_res_step:
        job_dirs = []
        for root, _, files in os.walk(af3_run_dir):
            if any(f.endswith(".json") and "_full_data_" in f for f in files):
                job_dirs.append(root)
        job_dirs = sorted(set(job_dirs))
        if not job_dirs:
            logger.warning("No AF3 job folders with *_full_data_*.json found. Skipping Step 3.")
        else:
            logger.info(f"Found {len(job_dirs)} job folder(s) to process.")
            getres_script = os.path.join(project_root, "src", "_023_ResMetrBot.py")

            start_time = time.time()
            for i, job_dir in enumerate(job_dirs, start=1):
                logger.info(f"[{i}/{len(job_dirs)}] Running _023_ResMetrBot.py for job: {job_dir}")
                try:
                    cmd = [sys.executable, getres_script, job_dir]
                    if avg_only:
                        cmd.append("--avg-only")
                    subprocess.run(cmd, check=True, cwd=project_root)
                except subprocess.CalledProcessError as e:
                    logger.error(f"_023_ResMetrBot.py failed in {job_dir} with exit code {e.returncode}.")
                finally:
                    trim_memory(logger)

            elapsed = time.time() - start_time
            logger.info(
                f"Per-residue metrics extraction finished over {len(job_dirs)} job(s) in {elapsed:.2f} seconds."
            )

    # === Module 2, Step 4: Generate minimum per-residue metrics ===
    logger.info("=== [Module 2] Step 4: Generate MINIMUM per-residue metrics (min-iPAE, minD, maxContact) ===")

    existing_min = []
    for root, _, files in os.walk(af3_run_dir):
        if "per_residue_metrics.xlsx" in files:
            existing_min.append(root)
    skip_min_step = False
    if existing_min:
        logger.warning("Found existing per_residue_metrics.xlsx (min-iPAE/minD/maxContact may already exist) in:")
        for folder in existing_min:
            logger.warning(f"  - {folder}")
        if not ask_yes_no(
            "Proceed and overwrite/append new min-iPAE, minD, and maxContact sheets? (y/n): ",
            assume_yes,
            logger
        ):
            logger.info("Skipping inter-chain min metrics extraction (will continue to next steps).")
            skip_min_step = True

    if not skip_min_step:
        if not ask_yes_no(
            "Run _024_MinMetrBot.py to compute inter-chain minPAE, minD, and maxContact vectors? (y/n): ",
            assume_yes,
            logger
        ):
            logger.info("User opted to skip minPAE extraction (continuing).")
            skip_min_step = True

    if not skip_min_step:
        start_time = time.time()
        getmin_script = os.path.join(project_root, "src", "_024_MinMetrBot.py")
        if not os.path.isfile(getmin_script):
            logger.error(f"_024_MinMetrBot.py not found at {getmin_script}.")
        else:
            try:
                cmd = [sys.executable, getmin_script, af3_run_dir]
                if avg_only:
                    cmd.append("--avg-only")
                subprocess.run(cmd, check=True, cwd=project_root)
            except subprocess.CalledProcessError as e:
                logger.error(f"_024_MinMetrBot.py failed with exit code {e.returncode}.")
            elapsed = time.time() - start_time
            logger.info(f"MIN per-residue metrics extraction completed in {elapsed:.2f} seconds.")

    # === Module 2, Step 5: Join align maps + min metrics into minScoresperMSA (run _025_) ===
    logger.info("=== [Module 2] Step 5: Join align maps + (min-iPAE, minD, maxContact) with MSA (AlignMinMetricsBot) ===")

    # Where _025_ writes
    csv_dir = os.path.join(af3_run_dir, "csv")
    ms_csv = os.path.join(csv_dir, "minScoresperMSA.csv")        # NEW location
    ms_xlsx = os.path.join(af3_run_dir, "minScoresperMSA.xlsx")  # Unchanged

    # Detect any existing outputs (xlsx + any CSVs in the csv/ subfolder)
    existing_outputs = []
    if os.path.exists(ms_xlsx):
        existing_outputs.append(ms_xlsx)
    if os.path.isdir(csv_dir):
        # include combined + per-chain CSVs
        for name in os.listdir(csv_dir):
            if name.endswith(".csv"):
                existing_outputs.append(os.path.join(csv_dir, name))

    # Overwrite prompt
    skip_025 = False
    if existing_outputs:
        logger.warning("minScoresperMSA outputs already exist:")
        for p in existing_outputs:
            logger.warning(f"  - {p}")
        if not ask_yes_no("Overwrite minScoresperMSA outputs? (y/n): ", assume_yes, logger):
            logger.info("Skipping _025_ AlignMinMetricsBot step.")
            skip_025 = True
        else:
            # Remove XLSX and clear csv/ folder
            for p in existing_outputs:
                try:
                    os.remove(p)
                    logger.info(f"Deleted old file: {p}")
                except IsADirectoryError:
                    try:
                        shutil.rmtree(p)
                        logger.info(f"Deleted old folder: {p}")
                    except Exception as e:
                        logger.warning(f"Could not delete {p}: {e}")
                except Exception as e:
                    logger.warning(f"Could not delete {p}: {e}")

    if not skip_025:
        # Ensure csv/ exists for the new per-chain + combined CSVs
        os.makedirs(csv_dir, exist_ok=True)

        _025_script = os.path.join(project_root, "src", "_025_AlignMinMetricsBot.py")
        cfg_path = os.path.join(project_root, "config", f"{run_name}.yml")
        if not os.path.isfile(_025_script):
            logger.error(f"_025_AlignMinMetricsBot.py not found at { _025_script }.")
        elif not os.path.isfile(cfg_path):
            logger.error(f"Run YAML not found at { cfg_path }.")
        else:
            logger.info(f"Running _025_AlignMinMetricsBot.py with config: {cfg_path}")
            try:
                subprocess.run([sys.executable, _025_script, cfg_path], check=True, cwd=project_root)
                logger.info("AlignMinMetricsBot finished successfully.")
                logger.info(f"Outputs: {ms_xlsx} and CSVs under {csv_dir}/")
            except subprocess.CalledProcessError as e:
                logger.error(f"_025_AlignMinMetricsBot.py failed with exit code {e.returncode}.")

    logger.info("=== Module 2 finished. Fixing permissions… ===")
    ensure_writable(af3_run_dir)
    sweep_fix_outputs(af3_run_dir)
    logger.info("=== All done. ===")


if __name__ == "__main__":
    main()