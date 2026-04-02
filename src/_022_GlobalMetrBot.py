#!/usr/bin/env python3
import os
import sys
import json
import csv
import re
import yaml

def load_config(cfg_path: str) -> dict:
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def extract_confidence_data(cfg_path: str):
    # --- Load config for ProtNames ---
    cfg = load_config(cfg_path)
    prot_names = cfg.get("ProtNames", {})

    # Derive sim_id from sheet or output_json
    sim_id = None
    sheet = str(cfg.get("sheet", ""))
    m = re.match(r"^(\d{4})", sheet)
    if m:
        sim_id = m.group(1)
    if not sim_id and "output_json" in cfg:
        m2 = re.match(r"^(\d{4})", os.path.basename(cfg["output_json"]))
        if m2:
            sim_id = m2.group(1)
    if not sim_id:
        print("ERROR: Could not derive sim_id from config.")
        sys.exit(1)

    # Set working dir = AF3_output/<SimID>
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    WD = os.path.join(project_root, "AF3_output", sim_id)
    if not os.path.isdir(WD):
        print(f"ERROR: Working directory {WD} not found.")
        sys.exit(1)

    print("Working directory is:", WD)
    job_folders = [d for d in os.listdir(WD) if os.path.isdir(os.path.join(WD, d))]
    print("Found job folders:", job_folders)

    all_rows = []
    all_columns = set()
    trivia_map_rows = []

    for job in job_folders:
        job_path = os.path.join(WD, job)

        # Expect job like "0026_01_something"
        m = re.match(rf"^{sim_id}_(\d{{2}})", job)
        trivia_name = None
        sample_letter = ""   ### NEW
        job_key = ""         ### NEW

        if m:
            job_idx = m.group(1)
            # Map A=1, B=2... → get key from ProtNames
            idx_int = int(job_idx)
            sample_letter = chr(ord("A") + idx_int - 1)   ### NEW
            trivia_name = prot_names.get(sample_letter)   # unchanged logic
            job_key = f"{sim_id}-{job_idx}"               ### NEW (matches 0084-10_ in CSV)

        for filename in os.listdir(job_path):
            if "summary_confidences" in filename:
                file_path = os.path.join(job_path, filename)
                model_index = os.path.splitext(filename.split('_')[-1])[0]

                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
                    continue

                row = {
                    "job_folder": job,
                    "job_key": job_key,                 ### NEW
                    "model_index": model_index,
                    "sample_letter": sample_letter,     ### NEW
                    "trivia_name": trivia_name or "",
                    "iptm": data.get("iptm"),
                    "ptm": data.get("ptm"),
                    "ranking_score": data.get("ranking_score"),
                    "fraction_disordered": data.get("fraction_disordered"),
                    "num_recycles": data.get("num_recycles"),
                }

                # chain_iptm
                for idx, val in enumerate(data.get("chain_iptm", [])):
                    row[f"chain_iptm_{idx}"] = val
                # pairwise iptm
                for i, rowlist in enumerate(data.get("chain_pair_iptm", [])):
                    for j, val in enumerate(rowlist):
                        row[f"pair_iptm_{i}_{j}"] = val
                # pairwise min pae
                for i, rowlist in enumerate(data.get("chain_pair_pae_min", [])):
                    for j, val in enumerate(rowlist):
                        row[f"pair_pae_min_{i}_{j}"] = val

                all_rows.append(row)
                all_columns.update(row.keys())

                # record mapping once per model
                trivia_map_rows.append({
                    "job_folder": job,
                    "job_key": job_key,               ### NEW
                    "model_index": model_index,
                    "sample_letter": sample_letter,   ### NEW
                    "trivia_name": trivia_name or ""
                })

    if not all_rows:
        print("No confidence-summary JSON files found.")
        return

    # Column order for model_confidences
    base_cols = [
        "job_folder", "job_key", "model_index", "sample_letter", "trivia_name",
        "iptm", "ptm", "ranking_score", "fraction_disordered", "num_recycles"
    ]
    dynamic_cols = sorted(all_columns - set(base_cols))
    fieldnames = base_cols + dynamic_cols

    # Write model_confidences.csv
    csv_file = os.path.join(WD, "model_confidences.csv")
    with open(csv_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            full_row = {col: row.get(col, "") for col in fieldnames}
            writer.writerow(full_row)
    print("Model confidence data extracted to:", csv_file)

    # Write model_trivia_map.csv (now richer)
    trivia_file = os.path.join(WD, "model_trivia_map.csv")
    with open(trivia_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["job_folder", "job_key", "model_index", "sample_letter", "trivia_name"]
        )
        writer.writeheader()
        for row in trivia_map_rows:
            writer.writerow(row)
    print("Model→trivia mapping written to:", trivia_file)


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].endswith((".yml", ".yaml")):
        print("Usage: python src/_022_GlobalMetrBot.py config/<run.yml>")
        sys.exit(1)
    extract_confidence_data(sys.argv[1])
