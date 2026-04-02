# src/R/install_r_packages.R

# Set CRAN mirror explicitly
options(repos = c(CRAN = "https://cloud.r-project.org"))



# Ensure BiocManager is available
if (!requireNamespace("BiocManager", quietly = TRUE))
  install.packages("BiocManager")

# Bioconductor packages
bioc_pkgs <- c("ArrayExpress", "edgeR", "limma", "msa")
for (pkg in bioc_pkgs) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    BiocManager::install(pkg, ask = FALSE)
  }
}


# CRAN packages not included in r-essentials
cran_pkgs <- c(
  "ggdist", "ggpattern", "gtools", "multcompView", "openxlsx", "patchwork", "pheatmap", "psych", "writexl"
)

for (pkg in cran_pkgs) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    install.packages(pkg)
  }
}
