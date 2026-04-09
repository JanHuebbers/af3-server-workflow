# af3-server-workflow
End-to-end workflow for preparing AlphaFold 3 server inputs and analyzing returned structures, confidence metrics, and for carrying out comparative merges of selected prediction runs.

## Table of contents
- [Overview](#overview)
- [Features](#features)
- [Notes](#notes)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Workflow modules](#workflow-modules)
  - [I Excel to JSON](#i-excel-to-json)
  - [II ChimeraX visualization and confidence metric extraction](#ii-chimerax-visualization-and-confidence-metric-extraction)
  - [III Confidence metric visualization via R](#iii-confidence-metric-visualization-via-r)
  - [IV Merge simulations](#iv-merge-simulations)
  - [V Merge merge (under construction)](#v-merge-merge-under-construction)
  - [VI Align R plots](#vi-align-r-plots)
- [Typical workflow](#typical-workflow)
- [Status](#status)

## Overview
`af3-server-workflow` is a modular pipeline for preparing AlphaFold 3 prediction runs, processing returned predictions, extracting and visualizing confidence metrics, and comparing results across multiple runs or merged simulation sets. It is designed for Ubuntu _via_ WSL on Windows.
## Features
- Excel-based preparation of AF3 input definitions
- JSON generation for AlphaFold 3 submission
- Residue map and sequence alignment generation
- ChimeraX-based structure visualization
- Confidence metric extraction from AF3 outputs
- R-based plotting and comparative analysis
- Merge workflows across runs
- Planned merge-of-merges analysis
- Alignment of exported ggplot `.rds` files for figure assembly
## Notes
- This workflow currently assumes a Linux-style environment.
- Examples are written for Ubuntu on WSL.
- ChimeraX paths may need manual adjustment in config/global.yml.
- Some scripts may require ownership or execution-permission fixes depending on your setup  
# Repository layout
```text
af3-server-workflow/
├── AF3_output
├── ChimeraX
├── Merge
├── Mergemerge
├── Metrics_plots
├── README.md
├── af3_input.xlsx
├── config
├── environment.yml
├── input
├── sequences
├── setup_af3_folders.sh
└── src
```
## Requirements
### System
- Linux environment
- Conda, Miniconda, or Mamba
- Python
- R 
- System libraries for R package setup (e.g., cmake, cairo, pkg-config)
- System/compiler toolchain for selected R packages
- ChimeraX (1.10.1)

**Recommended environment: Ubuntu or Ubuntu via WSL on Windows.**

## Installation
1. Clone the repository
```bash
git clone <your-repository-url>
cd af3-server-workflow
```
2. Configure Conda channels
To avoid version conflicts when installing R, compilers, and Bioconductor packages:
```bash
conda config --add channels conda-forge
conda config --set channel_priority strict
```
3. Create or update the environment
First-time setup:
```bash
conda env create -f environment.yml
```
If the environment already exists:
```bash
conda env update -n af3_env -f environment.yml --prune
```
4. Install required packages
Alignment tools
```bash
conda install -c bioconda mafft clustalo muscle
```
Excel writer backend
```bash
conda install -n af3_env -c conda-forge xlsxwriter
```
mmCIF geometry extraction
```bash
conda install -c conda-forge gemmi
```
R-related system dependencies
```bash
sudo apt update
sudo apt install -y \
  cmake \
  libudunits2-dev \
  libcairo2-dev \
  libexpat1-dev \
  pkg-confi
```
Compilers for R packages
```bash
conda install -n af3_env -c conda-forge compilers
```
5. Activate the environment
```bash
conda activate af3_env
```
6. Install R packages
```bash
Rscript src/R/install_r_packages.R
```
7. Create missing folders
```bash
chmod +x setup_af3_folders.sh
./setup_af3_folders.sh
```
8. Verify ChimeraX accessibility
Example for WSL:
```bash
"/mnt/c/Program Files/ChimeraX 1.10.1/bin/ChimeraX-console.exe" --version
```
Add the correct ChimeraX path to `./config/global.yml`.

9. Fonts on WSL
For the plotting scripts to render correctly, the DejaVu Sans `.ttf` files must be available inside WSL under:
```bash
/usr/share/fonts/truetype/dejavu/
```
At minimum, these files should be present:
- DejaVuSans.ttf
- DejaVuSans-Bold.ttf
- DejaVuSans-Oblique.ttf
- DejaVuSans-BoldOblique.ttf
If the files are missing, copy them into WSL and refresh the font cache:
```bash
sudo mkdir -p /usr/share/fonts/truetype/dejavu
sudo fc-cache -f -v
```
## Workflow modules
### I Excel to JSON
#### Activate the Conda environment:
```bash
conda activate af3_env
```
#### Prepare your input sheet in your Excel input file (`af3_input.xlsx`)
- Create a new sheet and update the SimID column and Sheet name
- Add names for your protein chains to the Chain_name columns
- Prepare FASTA files for chains and link FASTA files to Chain_seq columns via right click → link
- Update Ions or other columns if applicable. Note that for ions only "Ions" (no ions) or "CA" to calcium ions are supported.
- Allowed characters for chain names:
  - letters
  - numbers
  - spaces
  - dashes
  - underscores
  - colons
#### Batch generation of `.xlsx` input sheets
Modify parameters in _001_batch_excel.yml and execute:
```bash
python src/_001_batch_excel.py
```
Afterwards, copy sheets from `af3_input_temp.xlsx` to `af3_input.xlsx`.

#### Update `config.yml`
- Rename an existing `config.yml` in `af3_workflow/config` using the name of your input Excel sheet
- Change YAML header and sheet name
- Update output_json directory
- If applicable, change default_ion count or modelSeeds
- Provide the ChimeraX script for structure visualization under cx_script. ChimeraX `.cxc` files live under `af3_workflow/ChimeraX/cx_scripts`.
- Adjust alignment algorithm if necessary
- Adjust height and width for plotting in module 3 (WiP1 and HiP1)
- Update protein names and x-axis title for P1
  
#### Batch generation of `.yml` config files
Modify parameters in _002_batch_config.yml and execute:
```bash
python src/_002_batch_config.py
```
#### Run module 1
Change into the project folder
```bash
cd ~/projects/af3_workflow/
```
Generate JSON, residue map, and alignment for all or single runs
All
```bash
python src/_010_run_create_input.py
```
Single
```bash
python src/_010_run_create_input.py Run0001_2026-01-01_test
```
Batch
Modify parameters in batch_module1.sh and execute from the working directory:
```bash
./src/shell/batch_module1.sh
```
#### Verify output
- Check `input/` for the newly created JSON files
- Feed these JSONs into your AF3 batch runner, for example the AlphaFold 3 server
- Download AF3 output, extract files, and copy them into the project folder

Example:
```bash
sudo chown -R <user>:<user> ./AF3_output/0001
rsync -a --no-xattrs /mnt/c/Users/User/Downloads/folds_2026_01_01_00_01/ ~/projects/af3-server-workflow/AF3_output/0001/
```
---
### II ChimeraX visualization and confidence metric extraction
#### Run the wrapper for module 2
This is exemplary code for test run `0001`.
```bash
python src/_020_run_chimera_confmetr.py Run0001_2026-01-01_test
```
**Useful flags:**
- `--avg-only` to skip writing heavy per-model `ContactProbs` and `PAE` sheets
- `--yes` to answer all prompts with `y`
---
### III Confidence metric visualization via R
#### Run the wrapper for module 3
```bash
python src/_030_run_plot_module.py Run0001_2026-01-01_test
```
---
### IV Merge simulations
#### Run the wrapper
Runs all scripts in module 4. Use `--yes` to skip prompts.
```bash
export MERGENAME=MyMerge
python src/_040_run_merge_module.py Merge${MERGENAME} --yes
```
#### Run step-wise
##### Merge MSAs
Builds a merged multiple sequence alignment (MSA) per chain across selected `run_id`s and writes an alignment map.
```bash
python src/_041_merge_MSA.py Merge${MERGENAME}
```
##### Merge confidence metrics `.csv` files from AF3 output folders
```bash
python src/_042_merge_GlobalMetr.py Merge${MERGENAME}
```
##### Merge per-residue metrics `.xlsx` files from AF3 output folders
Creates a merged `minScoresperMSA_merged.xlsx` for the merge, where each run contributes one column set per chain containing mean per-residue metrics averaged across seeds/jobs within that run.
```bash
python src/_043_merge_MinMetr.py Merge${MERGENAME}
```
##### Create plots to compare metrics across various runs
```bash
python src/_044_create_merge_plots.py Merge${MERGENAME}
```
#### Selection by `--include`
- Include-only mode is controlled by the boolean CLI flag `--include`.
- When `--include` is set, the script only keeps rows belonging to the specified `include` jobs. If you list models for a given `job_id`, it keeps only those model indices. If a `job_id` has no models specified, all models for that job are included.
```bash
python src/_042_merge_GlobalMetr.py Merge${MERGENAME} --include
```
Config examples for the use of `--include`
List of dicts:
```yaml
merge_name: "MyMerge"
runs: ["0135", "0136", "0137"]

include:
  - job_id: "0135-01"
    model: []
  - job_id: "0136-02"
    model: [0, 4]
```
Parallel lists:
```yaml
merge_name: "MyMerge"
runs: ["0049", "0050"]

include:
  job_id: ["0135-01", "0135-02"]
  model: [[0, 1], []]
```
---
### V Merge merge (under construction)
Available:
- Script 052: combine global confidence metrics `.csv` tables
- Script 054: create visuals to compare these metrics across merged runs
Planned scripts:
- Script 051: create MSAs across different merges
- Script 053: combine per-residue metrics and alignments
Examples:
```bash
export MERGENAME=MyMergemerge
```
```bash
python src/_052_mergemerge_GlobalMetr.py Mergemerge${MERGENAME}
```
```bash
python src/_054_mergemerge_plots.py Mergemerge${MERGENAME}
```
---
### VI Align R plots
Use `align_rds_plots.R` to align the panel and axes of multiple ggplot objects saved as `.rds` files.
```bash
Rscript ./src/R/align_rds_plots.R <rds_dir> [width_cm] [height_cm]
```
- `<rds_dir>`: directory containing the `.rds` plots
- `[width_cm]` and `[height_cm]` are optional overrides
#### Examples
Use script defaults:
```bash
Rscript ./src/R/align_rds_plots.R ./Mergemerge/MyMerge/AlignHeat_sims/ChainA
```
Force all plots to `10 × 6` cm:
```bash
Rscript ./src/R/align_rds_plots.R ./Merge/MyMerge/2026-01-01/ 10.0 6.0
```
Keep per-plot widths, but force height to `6` cm:
```bash
Rscript ./src/R/align_rds_plots.R ./Merge/MyMerge/2026-01-01/ NA 6.0
```
**For each plot, the script computes size in this order per dimension:**
- Per-plot default based on the file name
- If no rule matches, global fallback = `16 × 6` cm
- If a CLI value is given:
- numeric → override for all plots
- `NA` → no override

**What it does**
- Loads all `.rds` files in `<rds_dir>` that are ggplot objects
- Calls `align_plots(data = plots, align = "hv", axis = "ytbr", greedy = TRUE)` once on the full set
- Writes aligned plots to `<rds_dir>/aligned/` as:
  - one `<stem>_aligned.rds` per input plot
  - one `<stem>_aligned.svg` per input plot

The aligned SVGs have matching panel and axis geometry, so they can be combined cleanly in Inkscape, Illustrator, or PowerPoint.

## Typical workflow
- Set up the environment
- Prepare `af3_input.xlsx`
- Create or update the matching YAML config
- Generate AF3 JSON input files
- Submit jobs to your AF3 execution backend
- Copy returned AF3 outputs into `AF3_output/`
- Run module 2 for metrics and structure visualization
- Run module 3 for plots
- Run module 4 to compare runs
- Run module 5 to compare merged runs
- Optionally use module 6 to align exported ggplot objects
## Status
- Module 1: active
- Module 2: active
- Module 3: active
- Module 4: active
- Module 5: under construction
- Module 6: active


