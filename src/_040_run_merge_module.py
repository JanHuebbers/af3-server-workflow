#!/usr/bin/env python3
"""
_040_run_merge_module.py — Module 4 wrapper (merge + plots)

Runs (in order):
  1) src/_041_merge_MSA.py
  2) src/_042_merge_GlobalMetr.py
  3) src/_043_merge_MinMetr.py
  4) src/_044_create_merge_plots.py

Usage:
  python src/_040_run_merge_module.py MergeAtMLO2vsAtCML12_fl_dIDR
  python src/_040_run_merge_module.py MergeAtMLO2vsAtCML12_fl_dIDR --yes
  python src/_040_run_merge_module.py MergeAtMLO2vsAtCML12_fl_dIDR --continue-on-error

Behavior:
- Prompts before each step (unless --yes).
- If expected outputs for a step already exist, asks whether to overwrite them.
- If a step fails, asks whether to continue (unless --yes, then controlled by flags).
"""

import os
import sys
import time
import logging
import argparse
import subprocess
import shutil
import re
from pathlib import Path

import yaml

from perm_helper import ensure_writable, sweep_fix_outputs


# -------------------------- logging & prompts --------------------------

def setup_logging(project_root: str):
    logs_dir = os.path.join(project_root, "src", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d%H%M")
    log_filename = f"{timestamp}_04_run_merge_module.log"
    log_path = os.path.join(logs_dir, log_filename)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger, log_path


def ask_yes_no(prompt: str, assume_yes: bool, logger=None) -> bool:
    """
    Ask a y/n question and return True if 'y'.

    If assume_yes=True, automatically returns True and logs.
    """
    if assume_yes:
        if logger:
            logger.info(f"[--yes] {prompt} -> auto-yes")
        return True
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        if logger:
            logger.warning(f"No stdin available for prompt: {prompt} -> defaulting to 'no'")
        return False


# -------------------------- config & paths --------------------------

def load_merge_config(merge_run_name: str, project_root: str, logger: logging.Logger):
    cfg_path = os.path.join(project_root, "config", f"{merge_run_name}.yml")
    if not os.path.isfile(cfg_path):
        logger.error(f"Cannot find merge config file: {cfg_path}")
        sys.exit(1)
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return Path(cfg_path), cfg


def safe_unlink(path: Path, logger: logging.Logger):
    try:
        if path.is_file():
            path.unlink()
            logger.info(f"Deleted file: {path}")
        elif path.is_dir():
            shutil.rmtree(path)
            logger.info(f"Deleted folder: {path}")
    except Exception as e:
        logger.warning(f"Could not delete {path}: {e}")


def is_date_dir(p: Path) -> bool:
    # e.g. 2026-02-24
    return p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name) is not None


# -------------------------- overwrite detection --------------------------

def step_outputs(merge_name: str, step: str) -> list[Path]:
    """
    Return a list of expected outputs for a given step (best-effort, conservative).
    """
    merge_dir = Path("Merge") / merge_name

    if step == "041":
        # _041_merge_MSA.py writes: Merge/<merge_name>/alignments/<tool>/...
        return [merge_dir / "alignments"]

    if step == "042":
        # _042_merge_GlobalMetr.py writes: Merge/<merge_name>/model_confidences.csv
        return [merge_dir / "model_confidences.csv"]

    if step == "043":
        # _043_merge_MinMetr.py writes: Merge/<merge_name>/minScoresperMSA_merged.xlsx
        return [merge_dir / "minScoresperMSA_merged.xlsx"]

    if step == "044":
        # _044_create_merge_plots.py writes dated folders under Merge/<merge_name>/<date>/...
        outs = []
        if merge_dir.is_dir():
            for child in merge_dir.iterdir():
                if is_date_dir(child):
                    outs.append(child)
        return outs

    return []


def any_exist(paths: list[Path]) -> bool:
    return any(p.exists() for p in paths)


def prompt_overwrite(paths: list[Path], step_label: str, assume_yes: bool, logger: logging.Logger) -> bool:
    """
    If any outputs exist, ask whether to overwrite (i.e., delete them).
    Returns True if we should proceed and overwrite (delete); False means "do not delete".
    """
    existing = [p for p in paths if p.exists()]
    if not existing:
        return False

    logger.warning(f"[{step_label}] Found existing outputs:")
    for p in existing:
        logger.warning(f"  - {p}")

    if ask_yes_no(f"[{step_label}] Overwrite (delete) these existing outputs? (y/n): ", assume_yes, logger):
        for p in existing:
            safe_unlink(p, logger)
        return True

    logger.info(f"[{step_label}] Keeping existing outputs (no deletion).")
    return False


# -------------------------- run step --------------------------

def run_step(
    *,
    label: str,
    script_path: Path,
    merge_run_name: str,
    assume_yes: bool,
    logger: logging.Logger,
    cwd: Path,
    continue_on_error: bool,
) -> bool:
    """
    Runs one step. Returns True if step succeeded, False if failed/skipped.
    On failure: prompt whether to continue (unless --yes; then uses continue_on_error).
    """
    if not script_path.is_file():
        logger.error(f"Missing script: {script_path}")
        sys.exit(1)

    if not ask_yes_no(f"Run {label} ({script_path.name})? (y/n): ", assume_yes, logger):
        logger.info(f"Skipping {label}.")
        return False

    logger.info(f"=== [Module 4] {label}: {script_path.name} {merge_run_name}")

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path), merge_run_name],
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

        if proc.stdout:
            logger.info("=== stdout ===")
            logger.info(proc.stdout)
        if proc.stderr:
            logger.info("=== stderr ===")
            logger.info(proc.stderr)

        if proc.returncode != 0:
            logger.error(f"{script_path.name} exited with code {proc.returncode}")

            # interactive: ask whether to continue
            if not assume_yes:
                if ask_yes_no(f"{label} failed. Continue with next step? (y/n): ", assume_yes, logger):
                    return False
                logger.info("Stopping due to failure (user chose not to continue).")
                sys.exit(proc.returncode)

            # non-interactive
            if continue_on_error:
                logger.warning(f"[--yes + --continue-on-error] continuing despite failure in {label}.")
                return False

            logger.info("[--yes + fail-fast] stopping on first failure.")
            sys.exit(proc.returncode)

        logger.info(f"{label} finished successfully.")
        return True

    except Exception:
        logger.exception(f"Failed while running {label}")
        if not assume_yes:
            if ask_yes_no(f"{label} crashed. Continue with next step? (y/n): ", assume_yes, logger):
                return False
        if continue_on_error:
            logger.warning(f"[--continue-on-error] continuing despite crash in {label}.")
            return False
        sys.exit(1)


# -------------------------- main --------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="python src/_040_run_merge_module.py",
        description="Run Module 4 merge pipeline: MSA merge, GlobalMetr merge, MinMetr merge, and merged plots.",
    )
    parser.add_argument("MergeName", help="Merge run name (config/<MergeName>.yml)")
    parser.add_argument(
        "--yes", "--assume-yes", "--non-interactive",
        dest="assume_yes",
        action="store_true",
        help="Non-interactive mode: automatically answer 'y' to all prompts.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="If set, keep going even if a step fails (useful with --yes).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="If set, stop immediately when a step fails (default behavior).",
    )
    args = parser.parse_args()

    merge_run_name = args.MergeName
    assume_yes = args.assume_yes

    # resolve failure policy (default: fail-fast)
    continue_on_error = bool(args.continue_on_error) and not bool(args.fail_fast)

    project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
    logger, log_path = setup_logging(str(project_root))
    logger.info(f"Log file initialized at: {log_path}")
    if assume_yes:
        logger.info("Running in non-interactive mode (--yes): all prompts will be auto-confirmed.")
        logger.info(f"Failure policy: {'continue-on-error' if continue_on_error else 'fail-fast'}")

    cfg_path, cfg = load_merge_config(merge_run_name, str(project_root), logger)
    merge_name = (cfg.get("merge_name") or "").strip()
    if not merge_name:
        logger.error(f"Config is missing non-empty 'merge_name': {cfg_path}")
        sys.exit(1)

    logger.info(f"Loaded merge config: {cfg_path}")
    logger.info(f"merge_name (trivia) = {merge_name!r}")

    steps = [
        ("Step 1: merge MSA",   "041", project_root / "src" / "_041_merge_MSA.py"),
        ("Step 2: merge Global metrics", "042", project_root / "src" / "_042_merge_GlobalMetr.py"),
        ("Step 3: merge Min metrics", "043", project_root / "src" / "_043_merge_MinMetr.py"),
        ("Step 4: create merged plots", "044", project_root / "src" / "_044_create_merge_plots.py"),
    ]

    logger.info("=== Module 4 wrapper starting ===")

    for label, code, script in steps:
        # If outputs exist for this step, ask whether to delete them (overwrite)
        outs = step_outputs(merge_name, code)
        if outs and any_exist(outs):
            prompt_overwrite(outs, label, assume_yes, logger)

        # For plots: even if user chose NOT to delete existing date folders,
        # still ask before running the plotting step (your original requirement)
        run_step(
            label=label,
            script_path=script,
            merge_run_name=merge_run_name,
            assume_yes=assume_yes,
            logger=logger,
            cwd=project_root,
            continue_on_error=continue_on_error,
        )

    # Best-effort: fix permissions on Merge/<merge_name>
    out_dir = project_root / "Merge" / merge_name
    if out_dir.is_dir():
        logger.info("=== Module 4 finished. Fixing permissions… ===")
        ensure_writable(str(out_dir))
        sweep_fix_outputs(str(out_dir))
    else:
        logger.warning(f"Merge output folder not found: {out_dir}")

    logger.info("=== All done. ===")


if __name__ == "__main__":
    main()