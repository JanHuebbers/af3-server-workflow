# src/R/03.06_P3_heatmap.R
#
# P3 – Per-residue metric heatmaps from AF3_output/<simID>/csv/minScoresperMSA.csv
# ------------------------------------------------------------------------------

# ────────────────────────────────────────────────────────────────────────────────
# 🔧 Parse argument, load packages/theme **and** config+params+simID
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript 03.06_P3_heatmap.R <config.yml>")
}
# Loads packages, theme, and defines `simID`, ProtNames, ItalChars, axis_title_expr, WiP1, HiP1, etc.
source("src/R/03.00_RunSetup.R")

# Excel-like color scheme (shared semantics with _025_AlignMinMetricsBot.py)
MIN_COLOR <- "#2D7F83"  # teal (low)
MID_COLOR <- "#FABE50"  # amber
MAX_COLOR <- "#B65256"  # red (high)

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup output directory
# ────────────────────────────────────────────────────────────────────────────────
JobID <- simID
current_date <- Sys.Date()
base_dir <- "Metrics_plots"
folder_name <- paste(JobID, current_date, sep = "_")
output_folder <- file.path(base_dir, folder_name)

if (!dir.exists(base_dir)) {
  dir.create(base_dir, recursive = TRUE)
}

if (!dir.exists(output_folder)) {
  dir.create(output_folder, recursive = TRUE)
  message("📁 Output folder created: ", output_folder)
} else {
  message("📁 Output folder already exists: ", output_folder)
}

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Read minScoresperMSA.csv for this simID
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("AF3_output", simID, "csv", "minScoresperMSA.csv")

if (!file.exists(Path_import)) {
  stop("❌ minScoresperMSA.csv not found: ", Path_import)
}

message("📥 Reading minScoresperMSA from: ", Path_import)

df <- readr::read_csv(Path_import, show_col_types = FALSE)

# Expect at least these "annotation" columns
required_cols <- c("chain", "msa_pos", "cons_aa")
if (!all(required_cols %in% names(df))) {
  stop(
    "❌ minScoresperMSA.csv is missing required columns: ",
    paste(setdiff(required_cols, names(df)), collapse = ", ")
  )
}

# Ensure msa_pos is numeric
df <- df %>%
  dplyr::mutate(
    msa_pos = suppressWarnings(as.integer(msa_pos))
  )

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Read model_trivia_map.csv for this simID
# ────────────────────────────────────────────────────────────────────────────────
Path_trivia <- file.path("AF3_output", simID, "model_trivia_map.csv")

if (!file.exists(Path_trivia)) {
  stop("❌ model_trivia_map.csv not found: ", Path_trivia)
}

message("📥 Reading model_trivia_map.csv from: ", Path_trivia)

trivia_df <- readr::read_csv(Path_trivia, show_col_types = FALSE) %>%
  dplyr::mutate(
    job_key       = as.character(job_key),
    sample_letter = as.character(sample_letter),
    model_index   = suppressWarnings(as.integer(model_index))
  )

# Expect at least these columns
required_cols_trivia <- c("job_folder", "job_key", "model_index", "sample_letter", "trivia_name")
if (!all(required_cols_trivia %in% names(trivia_df))) {
  stop(
    "❌ model_trivia_map.csv is missing required columns: ",
    paste(setdiff(required_cols_trivia, names(trivia_df)), collapse = ", ")
  )
}

# ────────────────────────────────────────────────────────────────────────────────
# 🧮 Pivot metric columns to long format
# ────────────────────────────────────────────────────────────────────────────────
# Metric columns look like:
#   0084-01_min-iPAE, ..., 0084-01_minD, ..., 0084-01_maxContact, ...
# We pivot them to:
#   chain, msa_pos, cons_aa, run_id, metric, value

metric_cols <- grep("(min-iPAE|minD|maxContact)$", names(df), value = TRUE)
if (length(metric_cols) == 0) {
  stop("❌ No metric columns ending in min-iPAE/minD/maxContact found in: ", Path_import)
}

long <- df %>%
  tidyr::pivot_longer(
    cols      = dplyr::all_of(metric_cols),
    names_to  = "col_label",
    values_to = "value"
  ) %>%
  # Split col_label "0084-01_minD" → run_id="0084-01", metric="minD"
  tidyr::separate_wider_regex(
    col_label,
    patterns = c(run_id = "^[^_]+", "_", metric = ".*$"),
    too_few  = "align_start"
  ) %>%
  dplyr::mutate(
    chain   = as.character(chain),
    msa_pos = as.integer(msa_pos),
    cons_aa = as.character(cons_aa)
  ) %>%
  dplyr::filter(!is.na(msa_pos))

# Clean up metric labels (align with Excel & previous scripts)
long <- long %>%
  dplyr::mutate(
    metric = dplyr::recode(
      metric,
      "minPAE" = "min-iPAE",  # safety; CSV usually already uses min-iPAE
      .default = metric
    )
  )

# Order metrics nicely
metric_levels <- c("minD", "min-iPAE", "maxContact")
long <- long %>%
  dplyr::mutate(
    metric = factor(metric, levels = metric_levels)
  ) %>%
  dplyr::filter(!is.na(value))

message(
  "✅ Long table built with ", nrow(long), " rows, ",
  dplyr::n_distinct(long$run_id), " runs, ",
  dplyr::n_distinct(long$metric), " metrics."
)

# ────────────────────────────────────────────────────────────────────────────────
# 🔁 Per-metric normalization + inversion
# ────────────────────────────────────────────────────────────────────────────────
# Goal:
#   - Per metric, normalize raw values → value_scaled in [0,1]
#   - For minD and min-iPAE: invert so low distance/error becomes "hot"
#   - For maxContact: keep direction (high contact = "hot")

long <- long %>%
  dplyr::group_by(metric) %>%
  dplyr::mutate(
    value_scaled = if (diff(range(value, na.rm = TRUE)) == 0) {
      0.5
    } else {
      scales::rescale(value, to = c(0, 1))
    },
    heat_value = dplyr::case_when(
      metric %in% c("minD", "min-iPAE") ~ 1 - value_scaled,
      TRUE                              ~ value_scaled
    )
  ) %>%
  dplyr::ungroup()

# ────────────────────────────────────────────────────────────────────────────────
# 🔤 Map run_id → Sample letters using model_trivia_map + ProtNames
# ────────────────────────────────────────────────────────────────────────────────
# - `run_id` in long corresponds to prefixes like "0084-10"
# - `trivia_df$job_key` stores the same prefix
# - `trivia_df$sample_letter` stores the config letter (A, B, C, …)
# - canonical order for y-axis is names(ProtNames)

if (is.null(names(ProtNames)) || length(names(ProtNames)) == 0) {
  stop("❌ ProtNames from config must be a *named* vector/list, e.g. A: 'AtMLO1', B: 'AtMLO2', …")
}

sample_letters_cfg <- names(ProtNames)

# basic mapping: one row per (job_key, sample_letter)
sample_map <- trivia_df %>%
  dplyr::filter(
    !is.na(job_key), job_key != "",
    !is.na(sample_letter), sample_letter != ""
  ) %>%
  dplyr::distinct(job_key, sample_letter)

# keep only runs we actually have in long
present_runs <- intersect(unique(long$run_id), sample_map$job_key)

if (length(present_runs) == 0) {
  stop("❌ No overlap between minScoresperMSA run_id and model_trivia_map job_key.")
}

sample_map <- sample_map %>%
  dplyr::filter(job_key %in% present_runs) %>%
  dplyr::rename(
    run_id = job_key,
    Sample = sample_letter
  )

# y-axis order: config order, but only letters that actually have data
Ly <- rev(sample_letters_cfg[sample_letters_cfg %in% sample_map$Sample])

if (length(Ly) == 0) {
  stop("❌ None of the ProtNames Sample letters are present in model_trivia_map for this run.")
}

# Precompute expression labels for Sample (A, B, C, ...)
# This bakes ProtNames + ItalChars into the plot object.
labs_sample_expr <- label_italic_prefix(Ly, lookup = ProtNames, n = ItalChars)
names(labs_sample_expr) <- Ly

# add Sample to long
long <- long %>%
  dplyr::inner_join(sample_map, by = "run_id") %>%
  dplyr::mutate(
    Sample = factor(Sample, levels = Ly)
  )

message("✅ Samples present (in order): ", paste(Ly, collapse = ", "))

# ────────────────────────────────────────────────────────────────────────────────
# 🏷 Chain facet labels as plotmath strings for label_parsed
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

# ────────────────────────────────────────────────────────────────────────────────
# 🎨 01 Helper: heatmap per chain_lab per metric (single panel, no facet)
# ────────────────────────────────────────────────────────────────────────────────
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
    ggplot2::scale_x_continuous(
      expand = c(0.001, 0.001)
    ) +
    ggplot2::scale_y_discrete(
      labels = labs_sample_expr,
      limits = Ly,
      name   = axis_title_expr,
      expand = c(0.001, 0.001)
    ) +
    ggplot2::labs(
      x = "MSA position",
      y = axis_title_expr
    ) +
    ggplot2::guides(fill = "none")
}

# ────────────────────────────────────────────────────────────────────────────────
# 📊 01 Generate & save heatmaps per chain (one file per chain × metric)
# ────────────────────────────────────────────────────────────────────────────────
chains <- levels(long$chain_lab)  # preserves your intended facet order
metrics <- c("min-iPAE", "minD", "maxContact")

message("📊 Generating and saving heatmaps per chain:")

for (c_lab in chains) {
  for (m in metrics) {
    p <- plot_metric_chain_heatmap(long, c_lab, m, Ly)

    # sanitize chain label for filenames (avoid spaces/special chars)
    c_tag <- gsub("[^A-Za-z0-9_-]+", "", as.character(c_lab))

    base_name <- paste0("P3_Heatmap_", m, "_", c_tag, "_", JobID, "_", current_date)
    base_path <- file.path(output_folder, base_name)

    ggplot2::ggsave(
      filename  = paste0(base_path, ".svg"),
      plot      = p,
      width     = 15.5,
      height    = HiP1,
      unit      = "cm",
      limitsize = FALSE
    )
    saveRDS(p, file = paste0(base_path, ".rds"))

    message("   • ", paste0(base_path, ".svg"))
    message("   • ", paste0(base_path, ".rds"))
  }
}

# ────────────────────────────────────────────────────────────────────────────────
# 🎨 02 Helper: heatmap for all chains and one metric
# ────────────────────────────────────────────────────────────────────────────────
plot_metric_heatmap <- function(data, metric_name, Ly) {
  data %>%
    dplyr::filter(metric == metric_name) %>%
    ggplot2::ggplot(
      ggplot2::aes(x = msa_pos, y = Sample, fill = heat_value)
    ) +
    ggplot2::geom_tile() +
    ggplot2::scale_fill_gradientn(
      colours  = c(MIN_COLOR, MID_COLOR, MAX_COLOR),
      values   = c(0, 0.5, 1),
      limits   = c(0, 1),
      na.value = "grey95"
    ) +
    ggplot2::facet_wrap(
      ~ chain_lab,
      scales  = "free_x",
      nrow    = 1,
      labeller = ggplot2::label_parsed
    ) +
    ggplot2::scale_y_discrete(
      labels = labs_sample_expr,  # <- baked expressions
      limits = Ly,
      name   = axis_title_expr,
      expand = c(0.03, 0.03)
    ) +
    ggplot2::labs(
      x = "MSA position",
      y = axis_title_expr
    ) +
    ggplot2::guides(
      fill = "none"
    )
}
# ────────────────────────────────────────────────────────────────────────────────
# 📊 02 Generate & save heatmaps per metric
# ────────────────────────────────────────────────────────────────────────────────

metrics <- c("min-iPAE", "minD", "maxContact")

message("📊 Generating and saving heatmaps per metric:")

for (m in metrics) {
  # build plot for this metric
  p <- plot_metric_heatmap(long, m, Ly)

  # one base name & path
  base_name <- paste0("P3_Heatmap_", m, "_", JobID, "_", current_date)
  base_path <- file.path(output_folder, base_name)

  # save SVG
  ggplot2::ggsave(
    filename  = paste0(base_path, ".svg"),
    plot      = p,
    width     = WiP2,
    height    = HiP1,
    unit      = "cm",
    limitsize = FALSE
  )

  saveRDS(p, file = paste0(base_path, ".rds"))

  message("   • ", paste0(base_path, ".svg"))
  message("   • ", paste0(base_path, ".rds"))
}

# ----------------------------------------------------------------------------- 
# 03 Combined heatmap containing all metrics (rows) × chains (columns)
# ----------------------------------------------------------------------------- 
message("📊 Generating combined heatmap (all metrics)...")

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
    labels = labs_sample_expr,
    limits = Ly,
    name   = axis_title_expr,
    expand = c(0.03, 0.03)
  ) +
  ggplot2::labs(
    x = "MSA position",
    y = axis_title_expr
  ) +
  ggplot2::guides(fill = "none")

# one base name & path for combined plot
base_name_all <- paste0("P3_Heatmap_allMetrics_", JobID, "_", current_date)
base_path_all <- file.path(output_folder, base_name_all)

# SVG
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

# ────────────────────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────────────────────