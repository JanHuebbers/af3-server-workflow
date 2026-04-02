#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_041_merge_MSA.py — Build merged MSAs (per chain) + alignment maps for Module 4 merge.

Goal
----
Given a merge YAML (same schema as _042_merge_GlobalMetr.py, plus alignment choice),
create per-chain MSAs across *runs* (one representative sequence per run_id per chain),
and write alignment maps mapping merged MSA positions to native residue indices.

Representative sequence rule (your requested default)
-----------------------------------------------------
For each run_id and chain, read the FIRST residue map found under:
    input/residue_maps/<run_id>/*_residue_map.csv
and derive the chain sequence from columns: chain_id, chain_pos, aa (sorted by chain_pos).

Alignment tool
--------------
Read from YAML:
    alignment_algo: auto|mafft|clustalo|muscle|none
or:
    alignment:
      tool: auto|...

Outputs
-------
Merge/<merge_name>/alignments/<effective_tool>/
  <merge_name>_<chain>_runs.fasta                (input sequences, one per run_id)
  <merge_name>_<chain>_runs_align_out.fasta      (aligned)
  <merge_name>_<chain>_align_map.csv             (merged MSA pos -> run_id + native res_idx)
  merge_msa_summary.json

Usage
-----
python src/_041_merge_MSA.py <MERGE_CFG>

Where <MERGE_CFG> is either:
  - NAME  -> uses config/NAME.yml
  - PATH  -> if endswith .yml/.yaml, uses that path
"""

from __future__ import annotations

import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
from contextlib import suppress

import pandas as pd
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

try:
    import yaml  # PyYAML
except Exception as e:
    raise SystemExit("Missing dependency 'PyYAML'. Install with: pip install pyyaml") from e

# Optional permissions helper
try:
    from perm_helper import ensure_writable, set_owner_and_perms
except Exception:
    def ensure_writable(_): pass
    def set_owner_and_perms(_p, mode=0o664): pass

RESMAPS_ROOT = Path("input") / "residue_maps"
MERGE_ROOT   = Path("Merge")

SUPPORTED = {"auto", "mafft", "clustalo", "muscle", "none"}

def norm_run_id(x) -> str:
    """
    Normalize run IDs to 4 digits:
      132, "132", "0132" -> "0132"
    """
    s = str(x).strip()
    if s.lower() in ("", "nan", "<na>", "none"):
        return ""
    if re.fullmatch(r"\d+", s):
        return s.zfill(4)
    m = re.search(r"(\d{3,4})", s)
    return m.group(1).zfill(4) if m else s

# ------------------------------ config helpers ------------------------------

def load_config(arg: str) -> dict:
    if arg.lower().endswith((".yml", ".yaml")):
        cfg_path = Path(arg)
    else:
        cfg_path = Path("config") / f"{arg}.yml"
    if not cfg_path.is_file():
        raise SystemExit(f"Config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}

def parse_runs(runs_val) -> List[str]:
    if runs_val is None:
        raise SystemExit("Config is missing 'runs'.")
    if isinstance(runs_val, (str, int)):
        runs_val = [runs_val]
    if not isinstance(runs_val, list):
        raise SystemExit("Config key 'runs' must be a list (or a scalar).")
    out: List[str] = []
    for x in runs_val:
        if isinstance(x, int):
            s = f"{x:04d}"
        else:
            s = str(x).strip()
            if s.isdigit() and len(s) < 4:
                s = f"{int(s):04d}"
        if not re.fullmatch(r"\d{4}", s):
            raise SystemExit(f"Invalid run_id in 'runs': {x!r} (expect 4 digits)")
        out.append(s)
    # de-dup preserve order
    seen = set()
    uniq = []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq

def get_alignment_algo(cfg: dict) -> str:
    algo = str(cfg.get("alignment_algo", (cfg.get("alignment") or {}).get("tool", "auto"))).lower()
    if algo not in SUPPORTED:
        raise SystemExit(f"alignment_algo must be one of {sorted(SUPPORTED)}")
    return algo


# ------------------------------ aligner selection ------------------------------

def _which(name: str) -> Optional[str]:
    return shutil.which(name)

def _pick_binary(algo: str) -> tuple[str, str]:
    algo = algo.lower()
    order = ["mafft", "clustalo", "muscle"] if algo == "auto" else [algo]
    for tool in order:
        candidates = {
            "mafft":    ["mafft"],
            "clustalo": ["clustalo", "clustal-omega", "clustalomega"],
            "muscle":   ["muscle"],
        }.get(tool, [])
        for c in candidates:
            p = _which(c)
            if p:
                return tool, p
    raise FileNotFoundError(
        f"No alignment binary found for '{algo}'. Tried: {', '.join(order)}. "
        f"Install e.g. `conda install -c bioconda mafft`."
    )

def _effective_algo_label(algo: str) -> str:
    if algo.lower() == "none":
        return "none"
    tool, _ = _pick_binary(algo)
    return tool


# ------------------------------ residue maps -> representative sequences ------------------------------

def _collect_residue_maps_for_run(run_id: str) -> List[Path]:
    d = RESMAPS_ROOT / run_id
    if not d.is_dir():
        raise FileNotFoundError(f"No residue maps at {d}")
    files = sorted(p for p in d.glob("*_residue_map.csv") if p.is_file())
    if not files:
        raise FileNotFoundError(f"No *_residue_map.csv under {d}")
    return files

@dataclass
class RunChainSeq:
    run_id: str
    chain: str
    seq: str
    res_index_list: List[int]  # native residue indices (chain_pos)

def _load_representative_sequences(runs: List[str]) -> Dict[str, List[RunChainSeq]]:
    """
    Returns dict: chain -> list of RunChainSeq (one per run_id).
    Uses the FIRST residue_map.csv file found under input/residue_maps/<run_id>/.
    """
    chain_to_records: Dict[str, List[RunChainSeq]] = {}
    for run_id in runs:
        run_id = norm_run_id(run_id)
        files = _collect_residue_maps_for_run(run_id)
        rep = files[0]
        df = pd.read_csv(rep)
        required = {"chain_id", "chain_pos", "aa"}
        if not required.issubset(df.columns):
            raise KeyError(f"{rep} missing required columns (need {sorted(required)}).")
        for chain in sorted(df["chain_id"].unique()):
            sub = df[df["chain_id"] == chain].copy()
            sub = sub.sort_values("chain_pos", kind="mergesort")
            seq = "".join(sub["aa"].astype(str).str.upper().tolist())
            idxs = sub["chain_pos"].astype(int).tolist()
            chain_to_records.setdefault(str(chain), []).append(
                RunChainSeq(run_id=run_id, chain=str(chain), seq=seq, res_index_list=idxs)
            )
    return chain_to_records


# ------------------------------ write FASTA + run alignment ------------------------------

def _write_per_chain_fastas(merge_name: str,
                            chain_to_records: Dict[str, List[RunChainSeq]],
                            out_dir: Path) -> Dict[str, Path]:
    """
    Write one FASTA per chain:
      Merge/<merge_name>/alignments/<tool>/<merge_name>_<chain>_runs.fasta

    Headers:
      run=<run_id>|chain=<chain>|len=<len>
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Path] = {}
    for chain, recs in chain_to_records.items():
        records: List[SeqRecord] = []
        for rec in recs:
            header = f"run={norm_run_id(rec.run_id)}|chain={chain}|len={len(rec.seq)}"
            records.append(SeqRecord(Seq(rec.seq), id=header, description=""))
        fp = out_dir / f"{merge_name}_{chain}_runs.fasta"
        ensure_writable(fp)
        with open(fp, "w", encoding="utf-8") as fh:
            SeqIO.write(records, fh, "fasta")
        set_owner_and_perms(fp)
        result[chain] = fp
    return result

def _run_alignment_to_fasta(fasta_in: Path, algo: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    aln_out = out_dir / f"{fasta_in.stem}_align_out.fasta"

    nseq = sum(1 for _ in SeqIO.parse(str(fasta_in), "fasta"))
    if nseq <= 1 or algo.lower() == "none":
        shutil.copy2(fasta_in, aln_out)
        set_owner_and_perms(aln_out)
        return aln_out

    tool, exe = _pick_binary(algo)

    if tool == "mafft":
        cmd = [exe, "--auto", str(fasta_in)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"MAFFT failed ({proc.returncode}). STDERR:\n{proc.stderr}")
        aln_out.write_text(proc.stdout, encoding="utf-8")
        set_owner_and_perms(aln_out)
        return aln_out

    if tool == "clustalo":
        cmd = [exe, "-i", str(fasta_in), "-o", str(aln_out), "--force", "--outfmt=fasta"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Clustal Omega failed ({proc.returncode}). STDERR:\n{proc.stderr}")
        set_owner_and_perms(aln_out)
        return aln_out

    if tool == "muscle":
        cmd_v5 = [exe, "-align", str(fasta_in), "-output", str(aln_out)]
        proc = subprocess.run(cmd_v5, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            set_owner_and_perms(aln_out)
            return aln_out
        cmd_v3 = [exe, "-in", str(fasta_in), "-out", str(aln_out)]
        proc2 = subprocess.run(cmd_v3, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc2.returncode != 0:
            raise RuntimeError(
                "MUSCLE failed.\n"
                f"v5 STDERR:\n{proc.stderr}\n"
                f"v3 STDERR:\n{proc2.stderr}\n"
            )
        set_owner_and_perms(aln_out)
        return aln_out

    raise ValueError(f"Unsupported tool: {tool}")


# ------------------------------ alignment map ------------------------------

def _parse_header_run_chain(header: str) -> Tuple[Optional[str], Optional[str]]:
    run_id = chain = None
    for part in header.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k == "run":
                run_id = norm_run_id(v)
            elif k == "chain":
                chain = v
    return run_id, chain

def _build_alignment_map_for_chain(aligned_fasta: Path,
                                   chain_records: List[RunChainSeq],
                                   out_csv: Path) -> None:
    """
    Emit CSV with columns:
      chain, aln_pos, run_id, res_idx, aa_aln

    res_idx is native chain_pos (1-based), or NA if gap.
    """
    residx: Dict[Tuple[str, str], List[int]] = {
        (norm_run_id(rec.run_id), rec.chain): rec.res_index_list for rec in chain_records
    }
    records = list(SeqIO.parse(str(aligned_fasta), "fasta"))

    state: Dict[Tuple[str, str], Dict[str, object]] = {}
    for rec in records:
        run_id, chain = _parse_header_run_chain(rec.id)
        run_id = norm_run_id(run_id)
        key = (run_id, chain)
        if key not in residx:
            raise KeyError(f"Aligned header {rec.id} not found among input sequences.")
        state[key] = {"aln": str(rec.seq), "cursor": 0, "run_id": norm_run_id(run_id), "chain": chain}

    rows: List[Dict[str, object]] = []
    aln_len = max(len(s["aln"]) for s in state.values())
    for i in range(aln_len):
        for key, st in state.items():
            run_id, chain = st["run_id"], st["chain"]
            aa = st["aln"][i] if i < len(st["aln"]) else "-"
            if aa == "-":
                res_idx = None
            else:
                cur = int(st["cursor"])
                li = residx[(run_id, chain)]
                res_idx = li[cur] if cur < len(li) else None
                st["cursor"] = cur + 1
            rows.append({
                "chain": chain,
                "aln_pos": i + 1,
                "run_id": run_id,
                "res_idx": res_idx,
                "aa_aln": aa
            })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    ensure_writable(out_csv)
    df_out = pd.DataFrame(rows)
    df_out["aln_pos"] = pd.to_numeric(df_out["aln_pos"], errors="coerce").astype("Int64")
    df_out["res_idx"] = pd.to_numeric(df_out["res_idx"], errors="coerce").astype("Int64")
    df_out.to_csv(out_csv, index=False)
    set_owner_and_perms(out_csv)


# ------------------------------ orchestration ------------------------------

@dataclass
class Summary:
    merge_name: str
    config_path: str
    algo: str
    effective_algo: str
    outputs: Dict[str, Dict[str, str]]  # chain -> {msa_in, msa_out, map_csv}
    runs: List[str]
    binaries_checked: List[str]

def run_from_config(cfg_path_or_name: str) -> Summary:
    cfg = load_config(cfg_path_or_name)
    merge_name = str(cfg.get("merge_name") or "").strip()
    if not merge_name:
        raise SystemExit("Config is missing 'merge_name'.")
    runs = parse_runs(cfg.get("runs"))
    algo = get_alignment_algo(cfg)
    effective = _effective_algo_label(algo)

    out_dir = MERGE_ROOT / merge_name / "alignments" / effective
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[merge_MSA] merge_name={merge_name}  runs={len(runs)}  algo={algo}  effective={effective}")

    # Collect representative sequences (one per run_id per chain)
    chain_to_records = _load_representative_sequences(runs)
    chains = sorted(chain_to_records.keys())
    if not chains:
        raise RuntimeError("No chains discovered across runs.")

    # Write FASTA inputs per chain
    fasta_inputs = _write_per_chain_fastas(merge_name, chain_to_records, out_dir)

    # Diagnostics: which binaries were found
    bins_checked: List[str] = []
    if algo != "none":
        for nm in ["mafft", "clustalo", "clustal-omega", "clustalomega", "muscle"]:
            p = _which(nm)
            if p:
                bins_checked.append(f"{nm}={p}")

    outputs: Dict[str, Dict[str, str]] = {}

    for chain in chains:
        fasta_in = fasta_inputs[chain]
        print(f"[merge_MSA] Aligning chain {chain} from {fasta_in} …")
        msa_out = _run_alignment_to_fasta(fasta_in, algo, out_dir)
        map_csv = out_dir / f"{merge_name}_{chain}_align_map.csv"
        _build_alignment_map_for_chain(msa_out, chain_to_records[chain], map_csv)
        outputs[chain] = {
            "msa_in": str(fasta_in),
            "msa_out": str(msa_out),
            "map_csv": str(map_csv),
        }
        print(f"[merge_MSA]  → MSA OUT: {msa_out}")
        print(f"[merge_MSA]  → Map    : {map_csv}")

    summary = Summary(
        merge_name=merge_name,
        config_path=str(Path(cfg_path_or_name)),
        algo=algo,
        effective_algo=effective,
        outputs=outputs,
        runs=runs,
        binaries_checked=bins_checked,
    )
    summary_path = out_dir / "merge_msa_summary.json"
    ensure_writable(summary_path)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(asdict(summary), fh, indent=2)
    set_owner_and_perms(summary_path)

    print(f"[merge_MSA] Done. Summary: {summary_path}")
    return summary

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python src/_041_merge_MSA.py <MERGE_CFG>")
        sys.exit(1)
    run_from_config(sys.argv[1])

if __name__ == "__main__":
    main()