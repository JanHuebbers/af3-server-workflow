#!/usr/bin/env python3
import os
import json
import pandas as pd

def read_fasta(fasta_path):
    """
    Return single-line amino-acid sequence from a FASTA file (skip headers).
    """
    if not os.path.isfile(fasta_path):
        raise FileNotFoundError(f"Could not find FASTA: {fasta_path}")
    seq_lines = []
    with open(fasta_path, "r") as fp:
        for line in fp:
            if line.startswith(">"):
                continue
            seq_lines.append(line.strip())
    return "".join(seq_lines)

def _norm_path_from_excel(relpath: str) -> str:
    """
    Normalize an Excel path (may contain backslashes) to absolute path
    relative to project root (one level up from this script).
    """
    relpath = (relpath or "").strip()
    if not relpath:
        return ""
    # Respect absolute paths as-is
    if os.path.isabs(relpath):
        return relpath
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(proj_root, relpath.replace("\\", os.sep))

def _parse_int(value, fallback: int) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return fallback
        return int(str(value).strip())
    except Exception:
        return fallback
      
# Collect chains helper
def _collect_chains_from_row(row: pd.Series):
    """
    Collect chains A..D present in the row.
    Supports optional counters via ChainX_count OR ChainX_counter.
    Skips any chain where count <= 0.
    """
    chains = []
    for label in ["A", "B", "C", "D"]:
        seq_col = f"Chain{label}_seq"
        name_col = f"Chain{label}_name"
        cnt1 = f"Chain{label}_count"
        cnt2 = f"Chain{label}_counter"

        if seq_col not in row or pd.isna(row[seq_col]) or not str(row[seq_col]).strip():
            continue

        fasta_path = _norm_path_from_excel(str(row[seq_col]))
        try:
            seq = read_fasta(fasta_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(str(e))

        # default 1 if no counter provided
        count_raw = row[cnt1] if (cnt1 in row and pd.notna(row[cnt1])) else row[cnt2] if (cnt2 in row and pd.notna(row[cnt2])) else 1
        count = _parse_int(count_raw, 1)

        if count <= 0:
            print(f"    Skipping Chain{label}: count <= 0")
            continue

        entry = {"proteinChain": {"sequence": seq, "count": count}}
        if name_col in row and pd.notna(row[name_col]) and str(row[name_col]).strip():
            entry["proteinChain"]["name"] = str(row[name_col]).strip()
        chains.append(entry)
    return chains

# Parse tokens from excel helper
def _parse_seed_token_list(raw):
    """
    Parse a string of seed tokens into a list of ints.
    Supports integers, ranges 'a-b' (inclusive), and comma/semicolon lists.
    """
    # handle missing / NaN early
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []

    # Fast path: numeric cells from Excel (int or float like 1234.0)
    if isinstance(raw, (int, float)):
        try:
            return [int(raw)]
        except Exception:
            return []

    txt = str(raw).strip()
    if not txt:
        return []

    seeds = []
    for token in txt.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-")
            if len(parts) == 2:
                try:
                    a = int(str(parts[0]).strip())
                    b = int(str(parts[1]).strip())
                    if a <= b:
                        seeds.extend(range(a, b + 1))
                    else:
                        seeds.extend(range(a, b - 1, -1))  # reversed range inclusive
                except Exception:
                    pass  # ignore bad range
            # else: ignore malformed multi-dash token
        else:
            try:
                seeds.append(int(token))
            except Exception:
                pass  # ignore bad token

    # dedupe (preserve order)
    seen, uniq = set(), []
    for s in seeds:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq

# Extract seeds from row
def _seeds_from_row(row: pd.Series, default_seeds: list[int]) -> list[int]:
      """
      Read per-job model seeds from an Excel row if present; otherwise return default_seeds.
      Supported columns (first match wins): ModelSeeds, Seeds, Seed, ModelSeed,
      or any column named Seed<digits> (e.g., Seed1, Seed2, ...).
      Values support integers, comma/semicolon lists, and inclusive ranges 'a-b'.
      """
      # priority-ordered simple names
      candidates = ["ModelSeeds", "Seeds", "Seed", "ModelSeed"]
      for col in candidates:
          if col in row and pd.notna(row.get(col)) and str(row.get(col)).strip():
              parsed = _parse_seed_token_list(row.get(col))
              if parsed:
                  return parsed
  
      # gather Seed1, Seed2, ... if present (sorted by natural index)
      seed_cols = []
      for col in row.index:
          if isinstance(col, str) and col.lower().startswith("seed"):
              tail = col[4:]  # after 'Seed'
              if tail.isdigit():
                  seed_cols.append((int(tail), col))
      if seed_cols:
          seeds = []
          for _, col in sorted(seed_cols, key=lambda x: x[0]):
              parsed = _parse_seed_token_list(row.get(col))
              if parsed:
                  seeds.extend(parsed)
          if seeds:
              # dedupe while preserving order
              seen = set()
              uniq = []
              for s in seeds:
                  if s not in seen:
                      seen.add(s)
                      uniq.append(s)
              return uniq
  
      return list(default_seeds or [])      

# Create json from excel input
def make_json_from_df(df, run_name, ion_default, model_seeds, output_json):
    """
    Build AF3 input JSON from one Excel sheet:
      - Optional ion block (omitted if count <= 0)
      - 1..4 chains (A..D), each omitted if count <= 0
    """
    jobs = []

    for idx, row in df.iterrows():
        job_name = str(row.get("JobName", "")).strip()
        if not job_name:
            continue

        # Ion type and count
        ion_type = "CA"
        if "Ions" in df.columns and pd.notna(row.get("Ions")) and str(row["Ions"]).strip():
            ion_type = str(row["Ions"]).strip().upper()

        ion_count_cell = row["Ions_count"] if ("Ions_count" in df.columns and pd.notna(row.get("Ions_count"))) else None
        ion_count = _parse_int(ion_count_cell, ion_default)

        # Gather chains (skip count<=0)
        try:
            chains = _collect_chains_from_row(row)
        except FileNotFoundError as e:
            print(f"[{run_name}] ERROR: {e}. Skipping job \"{job_name}\".")
            continue

        if not chains:
            print(f"[{run_name}] WARNING: No eligible chains on row {idx+1} for job '{job_name}' (all missing or count<=0). Skipping.")
            continue

        sequences_list = []

        # Only add ion if ion_count > 0
        if ion_count > 0:
            sequences_list.append({
                "ion": {
                    "ion": ion_type,
                    "count": ion_count
                }
            })
        else:
            print(f"[{run_name}] Note: omitting ion block for job '{job_name}' (ion_count <= 0).")

        sequences_list.extend(chains)
        
        row_seeds = _seeds_from_row(row, model_seeds)

        job_dict = {
            "name": job_name,
            "sequences": sequences_list,
            "dialect": "alphafoldserver",
            "version": 1,
        }
        if row_seeds:  # only include when non-empty
            job_dict["modelSeeds"] = row_seeds
        jobs.append(job_dict)

    out_dir = os.path.dirname(output_json)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_json, "w", encoding="utf-8") as out_f:
        json.dump(jobs, out_f, indent=2)

    print(f"[{run_name}] Wrote {len(jobs)} job entries to {output_json}")
