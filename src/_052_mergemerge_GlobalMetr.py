#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_052_mergemerge_GlobalMetr.py
Merge selected *merged* AF3 'model_confidences.csv' files using a YAML config.

Call with a single argument:
  - NAME   → uses config/NAME.yml
  - PATH   → if the argument ends with .yml/.yaml, use it directly

Config YAML schema (minimal):
  merge_name: "AtMLOvsAtEXO70"
  merges:
    - "AtMLO1vsAtEXO70"
    - "AtMLO2vsAtEXO70"
    ...

Inputs (implicit):
  ./Merge/<MergeName>/model_confidences.csv

Output (automatic unless overridden with --out):
  ./Mergemerge/<merge_name>/model_confidences.csv
"""

import os
import re
import argparse
from typing import List, Optional, Set, Any, Tuple
import pandas as pd

try:
    import yaml  # PyYAML
except Exception as e:
    raise SystemExit("Missing dependency 'PyYAML'. Install with: pip install pyyaml") from e


INPUT_ROOT  = os.path.join(".", "Merge")
OUTPUT_ROOT = os.path.join(".", "Mergemerge")

# Column order (kept consistent with _042; plus 'source_merge' near the front)
BASE_ORDER = [
    "source_merge",
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

def normalize_trivia_column(df: pd.DataFrame) -> pd.DataFrame:
    """Map any plausible trivia column to 'trivia_name' (if present)."""
    for a in ("trivia_name", "trivia", "name"):
        if a in df.columns:
            if a != "trivia_name":
                df = df.rename(columns={a: "trivia_name"})
            break
    return df

def add_mapping_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a 'mapping' column derived from job_folder.
    Safe even if mapping already exists.
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
        return tail

    if "mapping" in df.columns and df["mapping"].notna().any():
        # keep existing mapping unless it's empty and we can derive it
        if "job_folder" in df.columns:
            m = df["mapping"].astype(str).fillna("").str.strip()
            need = (m == "")
            if need.any():
                df.loc[need, "mapping"] = df.loc[need, "job_folder"].apply(extract_mapping)
        return df

    if "job_folder" in df.columns:
        df["mapping"] = df["job_folder"].apply(extract_mapping)
    else:
        df["mapping"] = ""
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

def parse_merges(val: Any) -> List[Tuple[str, str]]:
    """
    Return list of (merge_folder_name, source_merge_value).

    For your use-case, source_merge is simply the merge name listed under 'merges:'.
    """
    if val is None:
        raise SystemExit("Config is missing 'merges'.")
    if isinstance(val, (str, int)):
        val = [val]
    if not isinstance(val, list):
        raise SystemExit("Config key 'merges' must be a list (or a scalar).")

    out: List[Tuple[str, str]] = []
    for item in val:
        name = str(item).strip()
        if name:
            out.append((name, name))
    if not out:
        raise SystemExit("Config 'merges' contained no usable entries.")
    return out

def read_one_merge(merge_folder: str, source_merge: str) -> pd.DataFrame:
    csv_path = os.path.join(INPUT_ROOT, merge_folder, "model_confidences.csv")
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Missing: {csv_path}")

    df = pd.read_csv(csv_path, dtype=str)  # read as strings; coerce later
    df = normalize_trivia_column(df)

    # If a previous pipeline step already wrote source_merge, overwrite it deterministically
    if "source_merge" in df.columns:
        df = df.drop(columns=["source_merge"])

    df.insert(0, "source_merge", source_merge)

    # Ensure expected columns exist (robust to older merged outputs)
    if "job_folder" not in df.columns:
        df["job_folder"] = ""
    if "run_id" not in df.columns:
        df["run_id"] = ""

    return df

def main():
    ap = argparse.ArgumentParser(description="Merge already-merged AF3 model_confidences.csv using a YAML config.")
    ap.add_argument("config", help="Config name (uses config/<name>.yml) or a direct path to a YAML file.")
    ap.add_argument("--out", default=None, help="Optional explicit output CSV path; overrides config-derived path.")
    args = ap.parse_args()

    cfg = load_config(args.config)

    merge_name = cfg.get("merge_name")
    if not isinstance(merge_name, str) or not merge_name.strip():
        raise SystemExit("Config must define a non-empty 'merge_name' string.")
    merge_name = merge_name.strip()

    merges = parse_merges(cfg.get("merges"))

    frames: List[pd.DataFrame] = [read_one_merge(m, m) for (m, _) in merges]
    merged = pd.concat(frames, axis=0, ignore_index=True, sort=True)

    # Coerce numeric columns (base + dynamic patterns)
    for col in list(merged.columns):
        if looks_numeric_col(col):
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # Sort (stable) if present
    sort_cols = [c for c in ("source_merge", "run_id", "job_folder", "model_index") if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols, kind="stable")

    # Ensure mapping exists
    merged = add_mapping_column(merged)

    # Column order: preferred base first, then the rest (alphabetical)
    leading = [c for c in BASE_ORDER if c in merged.columns]
    trailing = [c for c in merged.columns if c not in leading]
    merged = merged[leading + sorted(trailing)]

    # Output path
    out_path = args.out or os.path.join(OUTPUT_ROOT, merge_name, "model_confidences.csv")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    merged.to_csv(out_path, index=False, na_rep="")

    print(f"[ok] Wrote {out_path}")
    print(f"Rows: {len(merged):,} | Columns: {len(merged.columns):,}")
    print("Merged inputs:")
    for m, _ in merges:
        print(f"  - {m}")

if __name__ == "__main__":
    main()