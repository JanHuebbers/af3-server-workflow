# src/R/04.00_RunMergeSetup.R

# ---- Load core packages (from Conda or install_r_packages.R)
source("src/R/03.01_LoadPackages.R")

# ---- Set global ggplot theme
source("src/R/03.02_ggPlotTheme.R")

# ---- Load helpers
## Convert triangular data to square matrix for "multicomp_letters".
source("src/R/tri_to_square.R")
## Create plot labels that are partly italic
source("src/R/ItalLabels.R")

# ────────────────────────────────────────────────────────────────────────────────
# After loading packages & theme, load the config
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop("Please provide config path as only argument")
source('src/R/05.01_LoadMergemergeConfig.R')

message("✅ Environment initialized: Packages loaded and ggplot2 theme applied.")