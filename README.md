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
- Here, ChimeraX 1.10.1 is used but newer versions will probably also work.
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
git clone https://github.com/JanHuebbers/af3-server-workflow.git
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
4. Activate the environment
   ```bash
   conda activate af3_env
   ```
5. Install additional dependencies

   **Sequence alignment tools**
   ```bash
   conda install -c bioconda mafft clustalo muscle
   ```

   **Python packages for Excel export and mmCIF processing**
   ```bash
   conda install -c conda-forge xlsxwriter gemmi
   ```

   **Ubuntu system utilities and R-related system dependencies**
   ```bash
   sudo apt update
   sudo apt install -y \
     unzip \
     cmake \
     libudunits2-dev \
     libcairo2-dev \
     libexpat1-dev \
     pkg-config
   ```

   **Compilers for R packages**
   ```bash
   conda install -c conda-forge compilers
   ```
6. Install R packages
   ```bash
   Rscript src/R/install_r_packages.R
   ```

   Verify that the required executables are accessible within the activated environment:
   ```bash
   command -v python Rscript mafft clustalo muscle unzip
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

**Note:** When running ChimeraX via WSL, warnings related to OSMesa or offscreen rendering may occur. These warnings are not necessarily fatal. Check the ChimeraX exit status, log messages, and generated session files to verify successful execution.

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
Modify parameters in _001_batch_excel.py and execute:
```bash
python src/_001_batch_excel.py
```
Afterwards, copy sheets from `af3_input_temp.xlsx` to `af3_input.xlsx`.

#### Update the run configuration (`.yml`)
- Copy an existing run configuration in `config/` and rename it according to your new simulation (e.g., `Run0001_2026-01-01_test.yml`).
- Set the `sheet` key to the exact name of the corresponding worksheet in `af3_input.xlsx`.
- Set `output_json` to the desired AF3 input JSON filename. The file will be generated under `input/`.
- If applicable, adjust `default_ion` and `modelSeeds`.
- Specify the ChimeraX script for structure visualization using `cx_script`. ChimeraX `.cxc` files are located under `ChimeraX/cx_scripts/`.
- Adjust the sequence alignment algorithm (`alignment_algo`) if necessary.
- Adjust the height and width for plotting in Module III (`WiP1` and `HiP1`).
- Update protein names and plot labels as required.

Example:
```yaml
sheet: "0001_2026-01-01_test"
output_json: "0001_2026-01-01_test.json"
default_ion: 0
modelSeeds: []
cx_script: Align_toA_cartoon_gradient.cxc
alignment_algo: clustalo
```

**Note:** The command-line argument passed to the Module I wrapper identifies the YAML configuration file, whereas the `sheet` key within that configuration identifies the Excel worksheet. These names do not have to be identical.

Before running Module I, ensure that the specified Excel worksheet exists and that all FASTA file paths are valid.
  
#### Batch generation of `.yml` config files
Modify parameters in _002_batch_config.py and execute:
```bash
python src/_002_batch_config.py
```
#### Run module 1
Change into the project folder
```bash
cd ~/projects/af3-server-workflow/
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

**Important:** Ensure that the extracted AF3 Server results retain their individual job directories. The expected directory structure is `AF3_output/<SimID>/<JobName>/`, with the model CIF and confidence JSON files located inside each job directory. Job directory names must not start with `fold_`. Do not extract individual job archives directly into `AF3_output/<SimID>/`.

Example:
```bash
sudo chown -R <user>:<user> ./AF3_output/0001
rsync -a --no-xattrs /mnt/c/Users/User/Downloads/folds_2026_01_01_00_01/ ~/projects/af3-server-workflow/AF3_output/0001/
```
---
### II ChimeraX visualization and confidence metric extraction
#### Run the wrapper for module 2
Before running Module II, ensure that:
- Module I has completed successfully.
- AF3 Server results have been extracted into correctly named individual job directories.
- Each job directory contains the corresponding model CIF files, full-data JSON files, and summary-confidence JSON files.
- The ChimeraX executable and selected `.cxc` script are correctly specified in the configuration files.

Example for simulation `0001`:
```bash
python src/_020_run_chimera_confmetr.py Run0001_2026-01-01_test
```

Optional flags:
- `--avg-only`: Reduces output size by omitting individual per-model contact probability, PAE, and geometric distance matrices while retaining the corresponding averaged matrices. This option is passed to the downstream per-residue metric scripts.
- `--yes`: Automatically answers all interactive prompts with `y`, including prompts to overwrite existing outputs. Aliases: `--assume-yes` and `--non-interactive`.

Example:
```bash
python src/_020_run_chimera_confmetr.py Run0001_2026-01-01_test --avg-only --yes
```

**Warning:** The `--yes` flag may automatically confirm the deletion and regeneration of existing analysis outputs.

#### Verify output
After running Module II, verify that the expected outputs have been generated:
- ChimeraX session files (`.cxs`) under `ChimeraX/<SimID>/`.
- `AF3_output/<SimID>/model_confidences.csv`.
- `AF3_output/<SimID>/model_trivia_map.csv`.
- Per-residue metric files within the individual job directories.
- `AF3_output/<SimID>/minScoresperMSA.xlsx`.
- Per-chain CSV files under `AF3_output/<SimID>/csv/`.

Review the corresponding log file under `src/logs/` for errors or warnings.

**Important:** Individual processing steps may fail without terminating the entire wrapper. Always verify that the required output files exist before proceeding to Module III.
---
### III Confidence metric visualization via R
#### Run the wrapper for module 3
Before running Module III, ensure that Module II has successfully generated the global and per-residue confidence metric files and that all required R packages have been installed.

Example:
```bash
python src/_030_run_plot_module.py Run0001_2026-01-01_test
```

The wrapper executes the following R scripts:
- `03.04_P1_ptmiptm_combi.R`
- `03.05_P2_ptmtoiptm.R`
- `03.06_P3_heatmap.R`

#### Verify output
Check the generated plots under `Metrics_plots/`. The plotting scripts generate:
- `.svg` files for visualization and figure preparation.
- `.rds` files containing ggplot objects for downstream plot alignment (Module VI).

**Note:** If plotting fails because of missing input files, verify the outputs and logs of Module II before troubleshooting the R scripts.
---
### IV Merge simulations
This module enables comparative analysis of multiple AF3 simulation runs by merging sequence alignments, global confidence metrics, and per-residue metrics.

Before running Module IV, ensure that Modules I and II have been completed successfully for all selected simulation runs.

#### Run the wrapper
Runs all scripts in Module IV in sequence:
- `_041_merge_MSA.py`
- `_042_merge_GlobalMetr.py`
- `_043_merge_MinMetr.py`
- `_044_create_merge_plots.py`

```bash
export MERGENAME=MyMerge
python src/_040_run_merge_module.py Merge${MERGENAME}
```

Optional flags:
- `--yes`: Automatically confirms all interactive prompts, including prompts to delete and regenerate existing outputs.
- `--fail-fast`: Terminates execution if a processing step fails (default behavior).
- `--continue-on-error`: Continues with subsequent processing steps if an individual step fails.

For non-interactive execution:
```bash
python src/_040_run_merge_module.py Merge${MERGENAME} --yes
```

**Warning:** Use `--yes` with caution when reprocessing existing merges, as previously generated outputs may be deleted automatically.

#### Run step-wise
##### Merge MSAs
Builds a merged multiple sequence alignment (MSA) per chain across selected `run_id`s and writes an alignment map.

```bash
python src/_041_merge_MSA.py Merge${MERGENAME}
```

##### Merge confidence metrics `.csv` files from AF3 output folders
Combines the `model_confidences.csv` files from the selected simulation runs into a single table.

```bash
python src/_042_merge_GlobalMetr.py Merge${MERGENAME}
```

##### Merge per-residue metrics from AF3 output folders
Reads per-chain `.csv` files or, if unavailable, the corresponding `minScoresperMSA.xlsx` files.

Creates a merged `minScoresperMSA_merged.xlsx` for the merge, where each run contributes one column set per chain containing mean per-residue metrics averaged across seeds/jobs within that run. The metrics are mapped onto the merged MSA.

```bash
python src/_043_merge_MinMetr.py Merge${MERGENAME}
```

##### Create plots to compare metrics across various runs
```bash
python src/_044_create_merge_plots.py Merge${MERGENAME}
```

Optional flags:
- `--script`: Execute an additional R plotting script. Can be specified multiple times.
- `--fail-fast`: Terminates execution if a plotting script fails (default behavior).
- `--continue-on-error`: Continues with subsequent plotting scripts if an individual script fails.

#### Selection by `--include`
The global confidence metrics merging script supports selective inclusion of individual jobs and models.
- Include-only mode is controlled by the boolean CLI flag `--include`.
- When `--include` is set, the script only keeps rows belonging to the jobs specified in the `include` section of the YAML configuration.
- If model indices are specified for a given `job_id`, only those models are included.
- If a `job_id` has no model indices specified, all models for that job are included.
- The `--include` flag applies to the global confidence metrics merging script.

```bash
python src/_042_merge_GlobalMetr.py Merge${MERGENAME} --include
```

Config examples for the use of `--include`:

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
runs: ["0135", "0136"]

include:
  job_id: ["0135-01", "0135-02"]
  model: [[0, 1], []]
```

#### Verify output
Check that the following outputs have been generated under `Merge/<merge_name>/`:
- `alignments/`: Merged MSAs and alignment maps.
- `model_confidences.csv`: Merged global confidence metrics.
- `minScoresperMSA_merged.xlsx`: Merged per-residue metrics mapped onto the merged MSAs.
- Dated directories containing comparative plots.

If `--continue-on-error` was used, review the reported execution status and verify that all expected outputs have been generated before proceeding to Module V.

---
### V Merge merge (under construction)
This module enables comparative analysis of multiple merges generated by Module IV.

#### Currently implemented scripts
- Script 052 (`_052_mergemerge_GlobalMetr.py`): Combine global confidence metrics `.csv` tables from multiple merges.
- Script 054 (`_054_mergemerge_plots.py`): Create plots to compare these metrics across merges.

#### Planned scripts
- Script 051: Create MSAs across different merges.
- Script 053: Combine per-residue metrics and map them onto shared MSAs.

#### Prepare the configuration
Create a merge-of-merges configuration file in `config/`, for example `MergemergeMyMergemerge.yml`, and specify the merges to be included.

Example:
```yaml
merge_name: "MyMergemerge"
merges:
  - "MyMerge1"
  - "MyMerge2"
```

Each selected merge must contain a `model_confidences.csv` file under `Merge/<merge_name>/`.

#### Merge global confidence metrics
Combines the global confidence metrics from the selected merges and adds a `source_merge` column to retain information on the origin of each entry.

```bash
export MERGENAME=MyMergemerge
python src/_052_mergemerge_GlobalMetr.py Mergemerge${MERGENAME}
```

The combined confidence metrics are written to:
```text
Mergemerge/<merge_name>/model_confidences.csv
```

The optional `--out` argument can be used to specify an alternative output file.

#### Create plots to compare metrics across various merges
```bash
python src/_054_mergemerge_plots.py Mergemerge${MERGENAME}
```

Optional flags:
- `--script`: Execute an additional R plotting script. Can be specified multiple times.
- `--fail-fast`: Terminates execution if a plotting script fails (default behavior).
- `--continue-on-error`: Continues with subsequent plotting scripts if an individual script fails.

#### Verify output
Check that the merged global confidence metric table and comparative plots have been generated under `Mergemerge/<merge_name>/`.

**Note:** Module V is currently under construction. The merging and comparative visualization of per-residue metrics across merges are not yet implemented.

---
### VI Align R plots
Use `align_rds_plots.R` to align the panel and axes of multiple ggplot objects saved as `.rds` files.

```bash
Rscript ./src/R/align_rds_plots.R <rds_dir> [width_cm] [height_cm]
```

- `<rds_dir>`: Directory containing the `.rds` plots.
- `[width_cm]` and `[height_cm]`: Optional overrides for plot dimensions.

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

**For each plot, the script determines the size in the following order per dimension:**
- Per-plot default based on the file name.
- If no rule matches, global fallback = `16 × 6` cm.
- If a CLI value is given:
  - Numeric → override for all plots.
  - `NA` → no override.

**What it does**
- Loads all `.rds` files in `<rds_dir>` that are ggplot objects.
- Calls `align_plots(data = plots, align = "hv", axis = "ytbr", greedy = TRUE)` once on the full set.
- Writes aligned plots to `<rds_dir>/aligned/` as:
  - One `<stem>_aligned.rds` per input plot.
  - One `<stem>_aligned.svg` per input plot.

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
# Acknowledgements
Special thanks goes to Aurélien and Pablo for testing this workflow and keeping the project alive!