#!/usr/bin/env python3
# run by: python src/_002_batch_config.py

from pathlib import Path
import re

CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ---- run ordering (phylogeny) ----
CHAIN1 = ["AtMLO1.1", "AtMLO2.1"]
CHAIN2 = ["AtCAM2.1"]

START_RUNID = 254  # -> 0254
sheet_count = len(CHAIN1) * len(CHAIN2)  # int
print(sheet_count)
# ---- fixed settings ----
DEFAULT_ION = 0
MODEL_SEEDS = []  # keep empty (seeds come from Excel)
CX_SCRIPT = "Align_toA_cartoon_gradient.cxc"
ALIGNMENT_ALGO = "clustalo"

WIP1 = 8.0
HIP1 = 5.5
SEP = ","
ITALCHARS = 0

PROTNAMES = {
    "A": "1710", "B": "1711", "C": "1712", "D": "1701", "E": "1702", "F": "1703",
    "G": "1704", "H": "1705", "I": "1706", "J": "1707", "K": "1708", "L": "1709"
}

def mlo_axis_parts(mlo: str) -> tuple[str, str]:
    # AtMLO4 -> ("AtMLO", "4"); HvMlo1 -> ("HvMlo", "1")
    m = re.match(r"^AtMLO(\d+)$", mlo)
    if m:
        return "AtMLO", m.group(1)
    m = re.match(r"^HvMlo(\d+)$", mlo)
    if m:
        return "HvMlo", m.group(1)
    return mlo, ""

def exo_axis_parts(exo: str) -> tuple[str, str]:
    # AtEXO70A1 -> ("AtEXO70", "A1") etc.
    m = re.match(r"^AtEXO70(.+)$", exo)
    if m:
        return "AtEXO70", m.group(1)
    return exo, ""

def axis_title_expr(mlo: str, exo: str) -> str:
    mlo_tag, mlo_bold = mlo_axis_parts(mlo)
    exo_tag, exo_bold = exo_axis_parts(exo)

    if mlo_tag == "AtMLO":
        # AtMLO4 -> At MLO 4
        left = f'paste(italic("At"), plain("MLO"), bold("{mlo_bold}")'
    elif mlo_tag == "HvMlo":
        # HvMlo1 -> HvMlo   (NO "1" in AxisTitle, per your request)
        left = 'paste(plain("HvMlo")'
    else:
        left = f'paste(plain("{mlo}")'

    right = f'plain("-"), italic("At"), plain("EXO70"), bold("{exo_bold}"))'
    return f"{left}, {right}"

def facet_title_mlo(mlo: str) -> str:
    mlo_tag, mlo_bold = mlo_axis_parts(mlo)
    if mlo_tag == "AtMLO":
        return f'italic("At")*plain("MLO")*bold("{mlo_bold}")'
    if mlo_tag == "HvMlo":
        # same rule for facet title: HvMlo (no 1)
        return 'plain("HvMlo")'
    return f'plain("{mlo}")'

def facet_title_exo(exo: str) -> str:
    exo_tag, exo_bold = exo_axis_parts(exo)
    if exo_tag == "AtEXO70":
        return f'italic("At")*plain("EXO70")*bold("{exo_bold}")'
    return f'plain("{exo}")'

def dump_yaml(runid4: str, mlo: str, exo: str) -> str:
    sheet = f'{runid4}_1{mlo}_1{exo}'
    out_json = f'{sheet}.json'
    axis = axis_title_expr(mlo, exo)
    facA = facet_title_mlo(mlo)
    facB = facet_title_exo(exo)

    lines = []
    lines.append(f'# ======================= config/{sheet} =======================')
    lines.append(f'# Module 1: Excel to JSON')
    lines.append(f'sheet: "{sheet}"')
    lines.append(f'output_json: "{out_json}"')
    lines.append(f'default_ion: {DEFAULT_ION}')
    lines.append(f'modelSeeds: {MODEL_SEEDS}')
    lines.append('')
    lines.append(f'# Module 2: ChimeraX processing and confidence metrics extraction')
    lines.append(f'cx_script: {CX_SCRIPT}')
    lines.append('')
    lines.append(f'# MSA')
    lines.append(f'alignment_algo: {ALIGNMENT_ALGO}')
    lines.append(f'# ================================================================================')
    lines.append(f'WiP1: {WIP1}')
    lines.append(f'HiP1: {HIP1}')
    lines.append(f'sep: "{SEP}"')
    lines.append(f'ItalChars: {ITALCHARS}')
    lines.append('')
    lines.append('ProtNames:')
    for k in ["A","B","C","D","E","F","G","H","I","J","K","L"]:
        lines.append(f'  {k}: "{PROTNAMES[k]}"')
    lines.append('')
    lines.append('AxisTitle:')
    lines.append(f'  {axis}')
    lines.append('')
    lines.append('FacetTitles:')
    lines.append(f'  A: \'{facA}\'')
    lines.append(f'  B: \'{facB}\'')
    lines.append('')
    return "\n".join(lines)

def main():
    runid = START_RUNID
    for mlo in CHAIN1:
        for exo in CHAIN2:
            runid4 = f"{runid:04d}"
            sheet = f"{runid4}_1{mlo}_1{exo}"
            yml_path = CONFIG_DIR / f"Run{sheet}.yml"

            yml_path.write_text(dump_yaml(runid4, mlo, exo), encoding="utf-8")
            runid += 1

    print(f"✅ Wrote {sheet_count} config files to {CONFIG_DIR}/ (Run0254...Run0343)")

if __name__ == "__main__":
    main()