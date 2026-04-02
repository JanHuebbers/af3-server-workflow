#!/usr/bin/env python3
"""
_023_ResMetrBot.py  (CSV-only residue mapping, CSV outputs per sheet)
--------------------------------------------------------------------
Extracts per-residue metrics from AF3 *_full_data_*.json and writes each result
as **separate CSV files** instead of a single XLSX workbook.
Residue mapping is read EXCLUSIVELY from CSVs generated from the AF3 input JSONs
by _012_ResidueMapBot.py.

Writes (each as its own CSV under per_residue_metrics/ in the job folder):
  • pLDDT.csv (atom-level aggregation)
  • ContactProbs_model_<idx>.csv per model (unless --avg-only)
  • PAE_model_<idx>.csv per model (unless --avg-only)
  • Avg_ContactProbs.csv, Avg_PAE.csv (averages across models)
  • GeomDist_model_<idx>.csv per model (Å) (unless --avg-only)
  • Avg_GeomDist.csv (Å)
  • residue_map.csv (as loaded from the CSV)

Important:
  • Matrices are trimmed to the CSV residue count (protein-only length).
  • No CIF parsing was done previously; this script now (optionally) reads mmCIFs via gemmi.

CLI flags preserved:
  --avg-only, --no-contact, --no-pae, --models
New flag:
  --no-geom  (skip geometric distance matrices from mmCIF)
"""

import os
import re
import gc
import sys
import json
import glob
import errno
import argparse
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from perm_helper import ensure_writable, sweep_fix_outputs

# Optional dependency: gemmi for mmCIF parsing
try:
    import gemmi  # pip install gemmi
    _HAS_GEMMI = True
except Exception:
    _HAS_GEMMI = False

# =============================================================================
# Utilities
# =============================================================================

def _safe_mean(df: pd.DataFrame, axis: int = 1):
    return df.mean(axis=axis, skipna=True)

def _normalize_fulldata(data):
    """Normalize _full_data JSON into a dict (handles older list-wrapped formats)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}

def _split_job_folder(job_folder_name: str) -> Tuple[str, str]:
    """
    From a job folder like '0010_01_...' extract: sim_id='0010', job_num='01'
    """
    m = re.match(r"^(\d{4})_(\d{2})", job_folder_name)
    if not m:
        raise ValueError(f"Cannot infer SimID/job from folder '{job_folder_name}'. "
                         f"Expected prefix like '0001_01_...'.")
    sim_id, job_num = m.group(1), m.group(2)
    return sim_id, job_num

def _project_root_from_job_path(job_path: str) -> str:
    """
    AF3 job folders live at <project_root>/AF3_output/<SimID>/<job_folder>.
    """
    return os.path.abspath(os.path.join(job_path, os.pardir, os.pardir, os.pardir))

def _load_residue_map_csv(job_path: str) -> pd.DataFrame:
    """
    Locate and load the residue-map CSV written by _012_ResidueMapBot.py.
    """
    job_folder = os.path.basename(job_path.rstrip(os.sep))
    sim_id, job_num = _split_job_folder(job_folder)
    base = f"{sim_id}-{job_num}"

    project_root = _project_root_from_job_path(job_path)
    resdir = os.path.join(project_root, "input", "residue_maps", sim_id)

    # Try to capture a seed from the job folder name, e.g. "0020_01_1710_..."
    seed: Optional[str] = None
    m_seed = re.match(r"^\d{4}_\d{2}_(\d+)", job_folder)  # allow multi-digit seeds
    if m_seed:
        seed = m_seed.group(1)

    candidates: List[str] = []
    candidates.append(os.path.join(resdir, f"{base}_residue_map.csv"))
    if seed:
        candidates.append(os.path.join(resdir, f"{base}-{seed}_residue_map.csv"))
        candidates.append(os.path.join(resdir, f"{sim_id}_{job_num}-{seed}_residue_map.csv"))
        candidates.append(os.path.join(resdir, f"{sim_id}_{job_num}_{seed}_residue_map.csv"))
    candidates.append(os.path.join(resdir, f"{base}-*_residue_map.csv"))
    candidates.append(os.path.join(resdir, f"{sim_id}_{job_num}_residue_map.csv"))
    candidates.append(os.path.join(resdir, f"{job_folder}_residue_map.csv"))
    candidates.append(os.path.join(job_path, "residue_map.csv"))
    candidates.append(os.path.join(job_path, "*residue_map*.csv"))

    resolved: Optional[str] = None
    for pat in candidates:
        if any(ch in pat for ch in "*?[]"):
            for p in sorted(glob.glob(pat)):
                if os.path.isfile(p):
                    resolved = p
                    break
        else:
            if os.path.isfile(pat):
                resolved = pat
        if resolved:
            break

    if not resolved:
        tried = "\n  - ".join(candidates[:8]) + ("\n  ... (more)" if len(candidates) > 8 else "")
        raise FileNotFoundError(
            "Residue-map CSV not found.\n"
            "Looked for (legacy & new) names such as:\n"
            f"  - {tried}\n"
            "Make sure _012_ResidueMapBot.py wrote CSVs under input/residue_maps/<SimID>/"
        )

    df = pd.read_csv(resolved)
    needed = {"global_idx", "chain_id", "chain_pos", "aa", "pdb_resnum"}
    if not needed.issubset(df.columns):
        raise RuntimeError(f"Residue-map CSV missing columns {needed - set(df.columns)} at {resolved}")

    cols = ["global_idx", "chain_id", "chain_pos", "aa", "pdb_resnum"]
    if "token_chain_id" in df.columns:
        cols.append("token_chain_id")
    else:
        df["token_chain_id"] = df["chain_id"]

    out = df[cols].copy()
    out["global_idx"] = pd.to_numeric(out["global_idx"], errors="coerce").astype("Int64")
    out["chain_pos"]   = pd.to_numeric(out["chain_pos"], errors="coerce").astype("Int64")
    out["aa"]          = out["aa"].astype(str)
    out["chain_id"]    = out["chain_id"].astype(str)
    out["pdb_resnum"]  = out["pdb_resnum"].astype(str)
    out["token_chain_id"] = out["token_chain_id"].astype(str)

    out = out.dropna(subset=["global_idx", "chain_pos"]).reset_index(drop=True)

    if out["global_idx"].notna().all():
        try:
            out = out.sort_values("global_idx")
        except Exception:
            pass

    return out.reset_index(drop=True)

# =============================================================================
# GeomDist helpers (mmCIF → residue Cβ/Cα coords → NxN distances)
# =============================================================================

def _find_model_cif(job_path: str, model_idx: str) -> Optional[str]:
    """
    Heuristically find the mmCIF for a given model index inside job_path.
    Tries several common patterns; falls back to a single *.cif if only one exists.
    """
    cif_files = sorted(glob.glob(os.path.join(job_path, "*.cif")))
    if not cif_files:
        return None
    # Try strong matches first
    candidates = []
    base_patterns = [
        f"_{model_idx}.cif", f"-{model_idx}.cif",
        f"model_{model_idx}.cif", f"ranked_{model_idx}.cif",
        f"_model{model_idx}.cif", f"_ranked{model_idx}.cif",
        f".{model_idx}.cif"
    ]
    for cf in cif_files:
        name = os.path.basename(cf)
        if any(pat in name for pat in base_patterns):
            candidates.append(cf)
    if candidates:
        return sorted(candidates)[0]
    if len(cif_files) == 1:
        return cif_files[0]
    return None

def _coords_from_chain_residue_order(model: "gemmi.Model", chain_name: str) -> List[Tuple[float,float,float,str]]:
    out: List[Tuple[float,float,float,str]] = []
    chain = None
    for ch in model:
        if ch.name == chain_name:
            chain = ch
            break
    if chain is None:
        return out

    for res in chain:
        has_ca = any(at.name.strip() == 'CA' for at in res)
        if not has_ca:
            continue
        aa3 = res.name.strip().upper() if isinstance(res.name, str) else str(res.name).strip().upper()
        want_atom = 'CA' if aa3 == 'GLY' else 'CB'
        picked = None
        for at in res:
            nm = at.name.strip()
            if nm == want_atom:
                picked = at
                break
        if picked is None:
            for at in res:
                if at.name.strip() == 'CA':
                    picked = at
                    break
        if picked is not None:
            p = picked.pos
            out.append((float(p.x), float(p.y), float(p.z), aa3))
        else:
            out.append((np.nan, np.nan, np.nan, aa3))
    return out

def _build_residue_coords_from_cif(cif_path: str, residue_map: pd.DataFrame) -> np.ndarray:
    if not _HAS_GEMMI:
        raise RuntimeError("gemmi is required for geometric distances. Install with: pip install gemmi")
    st = gemmi.read_structure(cif_path)
    if len(st) == 0:
        raise RuntimeError(f"No models found in CIF: {cif_path}")
    model = st[0]

    chain_cache: Dict[str, List[Tuple[float,float,float,str]]] = {}
    for ch in model:
        chain_cache[ch.name] = _coords_from_chain_residue_order(model, ch.name)

    N = len(residue_map)
    coords = np.full((N, 3), np.nan, dtype=np.float32)

    for idx, row in residue_map.reset_index(drop=True).iterrows():
        cand_ids = []
        if "token_chain_id" in row and isinstance(row["token_chain_id"], str):
            cand_ids.append(row["token_chain_id"])
        if isinstance(row["chain_id"], str) and row["chain_id"] not in cand_ids:
            cand_ids.append(row["chain_id"])

        chain_vec = None
        for cid in cand_ids:
            if cid in chain_cache:
                chain_vec = chain_cache[cid]
                break
        if chain_vec is None:
            for cid in cand_ids:
                for known in chain_cache.keys():
                    if known.lower() == cid.lower():
                        chain_vec = chain_cache[known]
                        break
                if chain_vec is not None:
                    break
        if chain_vec is None or not chain_vec:
            continue

        pos = int(row["chain_pos"])  # 1-based AA index from CSV
        j = pos - 1
        if 0 <= j < len(chain_vec):
            x, y, z, _aa3 = chain_vec[j]
            coords[idx, 0] = x if np.isfinite(x) else np.nan
            coords[idx, 1] = y if np.isfinite(y) else np.nan
            coords[idx, 2] = z if np.isfinite(z) else np.nan
    return coords

def _pairwise_dist_matrix(coords: np.ndarray) -> np.ndarray:
    N = coords.shape[0]
    mask = np.isfinite(coords).all(axis=1)
    X = coords.astype(np.float64, copy=False)
    X_filled = np.where(np.isfinite(X), X, 0.0)
    diffs = X_filled[:, None, :] - X_filled[None, :, :]
    D = np.sqrt(np.sum(diffs * diffs, axis=-1, dtype=np.float64), dtype=np.float64)
    D[~mask, :] = np.nan
    D[:, ~mask] = np.nan
    return D.astype(np.float32, copy=False)

# =============================================================================
# Core extraction
# =============================================================================

def extract_per_residue_metrics_for_job(
    job_path: str,
    avg_only: bool = False,
    write_contact: bool = True,
    write_pae: bool = True,
    write_geom: bool = True,
    models_filter: Optional[List[int]] = None,
) -> None:

    # Ensure per-job output directory exists
    out_dir = os.path.join(job_path, "per_residue_metrics")
    os.makedirs(out_dir, exist_ok=True)

    # Discover *_full_data_*.json files
    all_json = sorted(f for f in os.listdir(job_path) if f.endswith(".json") and "_full_data_" in f)
    if not all_json:
        print(f"No full_data JSONs found in {job_path}")
        return

    if models_filter is not None:
        keep = set(str(m) for m in models_filter)
        all_json = [f for f in all_json if f.split("_")[-1].split(".")[0] in keep]

    # Load residue map once (CSV-only source) & get protein-only length
    residue_map = _load_residue_map_csv(job_path)
    n_protein = len(residue_map)
    if n_protein <= 0:
        raise RuntimeError(f"Residue-map CSV produced zero residues for {job_path}")

    # Write residue_map CSV (as-is) into the output folder
    residue_map_out = os.path.join(out_dir, "residue_map.csv")
    ensure_writable(residue_map_out)
    residue_map.to_csv(residue_map_out, index=False)

    # Build a MultiIndex to label rows/columns of matrices in CSVs (to preserve mapping)
    row_index = pd.MultiIndex.from_arrays(
        [
            residue_map["global_idx"].tolist(),
            residue_map["chain"].tolist() if "chain" in residue_map.columns else residue_map["chain_id"].tolist(),
            residue_map["chain_pos"].tolist(),
            residue_map["aa"].tolist(),
            residue_map["pdb_resnum"].tolist(),
        ],
        names=["global_idx", "chain", "chain_pos", "aa", "pdb_resnum"],
    )

    # Containers for averages
    n_residues_json = 0
    pae_running_sum: Optional[pd.DataFrame] = None
    contact_running_sum: Optional[pd.DataFrame] = None
    geom_running_sum: Optional[pd.DataFrame] = None
    n_models_pae = n_models_contact = n_models_geom = 0

    # pLDDT aggregation
    plddt_dict: Dict[str, List[float]] = {}
    atom_chain_dict: Dict[str, List[int]] = {}

    # Per-model processing
    for fname in all_json:
        model_idx = fname.split("_")[-1].split(".")[0]
        fpath = os.path.join(job_path, fname)
        with open(fpath, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        data = _normalize_fulldata(raw)
        if not isinstance(data, dict) or not data:
            print(f"  Warning: {fpath} could not be normalized to a dict; skipping.")
            continue

        # pLDDT / atom_chain_ids
        plddt_vals = data.get("atom_plddts", [])
        atom_chain_ids = data.get("atom_chain_ids", [])
        plddt_vals = plddt_vals if isinstance(plddt_vals := plddt_vals, list) else []
        atom_chain_ids = atom_chain_ids if isinstance(atom_chain_ids, list) else []
        plddt_dict[model_idx] = plddt_vals
        atom_chain_dict[model_idx] = atom_chain_ids

        # token length
        if n_residues_json == 0 and "token_chain_ids" in data:
            token_chain_ids = list(data["token_chain_ids"])
            n_residues_json = len(token_chain_ids)

        # CONTACT
        if write_contact:
            cmat = data.get("contact_probs")
            if isinstance(cmat, (list, tuple)):
                cdf = pd.DataFrame(cmat, copy=False)
                if n_residues_json and (cdf.shape[0] != n_residues_json or cdf.shape[1] != n_residues_json):
                    cdf = cdf.reindex(index=range(n_residues_json), columns=range(n_residues_json))
                # Trim to protein-only
                cdf = cdf.iloc[:n_protein, :n_protein]
                # Label with residue mapping so CSV retains headers
                cdf.index = row_index
                cdf.columns = row_index
                # Accumulate average
                if contact_running_sum is None:
                    contact_running_sum = cdf.astype("float64")
                else:
                    contact_running_sum = contact_running_sum.add(cdf, fill_value=0.0)
                n_models_contact += 1
                # Per-model CSV (unless avg-only)
                if not avg_only:
                    out_fp = os.path.join(out_dir, f"ContactProbs_model_{model_idx}.csv")
                    ensure_writable(out_fp)
                    cdf.to_csv(out_fp)  # keep mapping headers
                del cdf  # <— now safely inside the isinstance(...) block

        # PAE
        if write_pae:
            pmat = data.get("pae")
            if isinstance(pmat, (list, tuple)):
                pdf = pd.DataFrame(pmat, copy=False)
                if n_residues_json and (pdf.shape[0] != n_residues_json or pdf.shape[1] != n_residues_json):
                    pdf = pdf.reindex(index=range(n_residues_json), columns=range(n_residues_json))
                pdf = pdf.iloc[:n_protein, :n_protein]
                pdf.index = row_index
                pdf.columns = row_index
                if pae_running_sum is None:
                    pae_running_sum = pdf.astype("float64")
                else:
                    pae_running_sum = pae_running_sum.add(pdf, fill_value=0.0)
                n_models_pae += 1
                if not avg_only:
                    out_fp = os.path.join(out_dir, f"PAE_model_{model_idx}.csv")
                    ensure_writable(out_fp)
                    pdf.to_csv(out_fp)
                del pdf

        # Geometric distances from mmCIF
        if write_geom:
            if not _HAS_GEMMI:
                if n_models_geom == 0:
                    print("  [geom] gemmi not installed; skipping GeomDist. Install with: pip install gemmi")
            else:
                cif_path = _find_model_cif(job_path, model_idx)
                if cif_path is not None:
                    try:
                        coords = _build_residue_coords_from_cif(cif_path, residue_map)
                        dist_mat = _pairwise_dist_matrix(coords)
                        gdf = pd.DataFrame(dist_mat, copy=False).iloc[:n_protein, :n_protein]
                        gdf.index = row_index
                        gdf.columns = row_index
                        if geom_running_sum is None:
                            geom_running_sum = gdf.astype("float64")
                        else:
                            geom_running_sum = geom_running_sum.add(gdf, fill_value=0.0)
                        n_models_geom += 1
                        if not avg_only:
                            out_fp = os.path.join(out_dir, f"GeomDist_model_{model_idx}.csv")
                            ensure_writable(out_fp)
                            gdf.to_csv(out_fp)
                        del gdf
                    except Exception as e:
                        print(f"  [geom] failed for model {model_idx} at {cif_path}: {e}")

        del data
        gc.collect()

    # pLDDT sheet (atom-level): build a compact CSV
    max_atoms = max((len(v) for v in plddt_dict.values()), default=0)
    plddt_df = pd.DataFrame({"atom_index": range(max_atoms)})
    first_chain_ids = atom_chain_dict[next(iter(atom_chain_dict))] if atom_chain_dict else []
    padded_chain = (first_chain_ids + [None] * max(0, max_atoms - len(first_chain_ids))) if first_chain_ids else [None] * max_atoms
    plddt_df["chain_id_token"] = padded_chain
    for idx_str, vals in sorted(plddt_dict.items(), key=lambda x: int(x[0])):
        padded_vals = vals + [pd.NA] * max(0, max_atoms - len(vals))
        plddt_df[f"plddt_{idx_str}"] = padded_vals
    pl_cols = [c for c in plddt_df.columns if c.startswith("plddt_")]
    plddt_df["avg_plddt"] = _safe_mean(plddt_df[pl_cols], axis=1) if pl_cols else pd.NA

    plddt_out = os.path.join(out_dir, "pLDDT.csv")
    ensure_writable(plddt_out)
    plddt_df.to_csv(plddt_out, index=False)

    # Averages
    if write_contact and contact_running_sum is not None and n_models_contact > 0:
        avg_c = (contact_running_sum / float(n_models_contact))
        avg_c.index = row_index
        avg_c.columns = row_index
        out_fp = os.path.join(out_dir, "Avg_ContactProbs.csv")
        ensure_writable(out_fp)
        avg_c.to_csv(out_fp)
        del avg_c

    if write_pae and pae_running_sum is not None and n_models_pae > 0:
        avg_p = (pae_running_sum / float(n_models_pae))
        avg_p.index = row_index
        avg_p.columns = row_index
        out_fp = os.path.join(out_dir, "Avg_PAE.csv")
        ensure_writable(out_fp)
        avg_p.to_csv(out_fp)
        del avg_p

    if write_geom and geom_running_sum is not None and n_models_geom > 0:
        avg_g = (geom_running_sum / float(n_models_geom))
        avg_g.index = row_index
        avg_g.columns = row_index
        out_fp = os.path.join(out_dir, "Avg_GeomDist.csv")
        ensure_writable(out_fp)
        avg_g.to_csv(out_fp)
        del avg_g

    # cleanup
    del (plddt_df, residue_map, contact_running_sum, pae_running_sum, geom_running_sum)
    gc.collect()

# =============================================================================
# Driver
# =============================================================================

def process_all_jobs(
    base_path: str,
    avg_only: bool,
    write_contact: bool,
    write_pae: bool,
    write_geom: bool,
    models_filter: Optional[List[int]],
):
    """Walk base_path, run extraction in each AF3 job folder that has *_full_data_*.json."""
    processed = 0

    try:
        ensure_writable(base_path)
        sweep_fix_outputs(base_path)
    except Exception:
        pass

    for root, _, files in os.walk(base_path):
        if any(f.endswith(".json") and "_full_data_" in f for f in files):
            try:
                print(f"Processing job: {root}")
                extract_per_residue_metrics_for_job(
                    root,
                    avg_only=avg_only,
                    write_contact=write_contact,
                    write_pae=write_pae,
                    write_geom=write_geom,
                    models_filter=models_filter,
                )
                processed += 1
            except MemoryError:
                print("MemoryError — retrying in averages-only mode for this job…")
                try:
                    extract_per_residue_metrics_for_job(
                        root,
                        avg_only=True,
                        write_contact=write_contact,
                        write_pae=write_pae,
                        write_geom=write_geom,
                        models_filter=models_filter,
                    )
                    processed += 1
                except Exception as e:
                    print(f"  Failed even in averages-only mode: {e}", file=sys.stderr)
            except Exception as e:
                print(f"  Error in {root}: {e}", file=sys.stderr)
            gc.collect()

    if processed == 0:
        print(f"No AF3 job folders with full_data JSONs found under {base_path}")
    else:
        print(f"Processed {processed} job(s) under {base_path}")

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=(
            "Extract per-residue metrics from AF3 *_full_data_*.json files; "
            "CSV-only residue mapping; write per-model CSVs + averages + pLDDT + residue_map."
        )
    )
    p.add_argument("path", help="Job folder or base directory (e.g., AF3_output/0016)")
    p.add_argument("--avg-only", action="store_true",
                   help="Skip per-model CSVs; write only pLDDT + Avg_ContactProbs + Avg_PAE + Avg_GeomDist + residue_map.")
    p.add_argument("--no-contact", action="store_true",
                   help="Skip computing/writing contact probability matrices entirely.")
    p.add_argument("--no-pae", action="store_true",
                   help="Skip computing/writing PAE matrices entirely.")
    p.add_argument("--no-geom", action="store_true",
                   help="Skip computing/writing geometric distance matrices from mmCIF.")
    p.add_argument("--models", type=str, default=None,
                   help="Comma-separated list of model indices to include (e.g., '0,1,2').")
    return p.parse_args(argv)

if __name__ == "__main__":
    print("[GetResidueMetr] v2025-09-05 CSV-only residue mapping + GeomDist → CSV outputs")
    args = parse_args()
    target = args.path
    if not os.path.isdir(target):
        print(f"ERROR: {target} is not a directory")
        sys.exit(1)

    models_filter = None
    if args.models:
        try:
            models_filter = [int(x.strip()) for x in args.models.split(",") if x.strip() != ""]
        except ValueError:
            print("WARNING: --models must be a comma-separated list of integers like '0,1,2'. Ignoring.", file=sys.stderr)
            models_filter = None

    process_all_jobs(
        base_path=target,
        avg_only=args.avg_only,
        write_contact=not args.no_contact,
        write_pae=not args.no_pae,
        write_geom=not args.no_geom,
        models_filter=models_filter,
    )
