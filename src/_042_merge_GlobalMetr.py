#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_042_merge_GlobalMetr.py
Merge selected AF3 'model_confidences.csv' files using a YAML config.

Call with a single argument:
  - NAME   → uses config/NAME.yml
  - PATH   → if the argument ends with .yml/.yaml, use it directly

Config YAML schema (minimal):
  merge_name: "3AtMpHvMLO"
  runs:
    - "0049"
    - "0050"
    ...

Inputs (implicit):
  ./AF3_output/<Run_ID>/model_confidences.csv

Output (automatic unless overridden with --out):
  ./Merge/<merge_name>/model_confidences.csv
"""

import os
import re
import sys
import argparse
from typing import List, Dict, Optional, Set, Any
import pandas as pd

try:
    import yaml  # PyYAML
except Exception as e:
    raise SystemExit("Missing dependency 'PyYAML'. Install with: pip install pyyaml") from e

AF3_ROOT = os.path.join(".", "AF3_output")

# Column order (no sim_id; place trivia_name right after run_id)
BASE_ORDER = [
    "run_id", "Sample", "ProtNames", "trivia_name", "job_folder", "mapping",
    "model_index", "iptm", "ptm", "ranking_score",
    "fraction_disordered", "num_recycles",
]

DYNAMIC_PATTERNS = [
    re.compile(r"^chain_iptm_\d+$"),
    re.compile(r"^pair_iptm_\d+_\d+$"),
    re.compile(r"^pair_pae_min_\d+_\d+$"),
]

NUMERIC_BASE = {
    "model_index", "iptm", "ptm", "ranking_score",
    "fraction_disordered", "num_recycles"
}

def looks_numeric_col(col: str) -> bool:
    if col in NUMERIC_BASE:
        return True
    return any(p.match(col) for p in DYNAMIC_PATTERNS)

def add_mapping_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'mapping' column derived from job_folder.

    Preferred logic:
      - If job_folder starts with the fixed 13-char prefix like '0135-01-1710_',
        mapping = job_folder[13:].
    Special case:
      - If the resulting tail contains "0ions_", mapping is only the part AFTER "0ions_".
        e.g. '..._0ions_3atmlo1' -> '3atmlo1'
    Fallback:
      - If job_folder missing or not a string, mapping = "".
    """
    def extract_mapping(jf: str) -> str:
        if not isinstance(jf, str):
            return ""

        # 1) Fixed-prefix slice (expects "####-##-####_" = 13 chars)
        tail = jf[13:] if len(jf) > 13 and jf[12] == "_" else jf

        # 2) Special case: if "0ions_" is present, only keep what comes after it
        z = tail.rfind("0ions_")
        if z != -1:
            return tail[z + len("0ions_"):]

        # 3) Otherwise keep the sliced tail as mapping
        return tail

    if "job_folder" in df.columns:
        df["mapping"] = df["job_folder"].apply(extract_mapping)
    else:
        df["mapping"] = ""
    return df

def normalize_trivia_column(df: pd.DataFrame) -> pd.DataFrame:
    """Map any plausible trivia column to 'trivia_name' (if present)."""
    for a in ("trivia_name", "trivia", "name"):
        if a in df.columns:
            if a != "trivia_name":
                df = df.rename(columns={a: "trivia_name"})
            break
    return df

def read_one(run_id: str) -> pd.DataFrame:
    csv_path = os.path.join(AF3_ROOT, run_id, "model_confidences.csv")
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Missing: {csv_path}")
    df = pd.read_csv(csv_path, dtype=str)  # read as strings; coerce later
    df.insert(0, "run_id", run_id)
    if "job_folder" not in df.columns:
        df["job_folder"] = ""
    df = normalize_trivia_column(df)
    return df

def load_config(arg: str) -> dict:
    """Resolve and load YAML: 'NAME' → config/NAME.yml, else if .yml/.yaml use as-is."""
    if arg.lower().endswith((".yml", ".yaml")):
        cfg_path = arg
    else:
        cfg_path = os.path.join("config", f"{arg}.yml")
    if not os.path.isfile(cfg_path):
        raise SystemExit(f"Config not found: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg

def parse_runs(runs_val) -> List[str]:
    """Accept list of strings/ints; coerce to 4-digit zero-padded strings."""
    if runs_val is None:
        raise SystemExit("Config is missing 'runs'.")
    if isinstance(runs_val, (str, int)):
        runs_val = [runs_val]
    if not isinstance(runs_val, list):
        raise SystemExit("Config key 'runs' must be a list (or a scalar).")
    out = []
    for x in runs_val:
        if isinstance(x, int):
            s = f"{x:04d}"
        else:
            s = str(x).strip()
            # pad left if it looks like digits and shorter than 4
            if s.isdigit() and len(s) < 4:
                s = f"{int(s):04d}"
        if not re.fullmatch(r"\d{4}", s):
            raise SystemExit(f"Invalid Run_ID in 'runs': {x!r} (expect 4 digits)")
        out.append(s)
    return out

def index_to_letters(idx: int) -> str:
    """
    Convert 0-based index to Excel-like letters:
      0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA, ...
    """
    s = ""
    n = idx
    while True:
        n, r = divmod(n, 26)
        s = chr(ord("A") + r) + s
        if n == 0:
            break
        n -= 1
    return s

def _coerce_model_list(x: Any) -> Optional[Set[str]]:
    """
    Convert a model spec to a set of string model_index values.
    Return None if 'all models' should be included for that job.
    """
    if x is None:
        return None
    if isinstance(x, str):
        s = x.strip()
        if s == "" or s.lower() in ("all", "any", "none"):
            return None
        # allow comma-separated
        parts = [p.strip() for p in s.split(",") if p.strip() != ""]
        if not parts:
            return None
        return set(parts)
    if isinstance(x, int):
        return {str(x)}
    if isinstance(x, list):
        if len(x) == 0:
            return None
        out = set()
        for v in x:
            if v is None:
                continue
            if isinstance(v, int):
                out.add(str(v))
            else:
                vs = str(v).strip()
                if vs != "":
                    out.add(vs)
        return out if out else None
    # fallback
    xs = str(x).strip()
    return {xs} if xs else None

def _normalize_job_key(x: Any) -> Optional[str]:
    """
    Normalize include job key to '####_##' (run_id + '_' + 2-digit job number).

    Accepts:
      - '0132_01'
      - '0132-01'                -> normalized to '0132_01'
      - '0132_01_1706_0ions_...'  -> normalized to '0132_01'
      - '0132-01-1706_...'       -> normalized to '0132_01'
    """
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})[-_](\d{2})", s)
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}"

def parse_include(include_val: Any) -> Dict[str, Optional[Set[str]]]:
    """
    Parse config 'include' into: { '####_##': set(models) or None(for all models) }.

    Supported formats:

    A) List-of-dicts (recommended):
      include:
        - job_id: "0132_01"
          model: [0,1,2]
        - job_id: "0132_09"
          model: []   # => all models for this job

    B) Dict with parallel lists:
      include:
        job_id: ["0132_01", "0132_09"]
        model:  [[0,1], []]
    """
    out: Dict[str, Optional[Set[str]]] = {}
    if include_val is None:
        return out

    # A) list-of-dicts
    if isinstance(include_val, list):
        for item in include_val:
            if not isinstance(item, dict):
                continue
            job_raw = item.get("job_id") or item.get("job") or item.get("job_key") or item.get("job_folder")
            job_key = _normalize_job_key(job_raw)
            if not job_key:
                continue
            models_spec = item.get("model") if "model" in item else item.get("models")
            out[job_key] = _coerce_model_list(models_spec)
        return out

    # B) dict with lists
    if isinstance(include_val, dict):
        job_ids = include_val.get("job_id") or include_val.get("job") or include_val.get("job_key") or []
        models  = include_val.get("model") if "model" in include_val else include_val.get("models")

        if isinstance(job_ids, (str, int)):
            job_ids = [job_ids]
        if not isinstance(job_ids, list):
            return out

        job_keys = []
        for jid in job_ids:
            jk = _normalize_job_key(jid)
            if jk:
                job_keys.append(jk)

        if models is None:
            for jk in job_keys:
                out[jk] = None
            return out

        if isinstance(models, (str, int)):
            mset = _coerce_model_list(models)
            for jk in job_keys:
                out[jk] = mset
            return out

        if isinstance(models, list):
            for i, jk in enumerate(job_keys):
                mspec = models[i] if i < len(models) else None
                out[jk] = _coerce_model_list(mspec)
            return out

    return out

def apply_include_filter(df: pd.DataFrame, include_map: Dict[str, Optional[Set[str]]]) -> pd.DataFrame:
    """
    Keep only rows where:
      - job_folder starts with '<####_##>_', where '####_##' is an include_map key, AND
      - if include_map['####_##'] is a set: model_index in that set
      - if include_map['####_##'] is None: all model_index allowed

    Robust to model_index being numeric (e.g. 4.0) or string.
    """
    if df.empty:
        return df
    if not include_map:
        # nothing specified -> include nothing (since user explicitly requested include-only mode)
        return df.iloc[0:0].copy()

    out = df.copy()

    if "job_folder" not in out.columns:
        out["job_folder"] = ""
    if "model_index" not in out.columns:
        out["model_index"] = ""

    job_series = out["job_folder"].astype(str)

    # Normalize model_index to canonical integer strings ("4", not "4.0")
    mi_num = pd.to_numeric(out["model_index"], errors="coerce")
    mi_str = out["model_index"].astype(str).str.strip()
    mi_norm = mi_str.where(mi_num.isna(), mi_num.round(0).astype("Int64").astype(str))

    keep = pd.Series(False, index=out.index)

    for job_key, models_set in include_map.items():
        prefix = f"{job_key}_"
        mask_job = job_series.str.startswith(prefix, na=False)

        if models_set is None:
            keep = keep | mask_job
        else:
            # normalize include models too
            models_set_norm = set()
            for m in models_set:
                ms = str(m).strip()
                try:
                    models_set_norm.add(str(int(float(ms))))
                except Exception:
                    if ms != "":
                        models_set_norm.add(ms)

            keep = keep | (mask_job & mi_norm.isin(models_set_norm))

    return out.loc[keep].copy()

##------------------------------------------------------------------------------##
################ MAIN FUNCTION ###################################################
##------------------------------------------------------------------------------##

def main():
    ap = argparse.ArgumentParser(description="Merge AF3 model_confidences.csv using a YAML config.")
    ap.add_argument("config", help="Config name (uses config/<name>.yml) or a direct path to a YAML file.")
    ap.add_argument("--out", default=None, help="Optional explicit output CSV path; overrides config-derived path.")
    ap.add_argument(
        "--include",
        action="store_true",
        help="Include-only mode: keep ONLY jobs/models listed under config key 'include'."
    )
    args = ap.parse_args()

    cfg = load_config(args.config)

    merge_name = cfg.get("merge_name")
    if not isinstance(merge_name, str) or not merge_name.strip():
        raise SystemExit("Config must define a non-empty 'merge_name' string.")
    merge_name = merge_name.strip()

    run_ids = parse_runs(cfg.get("runs"))

    # Optional sample mapping from config (mapping -> Sample, ProtNames)
    samples_cfg = cfg.get("Samples") or {}
    explicit_samples = bool(samples_cfg)

    sample_rows = []
    if explicit_samples:
        for sample_letter, info in samples_cfg.items():
            if not isinstance(info, dict):
                continue
            mapping_val = info.get("mapping")
            # support both 'prot_name' and 'trivia' keys
            prot_name   = info.get("prot_name") or info.get("ProtNames") or info.get("trivia")
            if mapping_val:
                sample_rows.append(
                    {"mapping": mapping_val, "Sample": sample_letter, "ProtNames": prot_name or mapping_val}
                )

    samples_df_cfg = pd.DataFrame(sample_rows) if sample_rows else None

    # Load each run
    frames: List[pd.DataFrame] = [read_one(rid) for rid in run_ids]

        # Unioned vertical concat
    merged = pd.concat(frames, axis=0, ignore_index=True, sort=True)

    # Coerce numeric columns (base + dynamic patterns)
    for col in list(merged.columns):
        if looks_numeric_col(col):
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # Sort rows by run_id, job_folder, model_index (if present)
    sort_cols = [c for c in ("run_id", "job_folder", "model_index") if c in merged.columns]
    merged = merged.sort_values(sort_cols, kind="stable")

    # Add mapping column from job_folder
    merged = add_mapping_column(merged)

    # ---- INCLUDE-ONLY FILTERING (optional) ----
    # If --include is set, keep ONLY the jobs/models listed under cfg['include'].
    include_map = parse_include(cfg.get("include"))
    if args.include:
        before = len(merged)
        merged = apply_include_filter(merged, include_map)
        after = len(merged)

        # Helpful console output
        print(f"[include] enabled | include rules: {len(include_map)} job(s)")
        print(f"[include] rows before: {before:,} | after: {after:,}")

    # Attach Sample + ProtNames:
    #  - if Samples block is present in config: use that mapping
    #  - otherwise: auto-generate Sample letters and use mapping as ProtNames
    if explicit_samples and samples_df_cfg is not None and not samples_df_cfg.empty:
        # Use user-provided Samples mapping
        merged = merged.merge(samples_df_cfg, on="mapping", how="left")
    else:
        # Auto fallback: Sample letters from mapping, ProtNames = mapping
        unique_mapping = [m for m in pd.unique(merged.get("mapping", [])) if isinstance(m, str) and m != ""]
        auto_rows = []
        for idx, mval in enumerate(unique_mapping):
            auto_rows.append(
                {
                    "mapping":   mval,
                    "Sample":    index_to_letters(idx),  # A,B,C,...
                    "ProtNames": mval,
                }
            )
        samples_df_auto = pd.DataFrame(auto_rows) if auto_rows else None
        if samples_df_auto is not None and not samples_df_auto.empty:
            merged = merged.merge(samples_df_auto, on="mapping", how="left")

    # Column order: preferred base first, then the rest (alphabetical)
    leading = [c for c in BASE_ORDER if c in merged.columns]
    trailing = [c for c in merged.columns if c not in leading]
    merged = merged[leading + sorted(trailing)]

    # Output path
    out_path = args.out or os.path.join(".", "Merge", merge_name, "model_confidences.csv")

    # Ensure output directory exists
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Write with real blanks
    merged.to_csv(out_path, index=False, na_rep="")

    print(f"[ok] Wrote {out_path}")
    print(f"Rows: {len(merged):,} | Columns: {len(merged.columns):,}")
    print(f"Run_IDs merged: {', '.join(run_ids)}")

if __name__ == "__main__":
    main()
