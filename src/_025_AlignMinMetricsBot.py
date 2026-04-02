#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_025_AlignMinMetricsBot.py

Join Align maps + per-residue min-iPAE, minD, maxContact into one wide CSV per SimID,
write one sheet per chain, and add multiple transposed sheets:
  - Combined_T (all metrics)
  - CombinedT_minPAE
  - CombinedT_minD
  - CombinedT_maxContact

This drop-in only changes HOW the per-chain Excel sheets (A, B, …) are written:
- They now use a TWO-ROW HEADER:
    * Top row  = display name from AF3_output/<sim_id>/model_trivia_map.csv
                 (e.g., 'AtMLO4'); for the first 3 columns the label is 'Name'.
    * Bottom   = the original column names (e.g., '0026-01_chain_pos', '0026-01_aa', '0026-01_minD', …)
- CSV outputs are unchanged.
- Transposed sheets (Combined_T and CombinedT_*) are UNCHANGED from the original file,
  including conditional-format coloring.

Notes
-----
- The optional mapping file is: AF3_output/<sim_id>/model_trivia_map.csv
  with columns: job_folder, model_index, trivia_name (written by your step _022_).
- If the mapping file is missing or has no names, we fall back to the jobkey (e.g., '0026-01').
"""

import os
import re
import sys
import glob
import math
import yaml
import logging
import pandas as pd
import numpy as np
from collections import Counter
from typing import Dict, List, Optional
from xlsxwriter.utility import xl_rowcol_to_cell

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------- Config helpers --------------------------

def read_yaml(path: str) -> dict:
    """Load a YAML file into a dict (empty dict if file is empty)."""
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def derive_sim_id_from_cfg(cfg: dict) -> Optional[str]:
    """
    Extract the 4-digit SimID from either:
      - cfg['sheet'] (prefix "####-..." or "####_...")
      - cfg['output_json'] filename
      - cfg['sim_id'] if explicitly set
    """
    sheet = str(cfg.get("sheet", "")).strip()
    m = re.match(r"^(\d{4})[\-_]", sheet)
    if m:
        return m.group(1)
    outj = os.path.basename(str(cfg.get("output_json", "")).strip())
    m = re.match(r"^(\d{4})[\-_]", outj)
    if m:
        return m.group(1)
    if "sim_id" in cfg and str(cfg["sim_id"]).strip():
        return str(cfg["sim_id"]).strip()
    return None

# ---------------------------- FS helpers ------------------------------

def ensure_dir(p: str) -> None:
    """Create a directory if it doesn't already exist."""
    os.makedirs(p, exist_ok=True)

def select_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """
    Return the first present column among 'candidates', case-insensitive.
    Useful when upstream scripts slightly rename columns.
    """
    for c in candidates:
        if c in df.columns:
            return c
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None

def find_align_map_files(alignments_root: str, sim_id: str, alignment_algo: str) -> List[str]:
    """
    Locate alignment map CSVs under input/alignments/<sim_id>/<alignment_algo>/.
    Various filename patterns are tried for robustness.
    """
    base = os.path.join(alignments_root, sim_id, alignment_algo)
    pats = [
        os.path.join(base, f"{sim_id}_*_align_map.csv"),
        os.path.join(base, f"{sim_id}_*_alignment_map.csv"),
        os.path.join(base, f"{sim_id}_*_align_map*.csv"),
    ]
    files = []
    for p in pats:
        files.extend(glob.glob(p))
    files = sorted(set(files))
    if not files:
        logging.error(f"No align_map CSVs found under: {base}")
    else:
        logging.info(f"Found {len(files)} align_map CSV(s) under {base}")
    return files

def parse_chain_from_filename(sim_id: str, path: str) -> Optional[str]:
    """Extract the chain ID from filenames like '0010_A_align_map.csv'."""
    fname = os.path.basename(path)
    m = re.search(rf"^{re.escape(sim_id)}_([A-Za-z0-9]+)_align", fname)
    return m.group(1) if m else None

def derive_job_key(sim_id: str, job_dirname_or_label: str) -> str:
    """
    Canonicalize job identifiers into the form '####-NN' (e.g., '0010-02'),
    even if the directory names differ (e.g., '0010_02_something').
    """
    s = str(job_dirname_or_label)
    base = os.path.basename(s)
    m = re.search(rf"(?<!\d){re.escape(sim_id)}[-_](\d{{2}})", base)
    if m:
        return f"{sim_id}-{m.group(1)}"
    m2 = re.match(r"^(\d{4})[-_](\d{2})", base)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return base.replace("_", "-")

# --------------------------- Domain logic -----------------------------

def consensus_aa(aa_list) -> str:
    """
    Simple majority consensus AA, ignoring gaps/missings.
    Ties are broken alphabetically among top-scoring residues.
    """
    filtered = [a for a in aa_list if a not in ("-", "NA", "", None)]
    if not filtered:
        return "-"
    counts = Counter(filtered).most_common()
    if len(counts) == 1 or (len(counts) > 1 and counts[0][1] > counts[1][1]):
        return counts[0][0]
    top = counts[0][1]
    tied = sorted([aa for aa, n in counts if n == top])
    return tied[0] if tied else "-"

# ---- Metric loaders (EXACT columns as in _024_) ----------------------

def _load_metric_exact(xlsx_path: str, desired_col: str, out_colname: str) -> Optional[pd.DataFrame]:
    """
    Load [chain, chain_pos, <metric>] from a workbook where the metric summary
    column is exactly `desired_col` (case-sensitive).
    The returned DataFrame has columns: chain (object), chain_pos (Int64), <out_colname>.
    """
    if not os.path.exists(xlsx_path):
        logging.warning(f"Missing metric workbook: {xlsx_path}")
        return None
    try:
        sheets = pd.read_excel(xlsx_path, sheet_name=None)
    except Exception as e:
        logging.warning(f"Failed reading {xlsx_path}: {e}")
        return None

    for _, df in sheets.items():
        cols_lower = {c.lower(): c for c in df.columns}
        chain_col = cols_lower.get("chain")
        chainpos_col = cols_lower.get("chain_pos")
        if not chain_col or not chainpos_col:
            continue
        if desired_col not in df.columns:
            # Allow case-insensitive match if case drifted accidentally
            if desired_col.lower() in cols_lower:
                desired = cols_lower[desired_col.lower()]
            else:
                continue
        else:
            desired = desired_col

        out = df[[chain_col, chainpos_col, desired]].copy()
        out.columns = ["chain", "chain_pos", out_colname]
        # Keep nullable integer so missing positions remain missing
        out["chain_pos"] = pd.to_numeric(out["chain_pos"], errors="coerce").astype("Int64")
        return out

    logging.warning(f"No suitable '{out_colname}' columns in {xlsx_path}")
    return None

def load_minpae_for_job(xlsx_path: str) -> Optional[pd.DataFrame]:
    """min-iPAE summary is 'mean_both_dir_min' (as produced by _024_)."""
    return _load_metric_exact(xlsx_path, desired_col="mean_both_dir_min", out_colname="min_iPAE")

def load_minD_for_job(xlsx_path: str) -> Optional[pd.DataFrame]:
    """minD summary is also 'mean_both_dir_min'."""
    return _load_metric_exact(xlsx_path, desired_col="mean_both_dir_min", out_colname="minD")

def load_maxContact_for_job(xlsx_path: str) -> Optional[pd.DataFrame]:
    """maxContact summary is 'mean_both_dir_max'."""
    return _load_metric_exact(xlsx_path, desired_col="mean_both_dir_max", out_colname="maxContact")

def map_metric_for_chain(chain_id: str, chain_pos_series: pd.Series,
                         metric_table: Optional[pd.DataFrame],
                         na_token) -> pd.Series:
    """
    Map a per-residue metric (e.g., min-iPAE) to aligned chain positions.
    Returns a Series aligned to chain_pos_series with numeric values or NaN.
    """
    if metric_table is None or metric_table.empty:
        # If we have no table, return all-missing
        return pd.Series([np.nan] * len(chain_pos_series), index=chain_pos_series.index, dtype=object)

    # Restrict to this chain and build a fast lookup {pos: value}
    mt = metric_table[metric_table["chain"] == chain_id].dropna(subset=["chain_pos"])
    metric_name = [c for c in mt.columns if c not in ("chain", "chain_pos")][0] if len(mt.columns) > 2 else mt.columns[-1]
    lut = {int(r.chain_pos): getattr(r, metric_name) for r in mt.itertuples(index=False)}

    def lookup(v):
        # Respect real missings and gaps
        if pd.isna(v) or v in ("-", ""):
            return np.nan
        try:
            iv = int(v)
        except Exception:
            return np.nan
        return lut.get(iv, np.nan)

    return chain_pos_series.apply(lookup).astype(object)

# --------- NEW: optional display names for jobs (AF3_output/<sim_id>/model_trivia_map.csv)

def load_display_names(sim_id: str, af3_output_root: str) -> Dict[str, str]:
    """
    Return {jobkey('####-##'): display_name} from model_trivia_map.csv if available.
    We pick the first non-empty trivia_name per jobkey (smallest model_index).
    Falls back to {} and the caller will use jobkeys as labels.
    """
    path = os.path.join(af3_output_root, sim_id, "model_trivia_map.csv")
    if not os.path.isfile(path):
        logging.info("No model_trivia_map.csv found; per-chain headers will use jobkeys.")
        return {}
    try:
        df = pd.read_csv(path)
    except Exception as e:
        logging.warning(f"Failed to read {path}: {e}")
        return {}

    need = {"job_folder", "model_index", "trivia_name"}
    if not need.issubset(df.columns):
        logging.warning(f"{path} missing required columns {need - set(df.columns)}")
        return {}

    df["jobkey"] = df["job_folder"].astype(str).apply(
        lambda s: derive_job_key(sim_id, os.path.basename(s))
    )
    df["model_index"] = pd.to_numeric(df["model_index"], errors="coerce")
    df = df.sort_values(["jobkey", "model_index"], kind="stable")

    out: Dict[str, str] = {}
    for jk, sub in df.groupby("jobkey", sort=False):
        name = next((str(t).strip() for t in sub["trivia_name"] if str(t).strip()), "")
        if name:
            out[jk] = name
    return out

# ------------------------------ Main ----------------------------------

def main():
    # --- CLI & config parsing ---
    if len(sys.argv) != 2 or not sys.argv[1].endswith((".yml", ".yaml")):
        print("Usage: python src/_025_AlignMinMetricsBot.py config/<run.yml>")
        sys.exit(1)

    cfg = read_yaml(sys.argv[1])
    sim_id = derive_sim_id_from_cfg(cfg)
    if not sim_id:
        logging.error("Could not determine sim_id. Ensure 'sheet' or 'output_json' begins with 4 digits.")
        sys.exit(2)

    alignment_algo = str(cfg.get("alignment_algo", "")).strip()
    if not alignment_algo or alignment_algo == "none":
        logging.error("Config must set a usable 'alignment_algo' (auto/mafft/clustalo/muscle).")
        sys.exit(2)

    # --- Fixed locations & filenames ---
    alignments_root = "input/alignments"
    af3_output_root = "AF3_output"
    minpae_filename = "per_residue_minPAE.xlsx"
    minD_filename   = "per_residue_minD.xlsx"
    maxC_filename   = "per_residue_maxContact.xlsx"

    # Use REAL missings everywhere; never the string "NA"
    na_token = np.nan

    logging.info(f"sim_id={sim_id}  alignment_algo={alignment_algo}")

    # ---- Align maps ----
    align_files = find_align_map_files(alignments_root, sim_id, alignment_algo)
    if not align_files:
        sys.exit(3)

    # Map chain -> file
    files_by_chain: Dict[str, str] = {}
    for f in align_files:
        ch = parse_chain_from_filename(sim_id, f)
        if ch:
            files_by_chain[ch] = f
    if not files_by_chain:
        logging.error("No align_map files with chain letters detected.")
        sys.exit(4)

    # ---- per-job metric tables ----
    jobs_root = os.path.join(af3_output_root, sim_id)
    if not os.path.isdir(jobs_root):
        logging.error(f"Jobs folder not found: {jobs_root}")
        sys.exit(5)

    # Only keep real job folders (we'll normalize names to '####-NN')
    job_dirs = [d for d in sorted(os.listdir(jobs_root))
                if os.path.isdir(os.path.join(jobs_root, d))]

    minpae_by_jobkey: Dict[str, Optional[pd.DataFrame]] = {}
    minD_by_jobkey:   Dict[str, Optional[pd.DataFrame]] = {}
    maxC_by_jobkey:   Dict[str, Optional[pd.DataFrame]] = {}

    jobkey_pat = re.compile(rf"^{re.escape(sim_id)}-\d{{2}}$")

    for jd in job_dirs:
        jk = derive_job_key(sim_id, jd)  # e.g. "0010_01_*" -> "0010-01"
        if not jobkey_pat.match(jk):
            logging.info(f"Skipping non-job folder: {jd} (normalized as {jk})")
            continue

        base = os.path.join(jobs_root, jd)
        minpae_by_jobkey[jk] = load_minpae_for_job(os.path.join(base, minpae_filename))
        minD_by_jobkey[jk]   = load_minD_for_job  (os.path.join(base, minD_filename))
        maxC_by_jobkey[jk]   = load_maxContact_for_job(os.path.join(base, maxC_filename))

    # Order keys like 0010-01, 0010-02, ...
    def job_sort_key(k: str):
        m = re.match(rf"^{re.escape(sim_id)}-(\d+)$", k)
        return int(m.group(1)) if m else 9999

    jobkeys = sorted(minpae_by_jobkey.keys(), key=job_sort_key)

    # ---- Build per-chain tables ----
    per_chain_tables: Dict[str, pd.DataFrame] = {}

    for chain_id, map_path in files_by_chain.items():
        logging.info(f"Processing chain {chain_id}: {map_path}")
        dfm = pd.read_csv(map_path)

        # Column names can vary a bit; resolve them robustly
        chain_col = select_col(dfm, ["chain", "chain_id"]) or "chain"
        aln_col   = select_col(dfm, ["aln_pos", "msa_pos", "align_pos", "aln_col"]) or "aln_pos"
        job_col   = select_col(dfm, ["job", "job_id", "job_dir"]) or "job"
        aa_col    = select_col(dfm, ["aa_aln", "aa"]) or "aa_aln"
        pos_col   = select_col(dfm, ["res_idx", "chain_pos", "res_pos", "native_pos"]) or "res_idx"

        missing = [c for c in [chain_col, aln_col, job_col, aa_col, pos_col] if c not in dfm.columns]
        if missing:
            logging.error(f"Align map missing columns {missing} in {map_path}")
            sys.exit(6)

        # Restrict to this chain and normalize job keys
        dfm = dfm[dfm[chain_col].astype(str) == str(chain_id)].copy()
        dfm["job_key"] = dfm[job_col].astype(str).apply(lambda x: derive_job_key(sim_id, os.path.basename(x)))

        # Wide matrices (index = MSA column index; columns = job_key)
        pos_wide = dfm.pivot(index=aln_col, columns="job_key", values=pos_col).sort_index()
        aa_wide  = dfm.pivot(index=aln_col, columns="job_key", values=aa_col).reindex(pos_wide.index)

        # Column order = sorted jobkeys
        pos_wide = pos_wide.reindex(columns=jobkeys)
        aa_wide  = aa_wide.reindex(columns=jobkeys)

        # Per-column consensus AA
        cons = aa_wide.apply(lambda r: consensus_aa(list(r.values)), axis=1)

        # Base output table for this chain
        out = pd.DataFrame({
            "chain":   chain_id,
            "msa_pos": pos_wide.index.astype(int),
            "cons_aa": cons,
        })

        # Keep chain positions as nullable integers; AA gaps become '-'
        for jk in jobkeys:
            out[f"{jk}_chain_pos"] = pos_wide[jk].astype("Int64")
            out[f"{jk}_aa"]        = aa_wide[jk].fillna("-")

        # ---- Attach metrics in BULK to avoid fragmentation ----
        minipae_cols, mind_cols, maxc_cols = {}, {}, {}
        for jk in jobkeys:
            minipae_cols[f"{jk}_min-iPAE"] = map_metric_for_chain(chain_id, out[f"{jk}_chain_pos"], minpae_by_jobkey.get(jk), na_token)
            mind_cols[f"{jk}_minD"]        = map_metric_for_chain(chain_id, out[f"{jk}_chain_pos"], minD_by_jobkey.get(jk),   na_token)
            maxc_cols[f"{jk}_maxContact"]  = map_metric_for_chain(chain_id, out[f"{jk}_chain_pos"], maxC_by_jobkey.get(jk),   na_token)

        out = pd.concat([out, pd.DataFrame(minipae_cols), pd.DataFrame(mind_cols), pd.DataFrame(maxc_cols)], axis=1)
        per_chain_tables[chain_id] = out

    # ---- Write outputs ----
    out_dir = os.path.join(af3_output_root, sim_id)
    ensure_dir(out_dir)
    csv_dir = os.path.join(out_dir, "csv")
    ensure_dir(csv_dir)

    # Column ordering for outputs
    prefix = ["chain", "msa_pos", "cons_aa"]
    chainpos_aa, min_cols, minD_cols, maxC_cols = [], [], [], []
    for jk in jobkeys:
        chainpos_aa.extend([f"{jk}_chain_pos", f"{jk}_aa"])
    for jk in jobkeys:
        min_cols.append(f"{jk}_min-iPAE")
        minD_cols.append(f"{jk}_minD")
        maxC_cols.append(f"{jk}_maxContact")
    final_cols = prefix + chainpos_aa + min_cols + minD_cols + maxC_cols

    # 1) Per-chain CSVs (write blanks, not 'NA')
    for chain_id, df in per_chain_tables.items():
        df_ordered = df[[c for c in final_cols if c in df.columns]].copy()
        chain_csv = os.path.join(csv_dir, f"{sim_id}_{chain_id}.csv")
        df_ordered.to_csv(chain_csv, index=False, na_rep="")  # leave empties blank
        logging.info(f"Wrote per-chain CSV: {chain_csv} (rows={len(df_ordered)})")

    # 2) Combined CSV (write blanks, not 'NA')
    combined = pd.concat(
        [df[[c for c in final_cols if c in df.columns]] for df in per_chain_tables.values()],
        ignore_index=True
    )
    out_csv = os.path.join(csv_dir, "minScoresperMSA.csv")
    combined.to_csv(out_csv, index=False, na_rep="")  # leave empties blank
    logging.info(f"Wrote combined CSV: {out_csv} (rows={len(combined)}, cols={len(combined.columns)})")

    # ---------------- Excel writer + Transposed sheets -----------------

    def build_transposed(per_chain_tables: Dict[str, pd.DataFrame],
                         jobkeys: List[str],
                         metric_rows: List[str]) -> pd.DataFrame:
        """
        Build a transposed table (rows = descriptors/metrics; columns = Chain:msa_pos).
        metric_rows are labels like '0010-01|min-iPAE' which become row labels '0010-01_min-iPAE'.
        """
        chain_order = sorted(per_chain_tables.keys(), key=lambda x: str(x))
        col_labels, chains_flat, msapos_flat, consaa_flat = [], [], [], []

        rows_dict = {lab: [] for lab in metric_rows}
        pos_rows  = {f"Chain_pos_{jk}": [] for jk in jobkeys}
        aa_rows   = {f"Chain_aa_{jk}":  [] for jk in jobkeys}

        for ch in chain_order:
            dfc = per_chain_tables[ch].sort_values("msa_pos")
            for _, r in dfc.iterrows():
                col_labels.append(f"{ch}:{int(r['msa_pos'])}")
                chains_flat.append(ch)
                msapos_flat.append(int(r["msa_pos"]))
                consaa_flat.append(r["cons_aa"])
                # metric rows
                for lab in metric_rows:
                    jk, mname = lab.split("|", 1)  # lab like "0010-01|min-iPAE"
                    col = f"{jk}_{mname}"
                    rows_dict[lab].append(r[col] if col in dfc.columns else np.nan)
                # pos/aa
                for jk in jobkeys:
                    pos_rows[f"Chain_pos_{jk}"].append(r.get(f"{jk}_chain_pos", np.nan))
                    aa_rows[f"Chain_aa_{jk}"].append(r.get(f"{jk}_aa", "-"))

        # Assemble rows
        rows, labels = [], []
        def add_row(label, vals): labels.append(label); rows.append(vals)
        add_row("Chain",   chains_flat)
        add_row("msa_pos", msapos_flat)
        add_row("cons_aa", consaa_flat)
        for lab in metric_rows:
            jk, mname = lab.split("|", 1)
            add_row(f"{jk}_{mname}", rows_dict[lab])
        for jk in jobkeys:
            add_row(f"Chain_pos_{jk}", pos_rows[f"Chain_pos_{jk}"])
            add_row(f"Chain_aa_{jk}",  aa_rows[f"Chain_aa_{jk}"])

        return pd.DataFrame(rows, index=labels, columns=col_labels)

    def write_transposed_sheet(writer, tdf: pd.DataFrame, sheet_name: str,
                               color_rows: Dict[str, dict]):
        """
        Write tdf to sheet with formatting and color scales per metric type.

        IMPORTANT: We coerce numeric rows BEFORE writing to Excel so that cells
        are real numbers (not strings), enabling proper conditional formatting.
        """
        # Work on a copy to avoid mutating the caller's DataFrame
        tdf = tdf.copy()

        # Normalize all pd.NA to np.nan so Excel sees blanks
        tdf = tdf.replace({pd.NA: np.nan})

        # Helper: coerce strings like "" or " " to NaN; numbers stay numeric
        def _coerce_float_or_nan(x):
            if pd.isna(x) or (isinstance(x, str) and x.strip() == ""):
                return np.nan
            try:
                return float(x)
            except Exception:
                return x

        # Coerce numeric-meaningful rows (positions + metrics)
        for idx in tdf.index:
            if (idx == "msa_pos") or idx.startswith("Chain_pos_") or \
               idx.endswith("_min-iPAE") or idx.endswith("_minD") or idx.endswith("_maxContact"):
                tdf.loc[idx] = tdf.loc[idx].map(_coerce_float_or_nan)

        # Now write with blanks for NaNs
        tname = re.sub(r"[^A-Za-z0-9 _-]", "_", sheet_name)[:31] or "Sheet"
        tdf.to_excel(writer, sheet_name=tname, index=True, na_rep="")  # blanks, not "NA"
        ws = writer.sheets[tname]
        wb = writer.book

        # Formats
        fmt_idx  = wb.add_format({"bold": True})
        fmt_head = wb.add_format({"bold": True})
        fmt_dec2 = wb.add_format({"num_format": "0.00"})
        fmt_int  = wb.add_format({"num_format": "0"})

        # Column widths & panes
        ws.freeze_panes(1, 1)
        ws.set_row(0, None, fmt_head)
        ws.set_column(0, 0, 18, fmt_idx)
        ncols = len(tdf.columns)
        for j in range(1, ncols + 1):
            ws.set_column(j, j, 10)

        # Row-level number formats (visual only; values are already numeric)
        for r, label in enumerate(tdf.index, start=1):
            if label in ("msa_pos",) or label.startswith("Chain_pos_"):
                ws.set_row(r, None, fmt_int)
            elif label.endswith("_min-iPAE") or label.endswith("_maxContact") or label.endswith("_minD"):
                ws.set_row(r, None, fmt_dec2)

        # Color scales
        MIN_COLOR = "#B65256"  # red
        MID_COLOR = "#FABE50"  # amber
        MAX_COLOR = "#2D7F83"  # teal

        def apply_colorscale(row_labels: List[str],
                             vmin: float, vmid: float, vmax: float,
                             invert: bool = False):
            """
            Excel 3-color scale requires vmin ≤ vmid ≤ vmax.
            To invert the 'direction', keep numeric bounds normal and swap colors.
            """
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

        # Apply per-metric color specs (support 'invert' flag)
        for _, spec in color_rows.items():
            apply_colorscale(
                row_labels=spec["rows"],
                vmin=spec["vmin"],
                vmid=spec["vmid"],
                vmax=spec["vmax"],
                invert=spec.get("invert", False),
            )

        # AA category shading
        fmt_unpolar = wb.add_format({"bg_color": "#8DC060"})
        fmt_polar   = wb.add_format({"bg_color": "#FABE50"})
        fmt_pos     = wb.add_format({"bg_color": "#2D7F83"})
        fmt_neg     = wb.add_format({"bg_color": "#B65256"})

        UNPOLAR = ["A","V","L","I","M","F","W","P","G"]
        POLAR   = ["S","T","N","Q","Y","C"]
        POS     = ["K","R","H"]
        NEG     = ["D","E"]

        # Ensure AA rows uppercase for consistent conditional formulas
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

    # Build metric row labels once (UNCHANGED)
    rows_minipae = [f"{jk}_min-iPAE"   for jk in jobkeys]
    rows_minD    = [f"{jk}_minD"       for jk in jobkeys]
    rows_maxC    = [f"{jk}_maxContact" for jk in jobkeys]

    # ---- Excel workbook (one per SimID) ----
    with pd.ExcelWriter(os.path.join(out_dir, "minScoresperMSA.xlsx"), engine="xlsxwriter") as writer:
        # ======== PER-CHAIN SHEETS (A, B, ...) — ONLY PART CHANGED ========
        # Optional map {jobkey -> display name}
        display_by_jobkey = load_display_names(sim_id, af3_output_root)

        for chain_id, df in per_chain_tables.items():
            df_ordered = df[[c for c in final_cols if c in df.columns]].copy()

            # Build MultiIndex columns:
            #   top row  = 'Name' for first 3 cols, otherwise display name or jobkey
            #   bottom   = original column name
            cols = list(df_ordered.columns)
            top, bottom = [], []
            for c in cols:
                if c in ("chain", "msa_pos", "cons_aa"):
                    top.append("Name"); bottom.append(c)
                else:
                    m = re.match(r"^(\d{4}-\d{2})_", c)
                    jk = m.group(1) if m else None
                    disp = display_by_jobkey.get(jk, jk or "")
                    top.append(disp)
                    bottom.append(c)

            df_mi = df_ordered.copy()
            df_mi.columns = pd.MultiIndex.from_arrays([top, bottom], names=["Name", "Column"])

            sheet_name = re.sub(r"[^A-Za-z0-9 _-]", "_", f"{chain_id}")[:31] or "Sheet"

            # IMPORTANT: MultiIndex requires index=True; then hide the index col for same look
            df_mi.to_excel(writer, sheet_name=sheet_name, index=True, na_rep="")
            ws = writer.sheets[sheet_name]
            ws.set_column(0, 0, None, None, {"hidden": True})

        # ======== TRANSPOSED SHEETS — UNCHANGED ========
        all_metric_labels = [f"{jk}|min-iPAE" for jk in jobkeys] + \
                            [f"{jk}|minD"     for jk in jobkeys] + \
                            [f"{jk}|maxContact" for jk in jobkeys]
        tdf_all = build_transposed(per_chain_tables, jobkeys, metric_rows=all_metric_labels)
        color_rows_all = {
            "min-iPAE":   {"rows": rows_minipae, "vmin": 0.0, "vmid": 0.25, "vmax": 1.0,  "invert": False},
            "minD":       {"rows": rows_minD,    "vmin": 1.0, "vmid": 15.0, "vmax": 60.0, "invert": False},
            # Invert colors for maxContact so high probability = red (analogous to 'min' metrics)
            "maxContact": {"rows": rows_maxC,    "vmin": 0.0, "vmid": 0.75, "vmax": 1.0,  "invert": True},
        }
        write_transposed_sheet(writer, tdf_all, "Combined_T", color_rows_all)

        # === CombinedT_minPAE ===
        tdf_minpae = build_transposed(per_chain_tables, jobkeys, metric_rows=[f"{jk}|min-iPAE" for jk in jobkeys])
        write_transposed_sheet(
            writer, tdf_minpae, "CombinedT_minPAE",
            {"min-iPAE": {"rows": rows_minipae, "vmin": 0.0, "vmid": 0.25, "vmax": 1.0, "invert": False}}
        )

        # === CombinedT_minD ===
        tdf_minD = build_transposed(per_chain_tables, jobkeys, metric_rows=[f"{jk}|minD" for jk in jobkeys])
        write_transposed_sheet(
            writer, tdf_minD, "CombinedT_minD",
            {"minD": {"rows": rows_minD, "vmin": 1.0, "vmid": 15.0, "vmax": 60.0, "invert": False}}
        )

        # === CombinedT_maxContact ===
        tdf_maxC = build_transposed(per_chain_tables, jobkeys, metric_rows=[f"{jk}|maxContact" for jk in jobkeys])
        write_transposed_sheet(
            writer, tdf_maxC, "CombinedT_maxContact",
            {"maxContact": {"rows": rows_maxC, "vmin": 1.0*0, "vmid": 0.75, "vmax": 1.0, "invert": True}}
        )

    logging.info(f"Wrote Excel: {os.path.join(out_dir, 'minScoresperMSA.xlsx')} (per-chain sheets now have two-row headers; transposed sheets unchanged)")
    logging.info(f"All CSVs stored under: {csv_dir}")

if __name__ == "__main__":
    main()
