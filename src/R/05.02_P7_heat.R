# src/R/05.02_P7_heat.R
# Heatmap: mean ipTM per MLO (y) × EXO70 (x) pair from mergemerge CSV.

# ────────────────────────────────────────────────────────────────────────────────
# Parse argument, load packages/theme **and** config+params
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) stop("Usage: Rscript 05.02_P7_heat.R <config.yml>")

# pulls in packages/theme/helpers + 05.01_LoadMergemergeConfig.R
source("src/R/05.00_RunMergemergeSetup.R")

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Import Confidence Scores (CSV)
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("Mergemerge", merge_trivia, "model_confidences.csv")
if (!file.exists(Path_import)) stop("❌ CSV file not found: ", Path_import)

Conf_scores <- readr::read_csv(Path_import, show_col_types = FALSE)

# Require minimum columns
req <- c("mapping", "iptm")
miss <- setdiff(req, names(Conf_scores))
if (length(miss)) stop("❌ Missing required columns in CSV: ", paste(miss, collapse = ", "))

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup Output Directory (date folder + timestamped exports)
# ────────────────────────────────────────────────────────────────────────────────
current_date <- as.character(Sys.Date())
timestamp    <- format(Sys.time(), "%H%M")

base_dir <- file.path("Mergemerge", merge_trivia)
output_folder <- file.path(base_dir, current_date)
dir.create(output_folder, recursive = TRUE, showWarnings = FALSE)

message("📁 Output folder: ", output_folder)

# Save input snapshot (useful for debugging/repro)
readr::write_csv(
  Conf_scores,
  file = file.path(output_folder, paste0("Conf_scores_", timestamp, ".csv"))
)

# ────────────────────────────────────────────────────────────────────────────────
# 🧭 Assign x/y bins from `mapping` using wildcard patterns (Px/Py)
# ────────────────────────────────────────────────────────────────────────────────
# Px: named wildcard patterns for x axis letters (names(Px) == names(Lx))
# Py: named wildcard patterns for y axis letters (names(Py) == names(Ly))

wild_to_regex <- function(pat) {
  # escape regex metacharacters except '*'
  esc <- gsub("([.\\^$+?()\\[\\]{}|\\\\])", "\\\\\\1", pat, perl = TRUE)
  rx  <- gsub("\\*", ".*", esc, perl = TRUE)
  paste0("^", rx, "$")
}

match_letter <- function(mapping_vec, patterns_named) {
  pats <- patterns_named
  rx   <- vapply(pats, wild_to_regex, character(1))

  # specificity score = number of non-wildcard characters
  spec <- nchar(gsub("\\*", "", pats))

  vapply(mapping_vec, function(m) {
    if (is.na(m) || !nzchar(m)) return(NA_character_)
    hits <- names(pats)[vapply(rx, function(r) grepl(r, m, perl = TRUE), logical(1))]

    if (length(hits) == 0) return(NA_character_)
    if (length(hits) == 1) return(hits)

    # choose the most specific (longest fixed part)
    hits[which.max(spec[hits])]
  }, character(1))
}

Conf_scores <- Conf_scores %>%
  dplyr::mutate(
    x_bin = match_letter(as.character(mapping), Px),
    y_bin = match_letter(as.character(mapping), Py)
  )

# Save unmatched/ambiguous rows for debugging
dropped <- Conf_scores %>% dplyr::filter(is.na(x_bin) | is.na(y_bin))
if (nrow(dropped) > 0) {
  message("⚠️ Dropping rows that don't match exactly one x and one y pattern: ", nrow(dropped))
  readr::write_csv(dropped, file.path(output_folder, paste0("dropped_unmatched_", timestamp, ".csv")))
}

Data_used <- Conf_scores %>%
  dplyr::filter(!is.na(x_bin), !is.na(y_bin)) %>%
  dplyr::mutate(
    x_bin = factor(x_bin, levels = names(Lx)),
    y_bin = factor(y_bin, levels = names(Ly))
  )

# ────────────────────────────────────────────────────────────────────────────────
# 📊 Summarise mean ipTM per y×x cell (9×10 = 90 cells)
# ────────────────────────────────────────────────────────────────────────────────
data_hm <- Data_used %>%
  dplyr::group_by(y_bin, x_bin) %>%
  dplyr::summarise(
    mean = mean(iptm, na.rm = TRUE),
    sd   = stats::sd(iptm, na.rm = TRUE),
    n    = dplyr::n(),
    .groups = "drop"
  )

# Complete full grid so you always get all combinations
full_grid <- tidyr::expand_grid(
  y_bin = factor(names(Ly), levels = names(Ly)),
  x_bin = factor(names(Lx), levels = names(Lx))
)

data_hm <- full_grid %>%
  dplyr::left_join(data_hm, by = c("y_bin", "x_bin"))

message("✅ Heatmap grid: ", length(Ly), " × ", length(Lx), " = ", length(Ly) * length(Lx), " cells")

# Export summaries
readr::write_csv(
  data_hm,
  file = file.path(output_folder, paste0("P7_heat_meaniptm_long_", timestamp, ".csv"))
)

mat_wide <- data_hm %>%
  dplyr::select(y_bin, x_bin, mean) %>%
  tidyr::pivot_wider(names_from = x_bin, values_from = mean)

readr::write_csv(
  mat_wide,
  file = file.path(output_folder, paste0("P7_heat_meaniptm_matrix_", timestamp, ".csv"))
)

# ────────────────────────────────────────────────────────────────────────────────
# 🎨 Heatmap plotting function (Ly rows, Lx columns)
# ────────────────────────────────────────────────────────────────────────────────
plot_heatmap <- function(df, x = "x_bin", y = "y_bin") {
  ggplot2::ggplot(df, ggplot2::aes(x = .data[[x]], y = .data[[y]])) +
    ggplot2::geom_tile(ggplot2::aes(fill = mean), color = "#000000", linewidth = 0.25) +
    ggplot2::geom_text(
      ggplot2::aes(label = ifelse(is.na(mean), "", sprintf("%.2f", mean))),
      color = "white", size = 2.2
    ) +
    ggplot2::scale_x_discrete(
      labels = Lx,
      limits = names(Lx),
      expand = c(0, 0),
      name = NULL
    ) +
    ggplot2::scale_y_discrete(
      labels = Ly,
      limits = rev(names(Ly)),
      expand = c(0, 0),
      name = NULL
    ) +
    ggplot2::scale_fill_gradientn(
      colours  = c("#0098A1", "#00B1B7", "#FABE50", "#F6A800"),
      values   = c(0, 0.1, 0.5, 1.0),
      oob      = scales::squish,
      na.value = "white"
    ) +
    ggplot2::coord_cartesian() +
    ggplot2::guides(fill = "none")
}

P7_heat <- plot_heatmap(data_hm, x = "x_bin", y = "y_bin")

# ────────────────────────────────────────────────────────────────────────────────
# 💾 Save plot as .svg and .rds (timestamped)
# ────────────────────────────────────────────────────────────────────────────────
svg_name <- paste0("P7_heat_", merge_trivia, "_", current_date, ".svg")
rds_name <- paste0("P7_heat_", merge_trivia, "_", current_date, ".rds")

ggplot2::ggsave(
  filename  = file.path(output_folder, svg_name),
  plot      = P7_heat,
  width     = SLw,
  height    = SLh,
  units     = "cm",
  limitsize = FALSE
)

saveRDS(
  object = P7_heat,
  file   = file.path(output_folder, rds_name)
)

message("✅ Saved: ", file.path(output_folder, svg_name))
message("✅ Saved: ", file.path(output_folder, rds_name))
message("✅ Done.")
