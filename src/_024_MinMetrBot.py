#!/usr/bin/env python3
"""
_024_MinMetrBot.py  —  CSV-first inter-chain mins for PAE & GeomDist, MAX for ContactProbs
----------------------------------------------------------------------------------------
Reads matrices from per-model / average **CSVs** in `per_residue_metrics/` (written by
_023_ResMetrBot.py) instead of from a single Excel workbook, and writes the
same three min/max workbooks as before:

1) per_residue_minPAE.xlsx
   - Reads PAE per-model (PAE_model_*.csv) or Avg_PAE.csv
   - Inter-chain min vectors (0–1). If PAE looks like Å, normalize by 30.
   - Falls back to *_full_data_*.json only if no CSVs are present.

2) per_residue_minD.xlsx
   - Reads GeomDist per-model (GeomDist_model_*.csv) or Avg_GeomDist.csv (Å)
   - Inter-chain min vectors in Å.

3) per_residue_maxContact.xlsx   (MAX instead of min)
   - Reads ContactProbs per-model (ContactProbs_model_*.csv) or Avg_ContactProbs.csv (0–1)
   - Inter-chain **max** vectors (0–1).

Inter-chain rule: only pairs (i, j) with chain_j != chain_i contribute; same-chain/self masked out.
"""

from __future__ import annotations

import os
import re
import sys
import glob
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from contextlib import suppress

from perm_helper import ensure_writable

ANNOT_COLS = {"global_idx", "chain", "chain_id", "chain_pos", "aa", "pdb_resnum", "token_chain_id"}
RESMET_DIR = "per_residue_metrics"
HEADER_LEVELS = 5  # we write MultiIndex headers with 5 levels: global_idx, chain, chain_pos, aa, pdb_resnum
INDEX_LEVELS  = 5  # number of left-most columns that hold the row MultiIndex in CSVs

# ----------------------------- utils -----------------------------

def is_job_dir(path: str) -> bool:
    with suppress(Exception):
        return any(fn.endswith(".json") and "_full_data_" in fn for fn in os.listdir(path))
    return False

def find_job_jsons(job_dir: str) -> List[str]:
    return sorted([f for f in os.listdir(job_dir) if f.endswith(".json") and "_full_data_" in f])

# ----------------------------- reading residue map -----------------------------

def load_residue_map(job_dir: str, n_res: int) -> pd.DataFrame:
    """Prefer the CSV written by _023_ (per_residue_metrics/residue_map.csv).
    If missing, return a minimal placeholder using length n_res.
    """
    csv_path = os.path.join(job_dir, RESMET_DIR, "residue_map.csv")
    if os.path.isfile(csv_path):
        rm = pd.read_csv(csv_path)
        if "chain" not in rm.columns and "chain_id" in rm.columns:
            rm = rm.rename(columns={"chain_id": "chain"})
        needed = {"global_idx", "chain", "chain_pos", "aa", "pdb_resnum"}
        if needed.issubset(set(rm.columns)) and len(rm) == n_res:
            return rm[["global_idx", "chain", "chain_pos", "aa", "pdb_resnum"]].copy()
    # fallback placeholder
    return pd.DataFrame({
        "global_idx": np.arange(1, n_res + 1),
        "chain": ["?"] * n_res,
        "chain_pos": np.arange(1, n_res + 1),
        "aa": ["X"] * n_res,
        "pdb_resnum": [str(i) for i in range(1, n_res + 1)],
    })

# ----------------------------- read matrices from CSVs -----------------------------

def _coerce_numeric_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(pd.to_numeric, errors="coerce")

def _largest_square_numeric_block(df: pd.DataFrame, label_for_err: str) -> np.ndarray:
    num = _coerce_numeric_df(df).dropna(axis=0, how="all").dropna(axis=1, how="all")
    n_rows, n_cols = num.shape
    N = min(n_rows, n_cols)
    if N == 0:
        raise ValueError(f"No numeric data found for {label_for_err}.")
    return num.iloc[:N, :N].to_numpy(dtype=float)


def _read_square_from_csv(path: str, label: str) -> np.ndarray:
    """
    Read a matrix CSV written by _023_ with 5 header rows and 5 index columns.
    Only read the numeric matrix columns to avoid DtypeWarning from the left
    MultiIndex columns (mixed string/int).
    """
    if not os.path.isfile(path):
        return None
    # Column names are integers when header=None; keep cols >= INDEX_LEVELS only.
    try:
        df = pd.read_csv(
            path,
            header=None,
            skiprows=HEADER_LEVELS,
            usecols=lambda c: isinstance(c, int) and c >= INDEX_LEVELS,
            dtype=np.float64,
            low_memory=False,
        )
        return _largest_square_numeric_block(df, label)
    except Exception:
        # Fallback: read all, then slice the left index columns off
        df = pd.read_csv(path, header=None, skiprows=HEADER_LEVELS, low_memory=False)
        if df.shape[1] <= INDEX_LEVELS:
            raise ValueError(f"{label}: Not enough columns after header/index removal in {path}")
        sub = df.iloc[:, INDEX_LEVELS:]
        return _largest_square_numeric_block(sub, label)

def _read_per_model_from_csv(job_dir: str, prefix: str) -> Dict[int, np.ndarray] | None:
    """Read per-model matrices matching `<prefix>_model_*.csv` under per_residue_metrics.
    Returns {model_index: ndarray} or None if nothing found.
    """
    pat = os.path.join(job_dir, RESMET_DIR, f"{prefix}_model_*.csv")
    files = sorted(glob.glob(pat))
    if not files:
        return None
    out: Dict[int, np.ndarray] = {}
    for fp in files:
        name = os.path.basename(fp)
        m = re.search(r"_model_(\d+)\.csv$", name)
        if not m:
            continue
        midx = int(m.group(1))
        arr = _read_square_from_csv(fp, f"{prefix} model {midx}")
        out[midx] = arr
    return out or None


def _read_avg_from_csv(job_dir: str, fname: str) -> np.ndarray | None:
    fp = os.path.join(job_dir, RESMET_DIR, fname)
    if not os.path.isfile(fp):
        return None
    return _read_square_from_csv(fp, fname)

# CSV readers for the three modalities
# PAE
def read_PAE_per_model(job_dir: str): return _read_per_model_from_csv(job_dir, "PAE")
def read_AvgPAE(job_dir: str):        return _read_avg_from_csv(job_dir, "Avg_PAE.csv")
# Geom (Å)
def read_Geom_per_model(job_dir: str): return _read_per_model_from_csv(job_dir, "GeomDist")
def read_AvgGeom(job_dir: str):        return _read_avg_from_csv(job_dir, "Avg_GeomDist.csv")
# Contact (0–1)
def read_Contact_per_model(job_dir: str): return _read_per_model_from_csv(job_dir, "ContactProbs")
def read_AvgContact(job_dir: str):        return _read_avg_from_csv(job_dir, "Avg_ContactProbs.csv")

# ----------------------------- inter-chain helpers -----------------------------

def _looks_like_angstroms(arr: np.ndarray, sample: int = 500, thresh: float = 1.0, frac: float = 0.7) -> bool:
    v = arr[np.isfinite(arr)]
    if v.size == 0:
        return False
    if v.size > sample:
        rng = np.random.default_rng(0)
        v = rng.choice(v, size=sample, replace=False)
    return (v > thresh).mean() > frac


def _interchain_mask(n: int, residue_map: pd.DataFrame) -> np.ndarray:
    chains = residue_map["chain"].to_numpy()
    if len(chains) != n:
        mask = np.ones((n, n), dtype=bool); np.fill_diagonal(mask, False)
        return mask
    mask = chains[:, None] != chains[None, :]
    if not np.any(mask):
        mask = np.ones((n, n), dtype=bool); np.fill_diagonal(mask, False)
    return mask

# ----------------------------- writers -----------------------------

def _write_single_sheet(job_dir: str, df: pd.DataFrame, sheet_name: str, filename: str) -> None:
    xlsx_path = os.path.join(job_dir, filename)
    tmp_path  = os.path.join(job_dir, f"__tmp__{filename}")
    with suppress(Exception): ensure_writable(xlsx_path)
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl", mode="w") as w:
            df.to_excel(w, sheet_name=sheet_name, index=False)
        print(f"[ok] wrote -> {xlsx_path}")
        return
    except PermissionError:
        print(f"[warn] Permission denied writing {xlsx_path} (is it open?). Writing to a temp workbook instead.")
    except Exception as e:
        print(f"[warn] Could not write {xlsx_path} ({e}). Writing to a temp workbook instead.")
    with pd.ExcelWriter(tmp_path, engine="openpyxl", mode="w") as w:
        df.to_excel(w, sheet_name=sheet_name, index=False)
    print(f"[ok] wrote {tmp_path}\n→ Close {os.path.basename(xlsx_path)} if open, then move/rename the temp file.")

def write_minpae_workbook(job_dir: str, df: pd.DataFrame) -> None:
    _write_single_sheet(job_dir, df, sheet_name="minPAE", filename="per_residue_minPAE.xlsx")

def write_mind_workbook(job_dir: str, df: pd.DataFrame) -> None:
    _write_single_sheet(job_dir, df, sheet_name="minD", filename="per_residue_minD.xlsx")

def write_maxcontact_workbook(job_dir: str, df: pd.DataFrame) -> None:
    _write_single_sheet(job_dir, df, sheet_name="maxContact", filename="per_residue_maxContact.xlsx")

# ----------------------------- core computations -----------------------------

def compute_min_vectors_interchain_pae(pae_raw: np.ndarray, residue_map: pd.DataFrame) -> Dict[str, np.ndarray]:
    pae = np.asarray(pae_raw, dtype=float)
    if pae.ndim != 2 or pae.shape[0] != pae.shape[1]:
        raise ValueError(f"PAE matrix must be square, got {pae.shape}")
    if _looks_like_angstroms(pae):
        pae = pae / 30.0
    n = pae.shape[0]; inter = _interchain_mask(n, residue_map)
    masked = np.where(inter, pae, np.nan)
    row_min = np.nanmin(masked, axis=1); col_min = np.nanmin(masked.T, axis=1)
    sym = (pae + pae.T)/2.0; sym_row_min = np.nanmin(np.where(inter, sym, np.nan), axis=1)
    both_dir_min = np.fmin(row_min, col_min)
    return {"row_min": row_min, "col_min": col_min, "sym_row_min": sym_row_min, "both_dir_min": both_dir_min}


def compute_min_vectors_interchain_dist(D_raw: np.ndarray, residue_map: pd.DataFrame) -> Dict[str, np.ndarray]:
    D = np.asarray(D_raw, dtype=float)
    if D.ndim != 2 or D.shape[0] != D.shape[1]:
        raise ValueError(f"Distance matrix must be square, got {D.shape}")
    n = D.shape[0]; inter = _interchain_mask(n, residue_map)
    masked = np.where(inter, D, np.nan)
    row_min = np.nanmin(masked, axis=1); col_min = np.nanmin(masked.T, axis=1)
    sym = (D + D.T)/2.0; sym_row_min = np.nanmin(np.where(inter, sym, np.nan), axis=1)
    both_dir_min = np.fmin(row_min, col_min)
    return {"row_min": row_min, "col_min": col_min, "sym_row_min": sym_row_min, "both_dir_min": both_dir_min}


def compute_max_vectors_interchain_contact(P_raw: np.ndarray, residue_map: pd.DataFrame) -> Dict[str, np.ndarray]:
    P = np.asarray(P_raw, dtype=float)
    if P.ndim != 2 or P.shape[0] != P.shape[1]:
        raise ValueError(f"Contact matrix must be square, got {P.shape}")
    n = P.shape[0]; inter = _interchain_mask(n, residue_map)
    masked = np.where(inter, P, np.nan)
    row_max = np.nanmax(masked, axis=1)
    col_max = np.nanmax(masked.T, axis=1)
    sym = (P + P.T)/2.0
    sym_row_max = np.nanmax(np.where(inter, sym, np.nan), axis=1)
    both_dir_max = np.fmax(row_max, col_max)
    return {"row_max": row_max, "col_max": col_max, "sym_row_max": sym_row_max, "both_dir_max": both_dir_max}

# ----------------------------- processors -----------------------------

def process_job_minPAE(job_dir: str) -> None:
    per_model = read_PAE_per_model(job_dir)
    avg_mat = None
    if per_model is None:
        avg_mat = read_AvgPAE(job_dir)
    if per_model is None and avg_mat is None:
        # JSON fallback (PAE only)
        jsons = find_job_jsons(job_dir)
        if jsons:
            mats: Dict[int, np.ndarray] = {}; N: Optional[int] = None
            for jf in jsons:
                p = os.path.join(job_dir, jf)
                with open(p, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                pae = data.get("pae")
                if pae is None:
                    continue
                A = np.asarray(pae, dtype=float)
                N = N or A.shape[0]
                if A.shape != (N, N):
                    pad0 = max(0, N - A.shape[0]); pad1 = max(0, N - A.shape[1])
                    if pad0 or pad1:
                        A = np.pad(A, ((0, pad0), (0, pad1)), mode="edge")
                    A = A[:N, :N]
                suf = os.path.splitext(jf)[0].split("_")[-1]
                m = int(suf) if suf.isdigit() else len(mats)
                mats[m] = A
                del data
            per_model = mats or None
    if per_model is None and avg_mat is None:
        print(f"[minPAE] skip: No PAE found for {job_dir}"); return

    N = (next(iter(per_model.values())).shape[0] if per_model is not None else avg_mat.shape[0])
    residue_map = load_residue_map(job_dir, N)
    df = pd.DataFrame({k: residue_map[k] for k in ["global_idx","chain","chain_pos","aa","pdb_resnum"]})

    if per_model is not None:
        model_indices = sorted(per_model.keys())
        for m in model_indices:
            vecs = compute_min_vectors_interchain_pae(per_model[m], residue_map)
            for metric, v in vecs.items():
                df[f"{metric}_model_{m}"] = v
        for metric in ("row_min","col_min","sym_row_min","both_dir_min"):
            M = np.vstack([df[f"{metric}_model_{m}"].to_numpy(float) for m in model_indices])
            df[f"mean_{metric}"] = np.nanmean(M, axis=0)
    else:
        vecs = compute_min_vectors_interchain_pae(avg_mat, residue_map)
        for metric, v in vecs.items():
            df[f"avg_{metric}"] = v

    write_minpae_workbook(job_dir, df)


def process_job_minD(job_dir: str) -> None:
    per_model = read_Geom_per_model(job_dir)
    avg_mat = None
    if per_model is None:
        avg_mat = read_AvgGeom(job_dir)
    if per_model is None and avg_mat is None:
        print(f"[minD] skip: No GeomDist found for {job_dir} (run _023_ResMetrBot.py with GeomDist)."); return

    N = (next(iter(per_model.values())).shape[0] if per_model is not None else avg_mat.shape[0])
    residue_map = load_residue_map(job_dir, N)
    df = pd.DataFrame({k: residue_map[k] for k in ["global_idx","chain","chain_pos","aa","pdb_resnum"]})

    if per_model is not None:
        model_indices = sorted(per_model.keys())
        for m in model_indices:
            vecs = compute_min_vectors_interchain_dist(per_model[m], residue_map)
            for metric, v in vecs.items():
                df[f"{metric}_model_{m}"] = v  # Å
        for metric in ("row_min","col_min","sym_row_min","both_dir_min"):
            M = np.vstack([df[f"{metric}_model_{m}"].to_numpy(float) for m in model_indices])
            df[f"mean_{metric}"] = np.nanmean(M, axis=0)  # Å
    else:
        vecs = compute_min_vectors_interchain_dist(avg_mat, residue_map)
        for metric, v in vecs.items():
            df[f"avg_{metric}"] = v  # Å

    write_mind_workbook(job_dir, df)


def process_job_maxContact(job_dir: str) -> None:
    per_model = read_Contact_per_model(job_dir)
    avg_mat = None
    if per_model is None:
        avg_mat = read_AvgContact(job_dir)
    if per_model is None and avg_mat is None:
        print(f"[maxContact] skip: No ContactProbs found for {job_dir}."); return

    N = (next(iter(per_model.values())).shape[0] if per_model is not None else avg_mat.shape[0])
    residue_map = load_residue_map(job_dir, N)
    df = pd.DataFrame({k: residue_map[k] for k in ["global_idx","chain","chain_pos","aa","pdb_resnum"]})

    if per_model is not None:
        model_indices = sorted(per_model.keys())
        for m in model_indices:
            vecs = compute_max_vectors_interchain_contact(per_model[m], residue_map)
            for metric, v in vecs.items():
                df[f"{metric}_model_{m}"] = v  # 0–1
        for metric in ("row_max","col_max","sym_row_max","both_dir_max"):
            M = np.vstack([df[f"{metric}_model_{m}"].to_numpy(float) for m in model_indices])
            df[f"mean_{metric}"] = np.nanmean(M, axis=0)  # 0–1
    else:
        vecs = compute_max_vectors_interchain_contact(avg_mat, residue_map)
        for metric, v in vecs.items():
            df[f"avg_{metric}"] = v  # 0–1

    write_maxcontact_workbook(job_dir, df)

# ----------------------------- CLI -----------------------------

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python src/_024_MinMetrBot.py <run_or_job_path>")
        sys.exit(1)

    target = sys.argv[1]
    if not os.path.isdir(target):
        print(f"ERROR: {target} is not a directory")
        sys.exit(1)

    if is_job_dir(target):
        process_job_minPAE(target)
        process_job_minD(target)
        process_job_maxContact(target)
    else:
        processed = 0
        for root, dirs, files in os.walk(target):
            if is_job_dir(root):
                process_job_minPAE(root)
                process_job_minD(root)
                process_job_maxContact(root)
                processed += 1
        if processed == 0:
            print(f"No AF3 job folders found under {target}")

if __name__ == "__main__":
    main()
