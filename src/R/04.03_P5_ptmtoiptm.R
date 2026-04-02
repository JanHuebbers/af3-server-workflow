# src/R/04.03_P5_ptmtoiptm.R

# ────────────────────────────────────────────────────────────────────────────────
# Parse argument, load packages/theme **and** merge config+params
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) stop("Usage: Rscript 04.03_P5_ptmtoiptm.R <config.yml>")
config_path <- args[1]

# this pulls in 04.00_RunMergeSetup.R which in turn sources your loader etc.
source("src/R/04.00_RunMergeSetup.R")

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Import Confidence Scores (CSV, not Excel)
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("Merge", merge_trivia, "model_confidences.csv")
if (!file.exists(Path_import)) {
  stop("❌ CSV file not found: ", Path_import)
}

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
    job_id      = stringr::str_pad(as.character(job_id), width = 2, pad = "0"),
    # SAFE coercion (works for numeric/character/factor):
    model_index = suppressWarnings(as.integer(model_index)),
    # ensure seed is character (for shape mapping)
    seed        = as.character(seed),
    # make ranking_score robust for top-selection
    ranking_score = suppressWarnings(as.numeric(ranking_score))
  ) %>%
  # YAML-driven filters (no-ops if vectors are empty)
  { if (length(drop_job_ids)) dplyr::filter(., !(job_id %in% drop_job_ids)) else . } %>%
  { if (length(drop_models))  dplyr::filter(., !(model_index %in% drop_models)) else . } %>%
  dplyr::relocate(ID, .after = run_id) %>%
  dplyr::relocate(Sample, .after = ID)

if ("Sample" %in% names(Conf_scores)) {
  Conf_scores <- Conf_scores %>%
    dplyr::mutate(Sample = factor(Sample, levels = sort(unique(Sample))))
}

# ────────────────────────────────────────────────────────────────────────────────
# 🔁 Sigmoidal transform (centered logistic, NO min/max scaling)
# ────────────────────────────────────────────────────────────────────────────────
K_SIG <- 8  # global steepness parameter for all sigmoid transforms

sigmoid_spread <- function(x, center, k = K_SIG) {
  # center: where you want most spread (e.g. median of the scores)
  # k     : steepness; larger = more aggressive (from config: K_SIG)
  plogis(k * (x - center))
}

# centers for pTM and ipTM (on raw scale)
ptm_center  <- stats::median(Conf_scores$ptm,  na.rm = TRUE)
iptm_center <- stats::median(Conf_scores$iptm, na.rm = TRUE)

# add transformed columns
Conf_scores <- Conf_scores %>%
  dplyr::mutate(
    ptm_sig  = sigmoid_spread(ptm,  center = ptm_center),
    iptm_sig = sigmoid_spread(iptm, center = iptm_center)
  )

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup Output Directory
# ────────────────────────────────────────────────────────────────────────────────
current_date <- Sys.Date()
base_dir     <- "Merge"
output_folder <- file.path(base_dir, merge_trivia, current_date)

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
# 📊 Data arrangement for plotting (reusing 04.02-style Fill_* + config colors)
# ────────────────────────────────────────────────────────────────────────────────
S <- dplyr::n_distinct(Conf_scores$Sample)  # Number of different input chain combinations

#Specify Box / Point / Mean color keys
Fill_box   <- rep(paste0("Box_",   1:S), 1)
Fill_point <- rep(paste0("Point_", 1:S), 1)
Fill_mean  <- rep(paste0("MPoint_",1:S), 1)

#Final data frame for plotting (including Fill_* keys)
Data_plot <- Conf_scores %>%
  dplyr::arrange(Sample) %>%
  dplyr::group_by(Sample) %>%
  tidyr::nest() %>%
  tibble::add_column(Fill_box) %>%
  tibble::add_column(Fill_point) %>%
  tibble::add_column(Fill_mean) %>%
  tidyr::unnest(cols = c(data)) %>%
  dplyr::ungroup()

# ────────────────────────────────────────────────────────────────────────────────
# ℹ Quick summary
# ────────────────────────────────────────────────────────────────────────────────
E <- dplyr::n_distinct(Data_plot$seed)      # Number of different seeds
message("✅ Data prepared: ", S, " input chain combinations; ", E, " seeds")

# ────────────────────────────────────────────────────────────────────────────────
# 📈 Plotting function: pTM vs ipTM with starshape = seed, Fill_point colors
# ────────────────────────────────────────────────────────────────────────────────

# Tick positions and labels (shared)
breaks_raw <- seq(0.0, 1.0, 0.2)
labels_raw <- sprintf("%.1f", breaks_raw)   # "0.0", "0.1", ..., "1.0"

# Seed → starshape mapping (same as in 04.02)
seed_levels <- c("1710", "1711", "1712",
                 "1701", "1702", "1703",
                 "1704", "1705", "1706",
                 "1707", "1708", "1709")

star_shapes <- c(15, 13, 28, 11, 23, 1, 2, 4, 5, 29, 24, 27)

# 🔒 Bake seed levels into the data
Conf_scores <- Conf_scores %>%
  dplyr::mutate(seed = factor(seed, levels = seed_levels))

plot_fun <- function(data,
                     x, y,
                     x_title, y_title,
                     use_sigmoid_ticks = FALSE,
                     k = K_SIG,
                     f = f,
                     alpha_val = 0.50,
                     size_val = 1.0,
                     starstroke_val = 0.5) {

  p <- ggplot(data = data, aes(x = .data[[x]], y = .data[[y]])) +
    geom_star(
      aes(
        starshape = seed,
        fill      = Fill_point
      ),
      alpha = alpha_val,
      size  = size_val,
      color = "#000000",
      starstroke = starstroke_val
    ) +
    scale_starshape_manual(
      limits = seed_levels,
      values = star_shapes
    ) +
    scale_fill_manual(values = f) +
    guides(
      fill      = "none",
      color     = "none",
      size      = "none",
      shape     = "none",
      starshape = "none",
      alpha     = "none"
    )

  if (!use_sigmoid_ticks) {
    # standard, equally spaced ticks in raw scale
    p <- p +
      scale_x_continuous(
        breaks = breaks_raw,
        labels = labels_raw,
        limits = c(-0.05, 1.05),
        name   = x_title,
        expand = c(0.001, 0.001)
      ) +
      scale_y_continuous(
        breaks = breaks_raw,
        labels = labels_raw,
        limits = c(-0.05, 1.05),
        name   = y_title,
        expand = c(0.001, 0.001)
      )
  } else {
    # ticks correspond to *untransformed* pTM/ipTM values,
    # placed at sigmoid-transformed positions (per-axis median center),
    # but still using the full 0..1 range for breaks/limits.

    x_center <- ptm_center
    y_center <- iptm_center

    p <- p +
      scale_x_continuous(
        breaks = sigmoid_spread(breaks_raw, center = x_center, k = k),
        labels = labels_raw,
        limits = c(0.00, 1.00),
        name   = x_title,
        expand = c(0.001, 0.001)
      ) +
      scale_y_continuous(
        breaks = sigmoid_spread(breaks_raw, center = y_center, k = k),
        labels = labels_raw,
        limits = c(0.00, 1.00),
        name   = y_title,
        expand = c(0.001, 0.001)
      )
  }

  p
}

# ────────────────────────────────────────────────────────────────────────────────
# 🖼 Generate and Save Plots (raw + sigmoidal)
# ────────────────────────────────────────────────────────────────────────────────

# 1) Untransformed pTM vs ipTM (linear axes)
ptm_vs_iptm_raw <- plot_fun(
  Data_plot,
  x        = "ptm",
  y        = "iptm",
  x_title  = "pTM score",
  y_title  = "ipTM score",
  use_sigmoid_ticks = FALSE,
  f = f
)

base_name_raw <- paste0("P5_pTMvsipTM_raw_", merge_trivia, "_", current_date)
base_path_raw <- file.path(output_folder, base_name_raw)

ggsave(
  file      = paste0(base_path_raw, ".svg"),
  plot      = ptm_vs_iptm_raw,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(ptm_vs_iptm_raw, file = paste0(base_path_raw, ".rds"))

# 2) Sigmoid-transformed plot:
#    - data: ptm_sig / iptm_sig (centered on medians)
#    - ticks: positions = sigmoid_spread(raw breaks, per-axis median)
#             labels    = raw breaks (0.0, 0.1, ..., 1.0)
ptm_vs_iptm_sig <- plot_fun(
  Data_plot,
  x        = "ptm_sig",
  y        = "iptm_sig",
  x_title  = "pTM score",
  y_title  = "ipTM score",
  use_sigmoid_ticks = TRUE,
  f = f
)

base_name_sig <- paste0("P5_pTMvsipTM_sig_", merge_trivia, "_", current_date)
base_path_sig <- file.path(output_folder, base_name_sig)

ggsave(
  file      = paste0(base_path_sig, ".svg"),
  plot      = ptm_vs_iptm_sig,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(ptm_vs_iptm_sig, file = paste0(base_path_sig, ".rds"))

# ────────────────────────────────────────────────────────────────────────────────
# 🖼 Generate and Save Additional TOP (best ranking_score per job) Plots (raw + sigmoidal)
# ────────────────────────────────────────────────────────────────────────────────

# Select ONLY the data points associated with the highest ranking_score per AF3 prediction job
# (grouped by run_id + job_folder; with_ties=FALSE ensures one point per job)
Conf_scores_top <- Conf_scores %>%
  dplyr::group_by(run_id) %>%
  dplyr::slice_max(order_by = ranking_score, n = 1, with_ties = FALSE) %>%
  dplyr::ungroup()

# Save the top-ranked subset as CSV for reference (with timestamp to avoid overwriting)
timestamp <- format(Sys.time(), "%H%M")
write_csv(Conf_scores_top, file = file.path(output_folder, paste0("Conf_scores_top_", timestamp, ".csv")))  

# Keep the exact same Fill_* mapping as in the full plot
fill_map <- Data_plot %>%
  dplyr::distinct(Sample, Fill_box, Fill_point, Fill_mean)

Data_plot_top <- Conf_scores_top %>%
  dplyr::left_join(fill_map, by = "Sample") %>%
  dplyr::arrange(Sample)

# TOP 1) Untransformed pTM vs ipTM (linear axes), different point style as requested
ptm_vs_iptm_raw_top <- plot_fun(
  Data_plot_top,
  x        = "ptm",
  y        = "iptm",
  x_title  = "pTM score",
  y_title  = "ipTM score",
  use_sigmoid_ticks = FALSE,
  f = f,
  alpha_val = 1.0,
  size_val  = 1.5,
  starstroke_val = 0.5
)

base_name_raw_top <- paste0("P5_pTMvsipTM_raw_", merge_trivia, "_", current_date, "_top")
base_path_raw_top <- file.path(output_folder, base_name_raw_top)

ggsave(
  file      = paste0(base_path_raw_top, ".svg"),
  plot      = ptm_vs_iptm_raw_top,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(ptm_vs_iptm_raw_top, file = paste0(base_path_raw_top, ".rds"))

# TOP 2) Sigmoid-transformed plot:
# IMPORTANT: uses the SAME ptm_center / iptm_center as the full plot, so overlays align.
ptm_vs_iptm_sig_top <- plot_fun(
  Data_plot_top,
  x        = "ptm_sig",
  y        = "iptm_sig",
  x_title  = "pTM score",
  y_title  = "ipTM score",
  use_sigmoid_ticks = TRUE,
  f = f,
  alpha_val = 1.0,
  size_val  = 1.5,
  starstroke_val = 0.5
)

base_name_sig_top <- paste0("P5_pTMvsipTM_sig_", merge_trivia, "_", current_date, "_top")
base_path_sig_top <- file.path(output_folder, base_name_sig_top)

ggsave(
  file      = paste0(base_path_sig_top, ".svg"),
  plot      = ptm_vs_iptm_sig_top,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(ptm_vs_iptm_sig_top, file = paste0(base_path_sig_top, ".rds"))

# ────────────────────────────────────────────────────────────────────────────────
# 🎛 Legend-only plot for Seed ↔ starshape mapping
# ────────────────────────────────────────────────────────────────────────────────

# Use the same seed order as in the plots
legend_data <- tibble::tibble(
  seed = factor(seed_levels, levels = seed_levels)
)

legend_plot <- ggplot(legend_data, aes(x = 1, y = 1, starshape = seed)) +
  geom_star(
    size  = 3,
    fill  = "grey70",
    color = "#000000",
    starstroke = 0.5
  ) +
  scale_starshape_manual(
    limits = seed_levels,
    values = star_shapes
  ) +
  guides(
    starshape = guide_legend(title = "Seed")
  ) +
  theme_void() +
  theme(
    legend.position   = "right",
    legend.title      = element_text(size = 8, family = "dejavu"),
    legend.text       = element_text(size = 6, family = "dejavu"),
    legend.key.size   = grid::unit(0.4, "cm"),
    legend.spacing.y  = grid::unit(0.1, "cm")
  )

# extract legend as a grob
legend_only <- cowplot::get_legend(legend_plot)

# wrap legend grob in a ggplot object
legend_gg <- cowplot::ggdraw(legend_only)

# save legend as separate SVG
legend_name <- paste0("P5_legend_seed_starshape_", merge_trivia, "_", current_date, ".svg")
ggsave(
  file      = file.path(output_folder, legend_name),
  plot      = legend_gg,
  width     = 4,      # tweak as needed
  height    = 6,
  unit      = "cm",
  limitsize = FALSE
)

# ────────────────────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────────────────────
message("✅ pTM vs ipTM plots saved to: ", output_folder)