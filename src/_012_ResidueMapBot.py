#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01.2_ResidueMapBot.py

Create residue-map CSVs from AF3 input JSONs.

Supports:
• Single file whose root is a LIST of entries, each with:
    {
      "name": "0010-01_....",
      "sequences": [
         {"ion":{"ion":"CA","count":4}},
         {"proteinChain":{"sequence":"...","count":1}},
         {"proteinChain":{"sequence":"...","count":1}}
      ],
      ...
    }
  (ions ignored; proteinChain.count expanded; chains labeled A,B,C,...)
• Also works with older per-entry/per-file schemas.

Usage (no flags):
    python 01.2_ResidueMapBot.py <path/to/input.json>

Outputs:
    <input_dir>/residue_maps/<sim_id>/<sim_id>-<job>_residue_map.csv
Columns (semicolon-delimited):
    global_idx  chain_id  chain_pos  aa  pdb_resnum  token_chain_id
"""

from __future__ import annotations
import sys, os, json, csv
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional, Tuple

def _extract_sim_id(entry_name: str, default: str = "sim") -> str:
    """
    From names like '0010-01_...' return '0010'.
    If not present, return default.
    """
    # expect '<sim>-<job>_...'
    head = entry_name.split("_", 1)[0]
    sim = head.split("-", 1)[0]
    return sim if sim.isdigit() else default

def _rows_for_chain(chain_id: str, sequence: str,
                    pdb_resnums: Optional[Iterable[int]] = None,
                    token_chain_id: Optional[str] = None) -> List[Tuple[str,int,str,int,str]]:
    seq = (sequence or "").strip().replace(" ", "").upper()
    if not seq:
        return []
    if pdb_resnums is None:
        pdb_resnums = range(1, len(seq)+1)
    tci = token_chain_id or chain_id
    rows = []
    for i, (aa, resnum) in enumerate(zip(seq, pdb_resnums), start=1):
        rows.append((chain_id, i, aa, int(resnum), tci))
    return rows

def _expand_protein_chains_from_entry(entry: Dict[str, Any]) -> List[str]:
    """Return a list of protein sequences for one entry, expanding 'count'; ignore ions."""
    out: List[str] = []
    seqs = entry.get("sequences", [])
    if not isinstance(seqs, list):  # tolerate weird inputs
        return out
    for item in seqs:
        if not isinstance(item, dict):
            continue
        pc = item.get("proteinChain")
        if isinstance(pc, dict) and isinstance(pc.get("sequence"), str):
            cnt = int(pc.get("count", 1)) if str(pc.get("count", 1)).isdigit() else 1
            out.extend([pc["sequence"]] * max(1, cnt))
        # all ion blocks are ignored
    return out

def _write_residue_map_csv(sim_name: str, chains: List[str], out_root: Path) -> Path:
    """
    chains: list of sequences in chain order (A, B, C, ...)
    Writes a semicolon-delimited CSV with UTF-8 BOM (great for Excel in EU locales).
    Places the file under residue_maps/<sim_id>/.
    """
    # figure out sim_id and job label for filename
    sim_id = _extract_sim_id(sim_name)
    # filename base: prefer '<sim>-<job>' if present, else sim_name stem
    base = sim_name.split("_")[0]  # e.g., '0010-01'
    # ensure output dir: .../residue_maps/<sim_id>/
    out_dir = out_root / sim_id
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{base}_residue_map.csv"

    # Excel-friendly: semicolon delimiter + UTF-8 BOM
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=",")
        w.writerow(["global_idx","chain_id","chain_pos","aa","pdb_resnum","token_chain_id"])
        g = 1
        for ci, seq in enumerate(chains):
            chain_id = chr(ord("A") + ci)
            for (cid, pos, aa, resnum, tk) in _rows_for_chain(chain_id, seq, None, chain_id):
                w.writerow([g, cid, pos, aa, resnum, tk])
                g += 1
    return csv_path

def _process_list_root_file(path: Path, out_root: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected list-root JSON for this mode.")
    for entry in data:
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        name = str(entry["name"])
        chains = _expand_protein_chains_from_entry(entry)
        if not chains:
            print(f"[skip] {name}: no protein chains found.")
            continue
        out_dir = out_root
        csv_path = _write_residue_map_csv(name, chains, out_dir)
        print(f"[OK] {name} -> {csv_path}")

def _guess_and_process(path: Path) -> None:
    # default output folder next to the input file
    out_root = path.parent / "residue_maps"

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"[ERROR] Could not read JSON: {e}")

    if isinstance(obj, list):
        _process_list_root_file(path, out_root)
        return

    # Fallbacks for older shapes:
    # - {"chains": {...}} or {"chains":[...]} or {"sequences":[...]} etc.
    def extract_simple(obj: Any) -> List[Tuple[str, str]]:
        # returns list of (chain_id, sequence)
        res: List[Tuple[str,str]] = []
        if isinstance(obj, dict):
            if "chains" in obj and isinstance(obj["chains"], dict):
                for cid, meta in obj["chains"].items():
                    if isinstance(meta, dict) and "sequence" in meta:
                        res.append((str(cid), str(meta["sequence"])))
            elif "chains" in obj and isinstance(obj["chains"], list):
                for i, meta in enumerate(obj["chains"]):
                    if isinstance(meta, dict) and "sequence" in meta:
                        cid = meta.get("chain_id") or meta.get("id") or chr(ord("A")+i)
                        res.append((str(cid), str(meta["sequence"])))
            elif "sequences" in obj and isinstance(obj["sequences"], list):
                # treat as plain chain list
                ci = 0
                for meta in obj["sequences"]:
                    if isinstance(meta, dict) and "sequence" in meta:
                        cid = meta.get("chain_id") or meta.get("id") or chr(ord("A")+ci)
                        res.append((str(cid), str(meta["sequence"])))
                        ci += 1
        return res

    pairs = extract_simple(obj)
    if pairs:
        # use file stem as name
        name = path.stem
        # ensure order by chain label (A,B,C) if possible
        def _score(c): 
            return ord(c[0]) if len(c[0])==1 and c[0].isalpha() else 10**6
        pairs = sorted(pairs, key=_score)
        chains = [seq for _, seq in pairs]
        (path.parent / "residue_maps").mkdir(parents=True, exist_ok=True)
        out = _write_residue_map_csv(name, chains, out_root)
        print(f"[OK] {name} -> {out}")
        return

    raise SystemExit("[ERROR] Could not recognize chains/sequences in this file.")

def main():
    if len(sys.argv) != 2:
        print("Usage: python 01.2_ResidueMapBot.py <path/to/input.json>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"[ERROR] Not found: {p}")
        sys.exit(1)
    _guess_and_process(p)

if __name__ == "__main__":
    main()
