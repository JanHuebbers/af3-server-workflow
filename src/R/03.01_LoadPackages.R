# src/R/03.01_LoadPackages.R

# ––– 0. Verbosity flag (set TRUE if you ever want debug output)
PKG_VERBOSE <- FALSE

# ––– 1. Define your libs vector (only packages installed via Conda or install_bioc.R)
libs <- c(
  # Bioconductor
  "ArrayExpress", "edgeR", "limma", "msa",
  
  # CRAN
  "dplyr", "ggdist", "ggstar", "grid", "gtools", 
  "multcompView", "openxlsx", "patchwork", "pheatmap", "psych", "RColorBrewer", 
  "readr", "readxl", "reticulate", "rmarkdown", "rstatix", 
  "scales", "showtext", "svglite", "tibble", "tidyverse", "writexl", "yaml"
)

# ––– 2. Load each package quietly, stop if any are missing
missing <- character(0)

suppressPackageStartupMessages({
  invisible(lapply(libs, function(pkg) {
    ok <- suppressWarnings(
      require(pkg, character.only = TRUE, quietly = TRUE, warn.conflicts = FALSE)
    )
    if (!ok) {
      missing <<- c(missing, pkg)
    } else if (PKG_VERBOSE) {
      message("✅ Loaded: ", pkg)
    }
  }))
})

if (length(missing) > 0) {
  stop(
    "❌ The following packages are missing from the Conda env or install_r_packages: ",
    paste(missing, collapse = ", ")
  )
}
message("✅ All required packages loaded successfully.")