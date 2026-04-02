#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_043_merge_MinMetr.py — Module 4 merged minScoresperMSA (CSV-first; no job folders required)

Reads per-run outputs that you KEEP:
  - Preferred: AF3_output/<run_id>/csv/<run_id>_<chain>.csv
  - Fallback: AF3_output/<run_id>/minScoresperMSA.xlsx (chain sheets)

Computes per-run mean across seed/job columns:
  - mean(min-iPAE) across columns like "0132-01_min-iPAE" ... "0132-12_min-iPAE"
  - mean(minD)     across "0132-01_minD" ... etc.
  - mean(maxContact) across "0132-01_maxContact" ... etc.

Maps per-run metrics onto the merged MSA axis using _041 outputs:
  Merge/<merge_name>/alignments/<tool>/<merge_name>_<chain>_align_map.csv
  columns: chain, aln_pos, run_id, res_idx, aa_aln

Outputs:
  Merge/<merge_name>/minScoresperMSA_merged.xlsx
    - one sheet per chain (A, B, ...)
    - Combined_T
    - CombinedT_minPAE
    - CombinedT_minD
    - CombinedT_maxContact

Usage:
  python src/_043_merge_MinMetr.py <MERGE_CFG>
"""

from __future__ import annotations

import re
import sys
import json
import logging
from pathlib import Path
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml
from xlsxwriter.utility import xl_rowcol_to_cell

from perm_helper import ensure_writable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AF3_ROOT   = Path("AF3_output")
MERGE_ROOT = Path("Merge")


# ---------------------------- Config helpers --------------------------

def resolve_cfg_path(arg: str) -> Path:
    if arg.lower().endswith((".yml", ".yaml")):
        p = Path(arg)
    else:
        p = Path("config") / f"{arg}.yml"
    if not p.is_file():
        raise FileNotFoundError(f"Config not found: {p}")
    return p

def read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def parse_runs(runs_val) -> List[str]:
    if runs_val is None:
        raise ValueError("Config missing 'runs'.")
    if isinstance(runs_val, (str, int)):
        runs_val = [runs_val]
    if not isinstance(runs_val, list):
        raise ValueError("'runs' must be a list.")
    out: List[str] = []
    for x in runs_val:
        if isinstance(x, int):
            s = f"{x:04d}"
        else:
            s = str(x).strip()
            if s.isdigit() and len(s) < 4:
                s = f"{int(s):04d}"
        if not re.fullmatch(r"\d{4}", s):
            raise ValueError(f"Invalid run_id: {x!r}")
        out.append(s)
    # de-dup keep order
    seen, uniq = set(), []
    for r in out:
        if r not in seen:
            uniq.append(r); seen.add(r)
    return uniq


# --------------------------- Small utilities --------------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def select_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None

def consensus_aa(aa_list) -> str:
    filtered = [a for a in aa_list if a not in ("-", "NA", "", None) and not pd.isna(a)]
    if not filtered:
        return "-"
    counts = Counter([str(x).upper() for x in filtered]).most_common()
    if len(counts) == 1 or (len(counts) > 1 and counts[0][1] > counts[1][1]):
        return counts[0][0]
    top = counts[0][1]
    tied = sorted([aa for aa, n in counts if n == top])
    return tied[0] if tied else "-"


# --------------------- Locate merged alignments (from _041_) ---------------------

def find_merge_alignment_dir(merge_name: str) -> Path:
    base = MERGE_ROOT / merge_name / "alignments"
    if not base.is_dir():
        raise FileNotFoundError(f"Missing: {base} (run _041_merge_MSA.py first)")
    for tool_dir in sorted(base.iterdir()):
        if tool_dir.is_dir() and (tool_dir / "merge_msa_summary.json").is_file():
            return tool_dir
    raise FileNotFoundError(f"No merge_msa_summary.json under {base} (run _041_merge_MSA.py first)")

def load_align_maps_by_chain(merge_name: str, tool_dir: Path) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for fp in sorted(tool_dir.glob(f"{merge_name}_*_align_map.csv")):
        m = re.search(rf"^{re.escape(merge_name)}_([A-Za-z0-9]+)_align_map\.csv$", fp.name)
        if not m:
            continue
        chain = m.group(1)
        df = pd.read_csv(fp)

        chain_col = select_col(df, ["chain", "chain_id"]) or "chain"
        aln_col   = select_col(df, ["aln_pos", "msa_pos"]) or "aln_pos"
        run_col   = select_col(df, ["run_id", "run"]) or "run_id"
        pos_col   = select_col(df, ["res_idx", "chain_pos"]) or "res_idx"
        aa_col    = select_col(df, ["aa_aln", "aa"]) or "aa_aln"

        miss = [c for c in (chain_col, aln_col, run_col, pos_col, aa_col) if c not in df.columns]
        if miss:
            raise KeyError(f"Align map {fp} missing columns: {miss}")

        df = df.rename(columns={
            chain_col: "chain",
            aln_col: "aln_pos",
            run_col: "run_id",
            pos_col: "res_idx",
            aa_col: "aa_aln",
        })

        df["chain"] = df["chain"].astype(str).str.strip()
        df["run_id"] = (
            pd.to_numeric(df["run_id"], errors="coerce")
            .astype("Int64")
            .astype(str)
            .str.replace("<NA>", "", regex=False)
            .str.zfill(4)
        )
        df["aln_pos"] = pd.to_numeric(df["aln_pos"], errors="coerce").astype("Int64")
        df["res_idx"] = pd.to_numeric(df["res_idx"], errors="coerce").astype("Int64")
        df["aa_aln"] = df["aa_aln"].astype(str).replace({"nan": "-"}).str.upper()

        out[chain] = df[df["chain"] == chain].copy()

    if not out:
        raise FileNotFoundError(f"No align maps found in {tool_dir}")
    return out


# ------------------- Read per-run per-chain inputs (CSV preferred) -------------------

JOB_PREFIX_RE = re.compile(r"^(?P<rid>\d{4})[-_](?P<job>\d{2})_(?P<rest>.+)$")

def find_run_chain_csv(run_id: str, chain: str) -> Optional[Path]:
    p = AF3_ROOT / run_id / "csv" / f"{run_id}_{chain}.csv"
    return p if p.is_file() else None

def read_run_chain_table(run_id: str, chain: str) -> pd.DataFrame:
    """
    Returns a DataFrame with at least: chain, msa_pos, cons_aa, and job metric columns.
    Prefer CSV; fallback to Excel chain sheet (using header=1 to handle 2-row header).
    """
    csvp = find_run_chain_csv(run_id, chain)
    if csvp is not None:
        df = pd.read_csv(csvp)
        return df

    xlsx = AF3_ROOT / run_id / "minScoresperMSA.xlsx"
    if not xlsx.is_file():
        raise FileNotFoundError(f"Missing both CSV and XLSX for run {run_id} chain {chain}")

    # chain sheet is typically named exactly by chain letter (e.g., "A")
    with pd.ExcelFile(xlsx) as xls:
        if chain not in xls.sheet_names:
            raise FileNotFoundError(f"Run {run_id}: sheet '{chain}' not found in {xlsx}")
        # two-row header → column names on second row
        df = pd.read_excel(xls, sheet_name=chain, header=1)
    return df


# ------------------- Collapse job columns to run-mean metrics -------------------

def collapse_to_run_means(df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """
    Input df resembles _025 output:
      chain, msa_pos, cons_aa,
      <job>_chain_pos, <job>_aa,
      <job>_min-iPAE, <job>_minD, <job>_maxContact

    Output keeps:
      chain, msa_pos, cons_aa,
      <run_id>_chain_pos, <run_id>_aa,
      <run_id>_min-iPAE, <run_id>_minD, <run_id>_maxContact
    """
    df = df.copy()

    chain_col = select_col(df, ["chain"]) or "chain"
    msa_col   = select_col(df, ["msa_pos", "aln_pos"]) or "msa_pos"
    cons_col  = select_col(df, ["cons_aa"]) or "cons_aa"
    if chain_col not in df.columns or msa_col not in df.columns:
        raise KeyError(f"Run {run_id}: missing required columns 'chain' and/or 'msa_pos'")

    # metric job columns
    def job_metric_cols(metric_suffix: str) -> List[str]:
        cols = []
        for c in df.columns:
            if isinstance(c, str):
                m = JOB_PREFIX_RE.match(c)
                if m and m.group("rid") == run_id and m.group("rest") == metric_suffix:
                    cols.append(c)
        return sorted(cols)

    cols_ipae = job_metric_cols("min-iPAE")
    cols_minD = job_metric_cols("minD")
    cols_maxC = job_metric_cols("maxContact")

    if not (cols_ipae or cols_minD or cols_maxC):
        # Sometimes CSV columns may use "-" in jobkey but suffixes match; if nothing found, fall back by suffix only
        for metric_suffix, store in [("min-iPAE", "cols_ipae"), ("minD", "cols_minD"), ("maxContact", "cols_maxC")]:
            pass  # keep simple; user data matches pattern in your examples

    out = pd.DataFrame({
        "chain": df[chain_col].astype(str).str.strip(),
        "msa_pos": pd.to_numeric(df[msa_col], errors="coerce").astype("Int64"),
        "cons_aa": df[cons_col].astype(str).str.upper() if cons_col in df.columns else "-",
    })

    # chain_pos / aa tracks for the run: use msa_pos as chain_pos (your stated assumption)
    out[f"{run_id}_chain_pos"] = out["msa_pos"].astype("Int64")
    out[f"{run_id}_aa"] = out["cons_aa"]

    # run mean metrics
    def mean_across(cols: List[str]) -> pd.Series:
        if not cols:
            return pd.Series([np.nan] * len(df), index=df.index)
        mat = pd.concat([pd.to_numeric(df[c], errors="coerce") for c in cols], axis=1)
        return mat.mean(axis=1, skipna=True)

    out[f"{run_id}_min-iPAE"] = mean_across(cols_ipae)
    out[f"{run_id}_minD"] = mean_across(cols_minD)
    out[f"{run_id}_maxContact"] = mean_across(cols_maxC)

    return out


# ------------------- Map run means onto merged MSA axis -------------------

def map_run_to_merged(chain: str, run_id: str, run_df: pd.DataFrame, align_map_chain: pd.DataFrame) -> pd.DataFrame:
    """
    run_df has msa_pos (treated as native res_idx) and run mean columns.
    align_map_chain provides mapping: (run_id, res_idx) -> merged aln_pos, plus aa_aln.

    Output columns include:
      chain, msa_pos (merged), cons_aa (merged consensus across runs), <run mean cols>, <run chain_pos/aa>
    """
    df = run_df.copy()
    df["res_idx"] = pd.to_numeric(df[f"{run_id}_chain_pos"], errors="coerce").astype("Int64")

    amap = align_map_chain.copy()
    amap = amap[(amap["run_id"] == run_id)].dropna(subset=["aln_pos"])
    amap = amap[["aln_pos", "res_idx"]].dropna(subset=["res_idx"]).copy()
    amap["res_idx"] = amap["res_idx"].astype("Int64")
    amap["aln_pos"] = amap["aln_pos"].astype("Int64")

    merged = df.merge(amap, how="left", on="res_idx")
    merged = merged.dropna(subset=["aln_pos"]).copy()
    merged["chain"] = chain
    merged["msa_pos"] = merged["aln_pos"].astype("Int64")
    merged = merged.drop(columns=["aln_pos", "res_idx"], errors="ignore")

    return merged


# ---------------- Excel writer + Transposed sheets (same style as _025_) -----------------

def build_transposed(per_chain_tables: Dict[str, pd.DataFrame],
                     run_ids: List[str],
                     metric_rows: List[str]) -> pd.DataFrame:
    chain_order = sorted(per_chain_tables.keys(), key=lambda x: str(x))
    col_labels, chains_flat, msapos_flat, consaa_flat = [], [], [], []

    rows_dict = {lab: [] for lab in metric_rows}
    pos_rows  = {f"Chain_pos_{rid}": [] for rid in run_ids}
    aa_rows   = {f"Chain_aa_{rid}":  [] for rid in run_ids}

    for ch in chain_order:
        dfc = per_chain_tables[ch].sort_values("msa_pos")
        for _, r in dfc.iterrows():
            col_labels.append(f"{ch}:{int(r['msa_pos'])}")
            chains_flat.append(ch)
            msapos_flat.append(int(r["msa_pos"]))
            consaa_flat.append(r["cons_aa"])

            for lab in metric_rows:
                rid, mname = lab.split("|", 1)
                col = f"{rid}_{mname}"
                rows_dict[lab].append(r[col] if col in dfc.columns else np.nan)

            for rid in run_ids:
                pos_rows[f"Chain_pos_{rid}"].append(r.get(f"{rid}_chain_pos", np.nan))
                aa_rows[f"Chain_aa_{rid}"].append(r.get(f"{rid}_aa", "-"))

    rows, labels = [], []
    def add_row(label, vals): labels.append(label); rows.append(vals)

    add_row("Chain",   chains_flat)
    add_row("msa_pos", msapos_flat)
    add_row("cons_aa", consaa_flat)

    for lab in metric_rows:
        rid, mname = lab.split("|", 1)
        add_row(f"{rid}_{mname}", rows_dict[lab])

    for rid in run_ids:
        add_row(f"Chain_pos_{rid}", pos_rows[f"Chain_pos_{rid}"])
        add_row(f"Chain_aa_{rid}",  aa_rows[f"Chain_aa_{rid}"])

    return pd.DataFrame(rows, index=labels, columns=col_labels)

def write_transposed_sheet(writer, tdf: pd.DataFrame, sheet_name: str, color_rows: Dict[str, dict]):
    tdf = tdf.copy().replace({pd.NA: np.nan})

    def _coerce_float_or_nan(x):
        if pd.isna(x) or (isinstance(x, str) and x.strip() == ""):
            return np.nan
        try:
            return float(x)
        except Exception:
            return x

    for idx in tdf.index:
        if (idx == "msa_pos") or idx.startswith("Chain_pos_") or \
           idx.endswith("_min-iPAE") or idx.endswith("_minD") or idx.endswith("_maxContact"):
            tdf.loc[idx] = tdf.loc[idx].map(_coerce_float_or_nan)

    tname = re.sub(r"[^A-Za-z0-9 _-]", "_", sheet_name)[:31] or "Sheet"
    tdf.to_excel(writer, sheet_name=tname, index=True, na_rep="")
    ws = writer.sheets[tname]
    wb = writer.book

    fmt_idx  = wb.add_format({"bold": True})
    fmt_head = wb.add_format({"bold": True})
    fmt_dec2 = wb.add_format({"num_format": "0.00"})
    fmt_int  = wb.add_format({"num_format": "0"})

    ws.freeze_panes(1, 1)
    ws.set_row(0, None, fmt_head)
    ws.set_column(0, 0, 18, fmt_idx)
    ncols = len(tdf.columns)
    for j in range(1, ncols + 1):
        ws.set_column(j, j, 10)

    for r, label in enumerate(tdf.index, start=1):
        if label == "msa_pos" or label.startswith("Chain_pos_"):
            ws.set_row(r, None, fmt_int)
        elif label.endswith("_min-iPAE") or label.endswith("_minD") or label.endswith("_maxContact"):
            ws.set_row(r, None, fmt_dec2)

    MIN_COLOR = "#B65256"
    MID_COLOR = "#FABE50"
    MAX_COLOR = "#2D7F83"

    def apply_colorscale(row_labels: List[str], vmin: float, vmid: float, vmax: float, invert: bool = False):
        min_col = MAX_COLOR if invert else MIN_COLOR
        max_col = MIN_COLOR if invert else MAX_COLOR
        mid_col = MID_COLOR
        idxs = [i for i, lab in enumerate(tdf.index, start=1) if lab in row_labels]
        if not idxs:
            return
        r1, r2 = min(idxs), max(idxs)
        ws.conditional_format(r1, 1, r2, ncols, {
            "type": "3_color_scale",
            "min_type": "num", "min_value": vmin, "min_color": min_col,
            "mid_type": "num", "mid_value": vmid, "mid_color": mid_col,
            "max_type": "num", "max_value": vmax, "max_color": max_col,
        })

    for _, spec in color_rows.items():
        apply_colorscale(spec["rows"], spec["vmin"], spec["vmid"], spec["vmax"], invert=spec.get("invert", False))

    # AA category shading
    fmt_unpolar = wb.add_format({"bg_color": "#8DC060"})
    fmt_polar   = wb.add_format({"bg_color": "#FABE50"})
    fmt_pos     = wb.add_format({"bg_color": "#2D7F83"})
    fmt_neg     = wb.add_format({"bg_color": "#B65256"})
    UNPOLAR = ["A","V","L","I","M","F","W","P","G"]
    POLAR   = ["S","T","N","Q","Y","C"]
    POS     = ["K","R","H"]
    NEG     = ["D","E"]

    for idx in tdf.index:
        if idx == "cons_aa" or idx.startswith("Chain_aa_"):
            tdf.loc[idx] = tdf.loc[idx].astype(str).str.upper()

    def _or_eq(cell_ref: str, values: list[str]) -> str:
        return "OR(" + ",".join([f'{cell_ref}="{v}"' for v in values]) + ")"

    aa_row_idxs = [i for i, lab in enumerate(tdf.index, start=1)
                   if lab == "cons_aa" or lab.startswith("Chain_aa_")]
    for r in aa_row_idxs:
        left_cell = xl_rowcol_to_cell(r, 1, row_abs=False, col_abs=False)
        ws.conditional_format(r, 1, r, ncols, {"type": "formula", "criteria": f"={_or_eq(left_cell, UNPOLAR)}", "format": fmt_unpolar})
        ws.conditional_format(r, 1, r, ncols, {"type": "formula", "criteria": f"={_or_eq(left_cell, POLAR)}",   "format": fmt_polar})
        ws.conditional_format(r, 1, r, ncols, {"type": "formula", "criteria": f"={_or_eq(left_cell, POS)}",     "format": fmt_pos})
        ws.conditional_format(r, 1, r, ncols, {"type": "formula", "criteria": f"={_or_eq(left_cell, NEG)}",     "format": fmt_neg})


# ------------------------------ Main ------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python src/_043_merge_MinMetr.py <MERGE_CFG>")
        sys.exit(1)

    cfg_path = resolve_cfg_path(sys.argv[1])
    cfg = read_yaml(cfg_path)

    merge_name = str(cfg.get("merge_name") or "").strip()
    if not merge_name:
        raise SystemExit("Config must define merge_name.")
    run_ids = parse_runs(cfg.get("runs"))
    if not run_ids:
        raise SystemExit("Config must define runs.")

    tool_dir = find_merge_alignment_dir(merge_name)
    align_maps = load_align_maps_by_chain(merge_name, tool_dir)
    chains = sorted(align_maps.keys(), key=str)

    logging.info(f"merge_name={merge_name}  runs={len(run_ids)}  chains={chains}")
    logging.info(f"Reading per-run chain inputs from AF3_output/<run>/csv/<run>_<chain>.csv (fallback XLSX).")

    # Build per-chain merged tables
    per_chain_tables: Dict[str, pd.DataFrame] = {}

    for chain in chains:
        parts: List[pd.DataFrame] = []
        for rid in run_ids:
            df_run_chain = read_run_chain_table(rid, chain)
            df_collapsed = collapse_to_run_means(df_run_chain, rid)
            df_mapped = map_run_to_merged(chain, rid, df_collapsed, align_maps[chain])
            # keep only run columns + keys (chain, msa_pos); cons_aa handled later
            keep = ["chain", "msa_pos"] + [c for c in df_mapped.columns if isinstance(c, str) and c.startswith(f"{rid}_")]
            parts.append(df_mapped[keep])

        # Outer-join all runs on merged MSA coordinate
        merged = None
        for p in parts:
            if merged is None:
                merged = p
            else:
                merged = merged.merge(p, on=["chain", "msa_pos"], how="outer")

        if merged is None:
            continue

        merged = merged.sort_values(["chain", "msa_pos"], kind="mergesort").reset_index(drop=True)

        # Build merged consensus AA from align_map across runs at each aln_pos
        amap = align_maps[chain].copy()
        amap = amap[amap["run_id"].isin(run_ids)].dropna(subset=["aln_pos"])
        aa_wide = amap.pivot(index="aln_pos", columns="run_id", values="aa_aln").reindex(columns=run_ids)
        cons = aa_wide.apply(lambda r: consensus_aa(list(r.values)), axis=1)
        cons_df = pd.DataFrame({"chain": chain, "msa_pos": cons.index.astype(int), "cons_aa": cons.values})

        merged = merged.merge(cons_df, on=["chain", "msa_pos"], how="left")

        # Put standard columns first
        merged = merged[["chain", "msa_pos", "cons_aa"] + [c for c in merged.columns if c not in ("chain", "msa_pos", "cons_aa")]]

        per_chain_tables[chain] = merged

    # Write Excel
    out_dir = MERGE_ROOT / merge_name
    ensure_dir(out_dir)
    out_xlsx = out_dir / "minScoresperMSA_merged.xlsx"
    ensure_writable(str(out_xlsx))

    # Column ordering similar to _025 (but per run_id)
    prefix = ["chain", "msa_pos", "cons_aa"]
    chainpos_aa, min_cols, minD_cols, maxC_cols = [], [], [], []
    for rid in run_ids:
        chainpos_aa.extend([f"{rid}_chain_pos", f"{rid}_aa"])
    for rid in run_ids:
        min_cols.append(f"{rid}_min-iPAE")
        minD_cols.append(f"{rid}_minD")
        maxC_cols.append(f"{rid}_maxContact")
    final_cols = prefix + chainpos_aa + min_cols + minD_cols + maxC_cols

    # Display names for run headers (optional)
    def display_name_for_run(rid: str) -> str:
        p = AF3_ROOT / rid / "model_trivia_map.csv"
        if not p.is_file():
            return rid
        try:
            d = pd.read_csv(p)
            if "trivia_name" not in d.columns:
                return rid
            names = [str(x).strip() for x in d["trivia_name"].tolist() if str(x).strip()]
            return Counter(names).most_common(1)[0][0] if names else rid
        except Exception:
            return rid

    display_by_run = {rid: display_name_for_run(rid) for rid in run_ids}

    rows_minipae = [f"{rid}_min-iPAE" for rid in run_ids]
    rows_minD    = [f"{rid}_minD" for rid in run_ids]
    rows_maxC    = [f"{rid}_maxContact" for rid in run_ids]

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        # Per-chain sheets with two-row header
        for chain_id, df in per_chain_tables.items():
            df_ordered = df[[c for c in final_cols if c in df.columns]].copy()

            cols = list(df_ordered.columns)
            top, bottom = [], []
            for c in cols:
                if c in ("chain", "msa_pos", "cons_aa"):
                    top.append("Name"); bottom.append(c)
                else:
                    m = re.match(r"^(\d{4})_", str(c))
                    rid = m.group(1) if m else None
                    top.append(display_by_run.get(rid, rid or ""))
                    bottom.append(str(c))

            df_mi = df_ordered.copy()
            df_mi.columns = pd.MultiIndex.from_arrays([top, bottom], names=["Name", "Column"])

            sheet_name = re.sub(r"[^A-Za-z0-9 _-]", "_", f"{chain_id}")[:31] or "Sheet"
            df_mi.to_excel(writer, sheet_name=sheet_name, index=True, na_rep="")
            ws = writer.sheets[sheet_name]
            ws.set_column(0, 0, None, None, {"hidden": True})

        # Rebuild transposed sheets (Combined_T and CombinedT_*)
        all_metric_labels = [f"{rid}|min-iPAE" for rid in run_ids] + \
                            [f"{rid}|minD" for rid in run_ids] + \
                            [f"{rid}|maxContact" for rid in run_ids]
        tdf_all = build_transposed(per_chain_tables, run_ids, metric_rows=all_metric_labels)

        color_rows_all = {
            "min-iPAE":   {"rows": rows_minipae, "vmin": 0.0, "vmid": 0.25, "vmax": 1.0,  "invert": False},
            "minD":       {"rows": rows_minD,    "vmin": 1.0, "vmid": 15.0, "vmax": 60.0, "invert": False},
            "maxContact": {"rows": rows_maxC,    "vmin": 0.0, "vmid": 0.75, "vmax": 1.0,  "invert": True},
        }
        write_transposed_sheet(writer, tdf_all, "Combined_T", color_rows_all)

        tdf_minpae = build_transposed(per_chain_tables, run_ids, metric_rows=[f"{rid}|min-iPAE" for rid in run_ids])
        write_transposed_sheet(
            writer, tdf_minpae, "CombinedT_minPAE",
            {"min-iPAE": {"rows": rows_minipae, "vmin": 0.0, "vmid": 0.25, "vmax": 1.0, "invert": False}}
        )

        tdf_minD = build_transposed(per_chain_tables, run_ids, metric_rows=[f"{rid}|minD" for rid in run_ids])
        write_transposed_sheet(
            writer, tdf_minD, "CombinedT_minD",
            {"minD": {"rows": rows_minD, "vmin": 1.0, "vmid": 15.0, "vmax": 60.0, "invert": False}}
        )

        tdf_maxC = build_transposed(per_chain_tables, run_ids, metric_rows=[f"{rid}|maxContact" for rid in run_ids])
        write_transposed_sheet(
            writer, tdf_maxC, "CombinedT_maxContact",
            {"maxContact": {"rows": rows_maxC, "vmin": 0.0, "vmid": 0.75, "vmax": 1.0, "invert": True}}
        )

    logging.info(f"Wrote: {out_xlsx}")


if __name__ == "__main__":
    main()