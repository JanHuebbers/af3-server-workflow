# src/R/04.04_P6_heatmap.R
#
# P6 – Per-residue metric heatmaps from Merge/<merge_trivia>/minScoresperMSA_merged.xlsx
# ------------------------------------------------------------------------------
# Output:
#   Merge/<merge_trivia>/<date>/P6_heatmap/
#     - P6_Heatmap_<metric>_<merge_trivia>_<date>.svg/.rds
#     - P6_Heatmap_<metric>_<chain>_<merge_trivia>_<date>.svg/.rds
#     - P6_Heatmap_allMetrics_<merge_trivia>_<date>.svg/.rds
#     - P6_heatmap_long_<merge_trivia>_<date>.csv
#
# Run:
#   Rscript src/R/04.04_P6_heatmap.R config/MergeXXXX.yml

# ────────────────────────────────────────────────────────────────────────────────
# 🔧 Parse argument, load packages/theme **and** merge config+params
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) stop("Usage: Rscript 04.04_P6_heatmap.R <merge_config.yml>")

# Loads packages/theme and defines:
# merge_trivia, WiP1, HiP1, (optionally WiP2), ItalChars, ProtNames, FacetTitles, axis_title_expr, ...
source("src/R/04.00_RunMergeSetup.R")

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(ggplot2)
  library(scales)
  library(tibble)
  library(stringr)
  library(openxlsx)
})

# Excel-like color scheme
MIN_COLOR <- "#2D7F83"  # teal (low)
MID_COLOR <- "#FABE50"  # amber
MAX_COLOR <- "#B65256"  # red (high)

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup output directory (Module 4 convention: Merge/<merge_trivia>/<date>/P6_heatmap)
# ────────────────────────────────────────────────────────────────────────────────
current_date  <- as.character(Sys.Date())
date_dir      <- file.path("Merge", merge_trivia, current_date)
output_folder <- file.path(date_dir, "P6_heatmap")
dir.create(output_folder, recursive = TRUE, showWarnings = FALSE)
message("📁 Output folder: ", output_folder)

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Import Confidence Scores (CSV, not Excel) for Sample mapping
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("Merge", merge_trivia, "model_confidences.csv")
if (!file.exists(Path_import)) {
  stop("❌ CSV file not found: ", Path_import)
}

# Read + derive job_id/model_index for filtering, THEN reduce to mapping cols
Conf_scores <- readr::read_csv(Path_import, show_col_types = FALSE) %>%
  dplyr::mutate(ID = dplyr::row_number()) %>%
  tidyr::separate_wider_delim(
    job_folder,
    names = c("sim_id", "job_id", "seed", "trivia_name_02"),
    delim = "_",
    too_many = "merge",
    cols_remove = FALSE
  ) %>%
  dplyr::mutate(
    job_id = stringr::str_pad(as.character(job_id), width = 2, side = "left", pad = "0"),
    model_index = suppressWarnings(as.integer(model_index))
  ) %>%
  # YAML-driven filters (no-ops if vectors are empty)
  { if (exists("drop_job_ids") && length(drop_job_ids)) dplyr::filter(., !(job_id %in% drop_job_ids)) else . } %>%
  { if (exists("drop_models")  && length(drop_models))  dplyr::filter(., !(model_index %in% drop_models)) else . } %>%
  # keep only what you need for mapping/labels (after filtering!)
  dplyr::transmute(
    run_id    = stringr::str_pad(as.character(run_id), width = 4, side = "left", pad = "0"),
    Sample    = as.character(Sample),
    ProtNames = as.character(ProtNames)
  ) %>%
  dplyr::distinct()

# Make sure Sample is an ordered factor
Conf_scores <- Conf_scores %>%
  dplyr::mutate(Sample = factor(Sample, levels = sort(unique(Sample))))

# X-axis order = Sample order
Lx <- levels(Conf_scores$Sample)
if (is.null(Lx) || length(Lx) == 0) Lx <- unique(as.character(Conf_scores$Sample))

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Read merged metrics workbook from Module 4
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("Merge", merge_trivia, "minScoresperMSA_merged.xlsx")
if (!file.exists(Path_import)) {
  stop(
    "❌ minScoresperMSA_merged.xlsx not found: ", Path_import,
    "\nDid you run the Module 4 merge step that writes this file (your _043 merge script)?"
  )
}
message("📥 Reading merged per-residue metrics from: ", Path_import)

sheets_all <- openxlsx::getSheetNames(Path_import)

# Keep only per-chain sheets (exclude Combined/summary helpers)
chain_sheets <- sheets_all[!grepl("^Combined", sheets_all)]
chain_sheets <- chain_sheets[!grepl("^Summary", chain_sheets, ignore.case = TRUE)]
chain_sheets <- chain_sheets[!grepl("^Notes", chain_sheets, ignore.case = TRUE)]

if (length(chain_sheets) == 0) {
  stop(
    "❌ No per-chain sheets found in: ", Path_import,
    "\nSheets present: ", paste(sheets_all, collapse = ", ")
  )
}

# ────────────────────────────────────────────────────────────────────────────────
# 🧩 Helper: read a sheet that has a 2-row header (row1 display, row2 real colnames)
# ────────────────────────────────────────────────────────────────────────────────
read_chain_sheet_twoheader <- function(xlsx, sheet) {
  raw <- openxlsx::read.xlsx(xlsx, sheet = sheet, colNames = FALSE)
  if (nrow(raw) < 3) return(NULL)

  header_names <- as.character(unlist(raw[2, ], use.names = FALSE))
  header_names[is.na(header_names) | header_names == ""] <-
    paste0("V", which(is.na(header_names) | header_names == ""))
  header_names <- make.unique(header_names, sep = "_")

  dat <- raw[-c(1, 2), , drop = FALSE]
  colnames(dat) <- header_names
  dat
}

# Candidate column names for the x-axis position column
pos_candidates <- c("msa_pos", "aln_pos", "MSA_pos", "pos", "position")

# Read and stack all chain sheets into one long table
long_list <- list()

for (sh in chain_sheets) {
  dfc <- read_chain_sheet_twoheader(Path_import, sh)
  if (is.null(dfc)) next

  # Find position column
  pos_col <- pos_candidates[pos_candidates %in% names(dfc)][1]
  if (is.na(pos_col) || is.null(pos_col)) {
    num_like <- names(dfc)[sapply(dfc, function(x) suppressWarnings(!all(is.na(as.integer(as.character(x))))))]
    pos_col <- num_like[1]
  }
  if (is.na(pos_col) || is.null(pos_col)) {
    message("⚠️  Skipping sheet ", sh, " (could not identify position column).")
    next
  }

  # Optional consensus AA column
  aa_col <- c("cons_aa", "aa_aln", "consensus", "AA")[c("cons_aa", "aa_aln", "consensus", "AA") %in% names(dfc)][1]
  if (is.na(aa_col) || is.null(aa_col)) aa_col <- NULL

  # Metric columns should end in min-iPAE/minD/maxContact
  metric_cols <- grep("(min-iPAE|minD|maxContact)$", names(dfc), value = TRUE)
  if (length(metric_cols) == 0) {
    message("⚠️  Sheet ", sh, " has no metric columns ending in min-iPAE/minD/maxContact. Skipping.")
    next
  }

  keep_cols <- c(pos_col, aa_col, metric_cols)
  keep_cols <- keep_cols[!is.na(keep_cols) & keep_cols != ""]
  dfc2 <- dfc[, keep_cols, drop = FALSE] %>%
    dplyr::mutate(
      chain   = as.character(sh),
      msa_pos = suppressWarnings(as.integer(as.character(.data[[pos_col]])))
    ) %>%
    dplyr::filter(!is.na(msa_pos))

  if (!is.null(aa_col) && aa_col %in% names(dfc2)) {
    dfc2 <- dfc2 %>% dplyr::rename(cons_aa = !!aa_col)
  } else {
    dfc2$cons_aa <- NA_character_
  }

  df_long <- dfc2 %>%
    tidyr::pivot_longer(
      cols      = dplyr::all_of(metric_cols),
      names_to  = "col_label",
      values_to = "value"
    ) %>%
    tidyr::separate_wider_regex(
      col_label,
      patterns = c(run_id = "^[^_]+", "_", metric = ".*$"),
      too_few  = "align_start"
    ) %>%
    dplyr::mutate(
      chain   = as.character(chain),
      run_id = stringr::str_pad(as.character(run_id), width = 4, side = "left", pad = "0"),
      metric  = dplyr::recode(metric, "minPAE" = "min-iPAE", .default = metric),
      value   = suppressWarnings(as.numeric(as.character(value)))
    ) %>%
    dplyr::filter(!is.na(value))

  long_list[[sh]] <- df_long
}

if (length(long_list) == 0) stop("❌ No usable chain sheets found in: ", Path_import)
long <- dplyr::bind_rows(long_list)

# ────────────────────────────────────────────────────────────────────────────────
# 🔁 Per-metric normalization + inversion (same semantics as P3)
# ────────────────────────────────────────────────────────────────────────────────
metric_levels <- c("minD", "min-iPAE", "maxContact")
long <- long %>%
  dplyr::mutate(metric = factor(metric, levels = metric_levels)) %>%
  dplyr::filter(!is.na(metric))

long <- long %>%
  dplyr::group_by(metric) %>%
  dplyr::mutate(
    value_scaled = if (diff(range(value, na.rm = TRUE)) == 0) 0.5 else scales::rescale(value, to = c(0, 1)),
    heat_value   = dplyr::case_when(
      metric %in% c("minD", "min-iPAE") ~ 1 - value_scaled,
      TRUE                               ~ value_scaled
    )
  ) %>%
  dplyr::ungroup()

message(
  "✅ Long table built with ", nrow(long), " rows; ",
  dplyr::n_distinct(long$run_id), " runs; ",
  dplyr::n_distinct(long$chain), " chain sheets."
)

# ────────────────────────────────────────────────────────────────────────────────
# 🔤 Map run_id → Sample + ProtNames using Conf_scores (filtered)
# ────────────────────────────────────────────────────────────────────────────────
Conf_scores <- Conf_scores %>%
  dplyr::distinct(run_id, Sample, ProtNames)

long <- long %>%
  dplyr::select(-dplyr::any_of(c("Sample", "ProtNames")))  %>%
  dplyr::left_join(Conf_scores, by = "run_id") %>%
  dplyr::filter(!is.na(Sample))

Ly <- rev(as.character(Lx))
long <- long %>% dplyr::mutate(Sample = factor(as.character(Sample), levels = Ly))

labs_sample_expr <- NULL
if (exists("label_italic_prefix")) {
  lookup <- stats::setNames(Conf_scores$ProtNames, as.character(Conf_scores$Sample))
  lookup[setdiff(Ly, names(lookup))] <- setdiff(Ly, names(lookup))
  labs_sample_expr <- label_italic_prefix(Ly, lookup = lookup, n = ItalChars)
  names(labs_sample_expr) <- Ly
}

# ────────────────────────────────────────────────────────────────────────────────
# 🏷 Chain facet labels as plotmath strings for label_parsed (same as P3)
# ────────────────────────────────────────────────────────────────────────────────
facet_map <- tibble::tibble(
  chain     = names(FacetTitles),
  chain_lab = unname(FacetTitles)   # character vector
)

long <- long %>%
  dplyr::mutate(chain = as.character(chain)) %>%
  dplyr::left_join(facet_map, by = "chain") %>%
  dplyr::mutate(
    chain_lab = ifelse(
      is.na(chain_lab) | chain_lab == "",
      chain,
      chain_lab
    ),
    chain_lab = as.character(chain_lab)
  )

# Ensure facet ordering follows `chain` while labels use `chain_lab`.
# We compute factor levels for `chain_lab` by arranging unique (chain, chain_lab)
# pairs by `chain` and then convert `chain_lab` to a factor with those levels.
chain_lab_levels <- long %>%
  dplyr::distinct(chain, chain_lab) %>%
  dplyr::arrange(chain) %>%
  dplyr::pull(chain_lab)

long <- long %>%
  dplyr::mutate(
    chain_lab = factor(chain_lab, levels = chain_lab_levels)
  )
metrics <- c("min-iPAE", "minD", "maxContact")
metrics <- metrics[metrics %in% unique(as.character(long$metric))]  
# ────────────────────────────────────────────────────────────────────────────────
# 💾 Save long-format data for downstream debugging / reuse
# ────────────────────────────────────────────────────────────────────────────────
csv_out <- file.path(output_folder, paste0("P6_heatmap_long_", merge_trivia, "_", current_date, ".csv"))
readr::write_csv(long, csv_out)
message("🧾 Wrote long table: ", csv_out)

# ────────────────────────────────────────────────────────────────────────────────
# 🎨 01 Helper: heatmap per chain_lab per metric (single panel, no facet)
# ────────────────────────────────────────────────────────────────────────────────
WiP2_safe <- if (exists("WiP2")) WiP2 else 15.5
HiP1_safe <- if (exists("HiP1")) HiP1 else 5.5

chains  <- levels(long$chain_lab)
metrics <- c("min-iPAE", "minD", "maxContact")

plot_metric_chain_heatmap <- function(data, chain_lab_value, metric_name, Ly) {
  data %>%
    dplyr::filter(metric == metric_name, chain_lab == chain_lab_value) %>%
    ggplot2::ggplot(ggplot2::aes(x = msa_pos, y = Sample, fill = heat_value)) +
    ggplot2::geom_tile() +
    ggplot2::scale_fill_gradientn(
      colours  = c(MIN_COLOR, MID_COLOR, MAX_COLOR),
      values   = c(0, 0.5, 1),
      limits   = c(0, 1),
      na.value = "grey95"
    ) +
    ggplot2::scale_x_continuous(expand = c(0.001, 0.001)) +
    ggplot2::scale_y_discrete(
      labels = if (!is.null(labs_sample_expr)) labs_sample_expr else waiver(),
      limits = Ly,
      name   = axis_title_expr,
      expand = c(0.001, 0.001)
    ) +
    ggplot2::labs(x = "MSA position", y = axis_title_expr) +
    ggplot2::guides(fill = "none")
}

# ────────────────────────────────────────────────────────────────────────────────
# 📊 01 Generate & save heatmaps per chain (one file per chain × metric)
# ────────────────────────────────────────────────────────────────────────────────
message("📊 Generating and saving P6 heatmaps per chain:")

for (c_lab in chains) {
  for (m in metrics) {
    p <- plot_metric_chain_heatmap(long, c_lab, m, Ly)

    c_tag <- gsub("[^A-Za-z0-9_-]+", "", as.character(c_lab))
    base_name <- paste0("P6_Heatmap_", m, "_", c_tag, "_", merge_trivia, "_", current_date)
    base_path <- file.path(output_folder, base_name)

    ggplot2::ggsave(
      filename  = paste0(base_path, ".svg"),
      plot      = p,
      width     = 15.5,
      height    = HiP1_safe,
      unit      = "cm",
      limitsize = FALSE
    )
    saveRDS(p, file = paste0(base_path, ".rds"))
  }
}

# ────────────────────────────────────────────────────────────────────────────────
# 🎨 02 Helper: heatmap for all chains and one metric (facet_grid, proportional widths)
# ────────────────────────────────────────────────────────────────────────────────
plot_metric_heatmap <- function(data, metric_name, Ly) {
  data %>%
    dplyr::filter(metric == metric_name) %>%
    ggplot2::ggplot(ggplot2::aes(x = msa_pos, y = Sample, fill = heat_value)) +
    ggplot2::geom_tile() +
    ggplot2::scale_fill_gradientn(
      colours  = c(MIN_COLOR, MID_COLOR, MAX_COLOR),
      values   = c(0, 0.5, 1),
      limits   = c(0, 1),
      na.value = "grey95"
    ) +
    ggplot2::facet_grid(
      . ~ chain_lab,
      scales   = "free_x",
      space    = "free_x",
      labeller = ggplot2::label_parsed
    ) +
    ggplot2::scale_y_discrete(
      labels = if (!is.null(labs_sample_expr)) labs_sample_expr else waiver(),
      limits = Ly,
      name   = axis_title_expr,
      expand = c(0.03, 0.03)
    ) +
    ggplot2::labs(x = "MSA position", y = axis_title_expr) +
    ggplot2::guides(fill = "none")
}

# ────────────────────────────────────────────────────────────────────────────────
# 📊 02 Generate & save heatmaps per metric
# ────────────────────────────────────────────────────────────────────────────────
message("📊 Generating and saving P6 heatmaps per metric:")

for (m in metrics) {
  p <- plot_metric_heatmap(long, m, Ly)

  base_name <- paste0("P6_Heatmap_", m, "_", merge_trivia, "_", current_date)
  base_path <- file.path(output_folder, base_name)

  ggplot2::ggsave(
    filename  = paste0(base_path, ".svg"),
    plot      = p,
    width     = WiP2_safe,
    height    = HiP1_safe,
    unit      = "cm",
    limitsize = FALSE
  )
  saveRDS(p, file = paste0(base_path, ".rds"))
}

# ----------------------------------------------------------------------------- 
# 03 Combined heatmap containing all metrics (rows) × chains (columns)
# ----------------------------------------------------------------------------- 
message("📊 Generating combined P6 heatmap (all metrics)...")

p_all <- long %>%
  ggplot2::ggplot(ggplot2::aes(x = msa_pos, y = Sample, fill = heat_value)) +
  ggplot2::geom_tile() +
  ggplot2::scale_fill_gradientn(
    colours  = c(MIN_COLOR, MID_COLOR, MAX_COLOR),
    values   = c(0, 0.5, 1),
    limits   = c(0, 1),
    na.value = "grey95"
  ) +
  ggplot2::facet_grid(
    metric ~ chain_lab,
    scales = "free_x",
    space  = "free_x",
    labeller = ggplot2::labeller(
      metric    = ggplot2::label_value,
      chain_lab = ggplot2::label_parsed
    )
  ) +
  ggplot2::scale_y_discrete(
    labels = if (!is.null(labs_sample_expr)) labs_sample_expr else waiver(),
    limits = Ly,
    name   = axis_title_expr,
    expand = c(0.03, 0.03)
  ) +
  ggplot2::labs(x = "MSA position", y = axis_title_expr) +
  ggplot2::guides(fill = "none")

base_name_all <- paste0("P6_Heatmap_allMetrics_", merge_trivia, "_", current_date)
base_path_all <- file.path(output_folder, base_name_all)

ggplot2::ggsave(
  filename  = paste0(base_path_all, ".svg"),
  plot      = p_all,
  width     = 15.5,
  height    = 15.0,
  unit      = "cm",
  limitsize = FALSE
)
saveRDS(p_all, file = paste0(base_path_all, ".rds"))

message("   • ", paste0(base_path_all, ".svg"))
message("   • ", paste0(base_path_all, ".rds"))
message("✅ Done.")