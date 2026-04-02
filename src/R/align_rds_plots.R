#!/usr/bin/env Rscript

# align_rds_plots.R
#
# Usage:
#   Rscript src/R/align_rds_plots.R <rds_dir> [width_cm] [height_cm]
#
# Examples:
#   Rscript src/R/align_rds_plots.R ./Metrics_plots/0097_2025-12-09/Scores
#   Rscript src/R/align_rds_plots.R ./Metrics_plots/0097_2025-12-09/Scores 8 6.5
#
# Behavior:
#   - If width/height are given on the command line, they are used for ALL plots.
#   - Otherwise, per-plot defaults (by filename pattern) are used.
#   - If neither CLI nor per-plot rule applies: fallback = 16 x 6 cm.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1L) {
  stop(
    "Usage: Rscript src/R/align_rds_plots.R <rds_dir> [width_cm] [height_cm]",
    call. = FALSE
  )
}

input_dir <- normalizePath(args[1], mustWork = TRUE)

parse_dim <- function(x) {
  if (length(x) == 0L) return(NA_real_)
  if (x %in% c("", "NA", "NaN", "-")) return(NA_real_)
  as.numeric(x)
}

cli_width_cm  <- if (length(args) >= 2L) parse_dim(args[2]) else NA_real_
cli_height_cm <- if (length(args) >= 3L) parse_dim(args[3]) else NA_real_

# Global fallback (used only if no CLI AND no per-stem rule)
global_default_width_cm  <- 16
global_default_height_cm <- 6

# Basic sanity on CLI if provided
if (!is.na(cli_width_cm) && cli_width_cm <= 0) {
  stop("Width (if supplied) must be a positive numeric value in cm.")
}
if (!is.na(cli_height_cm) && cli_height_cm <= 0) {
  stop("Height (if supplied) must be a positive numeric value in cm.")
}

message("Input directory: ", input_dir)

if (!is.na(cli_width_cm) || !is.na(cli_height_cm)) {
  message(
    "Plot size overridden from CLI: ",
    ifelse(is.na(cli_width_cm),  global_default_width_cm,  cli_width_cm),  " x ",
    ifelse(is.na(cli_height_cm), global_default_height_cm, cli_height_cm), " cm"
  )
} else {
  message(
    "Using script defaults & per-plot rules (fallback ",
    global_default_width_cm, " x ", global_default_height_cm, " cm)"
  )
}

cm_to_in <- 1 / 2.54

# -------------------------------------------------------------------
# Load packages + theme + (optionally) custom align_plots wrapper
# -------------------------------------------------------------------
suppressMessages({
  source("src/R/03.01_LoadPackages.R")
  source("src/R/03.02_ggPlotTheme.R")  # where your theme + align_plots live
})

if (!dir.exists(input_dir)) {
  stop("Input directory does not exist: ", input_dir, call. = FALSE)
}

rds_files <- list.files(
  path       = input_dir,
  pattern    = "\\.rds$",
  full.names = TRUE
)

if (length(rds_files) == 0L) {
  stop("No .rds files found in: ", input_dir, call. = FALSE)
}

aligned_dir <- file.path(input_dir, "aligned_01")
if (!dir.exists(aligned_dir)) {
  dir.create(aligned_dir, recursive = TRUE, showWarnings = FALSE)
}

message("Found ", length(rds_files), " .rds file(s).")
message("Aligned outputs will be written to: ", aligned_dir)

# helper: base name without extension
file_stem <- function(path) {
  tools::file_path_sans_ext(basename(path))
}

# -------------------------------------------------------------------
# Size helper
#   Priority:
#     1) CLI width/height (if given) → used for ALL plots
#     2) Per-stem defaults (when no CLI)
#     3) Global fallback 16 x 6 (when no CLI and no rule)
# -------------------------------------------------------------------
get_size_cm <- function(stem,
                        cli_w  = cli_width_cm,
                        cli_h  = cli_height_cm,
                        def_w  = global_default_width_cm,
                        def_h  = global_default_height_cm) {
  # 1) Start from global fallback
  stem_w <- def_w
  stem_h <- def_h

  # 2) Refine with per-stem defaults
  if (grepl("^P1_Score_", stem)) {
    stem_w <- 8;   stem_h <- 5.5   # violin / scores
  } else if (grepl("^P2_pTMvsipTM_raw_", stem)) {
    stem_w <- 5.5; stem_h <- 5.5   # raw scatter
  } else if (grepl("^P2_pTMvsipTM_sig_", stem)) {
    stem_w <- 5.5; stem_h <- 5.5   # sigmoid scatter
  } else if (grepl("^P3_Heatmap_allMetrics_", stem)) {
    stem_w <- 15.5;  stem_h <- 15    # big grid
  } else if (grepl("^P3_Heatmap_maxContact_", stem)) {
    stem_w <- 15.5;  stem_h <- 5.5
  } else if (grepl("^P3_Heatmap_minD_", stem)) {
    stem_w <- 15.5;  stem_h <- 5.5
  } else if (grepl("^P3_Heatmap_min-iPAE_", stem)) {
    stem_w <- 15.5;  stem_h <- 5.5
  } else if (grepl("^P4_Score_", stem)) {
    stem_w <- 7.8;   stem_h <- 4.5
  } else if (grepl("^P5_pTMvsipTM_raw_", stem)) {
    stem_w <- 6.8; stem_h <- 5.5
  } else if (grepl("^P5_pTMvsipTM_sig_", stem)) {
    stem_w <- 6.8; stem_h <- 5.5
  } else if (grepl("^P6_Heatmap_maxContact_", stem)) {
    stem_w <- 15.5; stem_h <- 5.5
  } else if (grepl("^P10_Violin_", stem)) {
    stem_w <- 7.8;   stem_h <- 4.5 
  }

  # 3) Apply CLI overrides per dimension (NA = no override)
  w <- if (!is.na(cli_w)) cli_w else stem_w
  h <- if (!is.na(cli_h)) cli_h else stem_h

  list(w = w, h = h)
}

# -------------------------------------------------------------------
# Read all .rds and keep only ggplot objects
# -------------------------------------------------------------------
objs <- lapply(rds_files, readRDS)
is_plot <- vapply(objs, inherits, logical(1), what = "gg")

if (!any(is_plot)) {
  stop("None of the .rds files in ", input_dir, " are ggplot objects.")
}

plot_files <- rds_files[is_plot]
plot_objs  <- objs[is_plot]

message("Using ", length(plot_objs), " ggplot object(s) for alignment:")
for (pf in plot_files) message("  • ", basename(pf))

# -------------------------------------------------------------------
# Align all plots together using align_plots()
# -------------------------------------------------------------------
aligned_list <- align_plots(
  data   = plot_objs,
  align  = "hv",
  axis   = "ytbr",
  greedy = TRUE
)

# Safety: make sure lengths match
if (length(aligned_list) != length(plot_objs)) {
  stop("align_plots() returned ", length(aligned_list),
       " plots for ", length(plot_objs), " inputs.")
}

# -------------------------------------------------------------------
# Save aligned plots: one SVG + one RDS per input
# -------------------------------------------------------------------
for (i in seq_along(plot_files)) {
  stem      <- file_stem(plot_files[i])
  p_aligned <- aligned_list[[i]]

  # Choose size (CLI wins, then stem rules, then global fallback)
  sz <- get_size_cm(stem)

  svg_path <- file.path(aligned_dir, paste0(stem, "_aligned.svg"))

  ggplot2::ggsave(
    filename  = svg_path,
    plot      = p_aligned,
    width     = sz$w,
    height    = sz$h,
    units     = "cm",
    limitsize = FALSE,
    bg        = "transparent"  # or "white" if you prefer the box
  )

  message("  Wrote: ", svg_path, " (", sz$w, " x ", sz$h, " cm)")

  rds_out <- file.path(aligned_dir, paste0(stem, "_aligned.rds"))
  saveRDS(p_aligned, rds_out)
  message("  Wrote: ", rds_out)
}

message("\nAll plots aligned and saved.")