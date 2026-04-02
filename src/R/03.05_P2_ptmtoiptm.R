# src/R/03.05_P2_ptmtoiptm.R

# ────────────────────────────────────────────────────────────────────────────────
# Parse argument, load packages/theme **and** config+params+simID
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop("Usage: Rscript 03.05_P2_ptmtoiptm.R <config.yml>")
config_path <- args[1]
source('src/R/03.00_RunSetup.R')   # this now also runs 03.03_LoadConfig.R

# update axis text style for x-axis
theme_update(
  axis.text.x = element_text(
    size   = 6,
    family = "dejavu",
    hjust  = 1.0,
    vjust  = 0.5,
    angle  = 90
  )
)

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Import Confidence Scores
# ────────────────────────────────────────────────────────────────────────────────
Path_import <- file.path("AF3_output", simID, "model_confidences.csv")
if (!file.exists(Path_import)) {
  stop("❌ CSV file not found: ", Path_import)
}

# Convert integer to Excel-style sample ID (e.g., A, B, ..., AA, AB, ...)
int2col <- function(n) {
  if (n <= 26) {
    return(LETTERS[n])
  } else {
    first <- int2col((n - 1) %/% 26)
    second <- LETTERS[((n - 1) %% 26) + 1]
    return(paste0(first, second))
  }
}

# ────────────────────────────────────────────────────────────────────────────────
# Sigmoidal transform (centered logistic, NO min/max scaling)
# ────────────────────────────────────────────────────────────────────────────────
K_SIG <- 7  # global steepness parameter for all sigmoid transforms

sigmoid_spread <- function(x, center, k = K_SIG) {
  # center: where you want most spread (e.g. median of the scores)
  # k     : steepness; larger = more aggressive
  plogis(k * (x - center))
}


# ────────────────────────────────────────────────────────────────────────────────
# 🧮 Process and Annotate Confidence Data
# ────────────────────────────────────────────────────────────────────────────────
Conf_scores <- read_csv(Path_import) %>%
  arrange(job_folder, model_index) %>%
  separate_wider_delim(
    job_folder,
    names = c("JobID", "simID", "Name"),
    delim = "_",
    too_many = "merge",
    cols_remove = FALSE
  ) %>%
  rename(JobName = job_folder) %>%
  relocate(JobName, .before = JobID) %>%
  mutate(ID = row_number()) %>%
  group_by(JobName) %>%
  nest() %>%
  ungroup() %>%
  mutate(Sample = sapply(row_number(), int2col)) %>%
  mutate(
    mean_ptm  = map_dbl(data, ~ mean(.x$ptm,  na.rm = TRUE)),
    mean_iptm = map_dbl(data, ~ mean(.x$iptm, na.rm = TRUE))
  ) %>%
  unnest(data, keep_empty = TRUE) %>%
  ungroup() %>%
  relocate(ID, .before = Name) %>%
  relocate(Sample, .before = Name) %>%
  mutate(
    mean_ptm_norm = mean_ptm * 0.1,
    model_index   = as.factor(model_index),
    # new transformed columns: each centered on its own median
    ptm_sig  = sigmoid_spread(
      ptm,
      center = median(ptm,  na.rm = TRUE)
    ),
    iptm_sig = sigmoid_spread(
      iptm,
      center = median(iptm, na.rm = TRUE)
    )
  )

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup Output Directory
# ────────────────────────────────────────────────────────────────────────────────
JobID <- unique(Conf_scores$JobID)
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
# 📈 Plotting Function
#   - raw axes: equally spaced ticks 0..1
#   - sigmoid axes: data already ptm_sig/iptm_sig,
#     ticks at sigmoid_spread(raw breaks, median), labels = raw breaks
# ────────────────────────────────────────────────────────────────────────────────

breaks_raw  <- seq(0.0, 1.0, 0.2)
labels_raw  <- sprintf("%.1f", breaks_raw)   # "0.0", "0.1", ..., "1.0"

plot_fun <- function(data,
                     x, y,
                     xlab, min_Psize, max_Psize, xlim,
                     x_title = "x score",
                     y_title = "y score",
                     use_sigmoid_ticks = FALSE,
                     k = K_SIG) {

  p <- ggplot(data = data, aes(x = .data[[x]], y = .data[[y]])) +
    geom_star(
      aes(
        # 1️⃣ starshape now corresponds to Sample
        starshape = Sample,
        # keep fill as numeric for the gradient
        fill      = as.numeric(factor(Sample))
      ),
      alpha    = 0.3,
      size     = 1.0,
      color    = "#000000"
      # , position = position_jitter(width = 0.05, height = 0.05)
    ) +
    scale_fill_gradientn(
      colours  = c("#0098A1", "#F6A800"),
      na.value = "white"
    ) +
    scale_starshape_manual(
      values = c(15, 13, 28, 11, 23, 1, 2, 4, 5, 29, 24, 27,
                3, 6, 7, 8, 9, 10, 12, 14, 16, 17, 18, 19,
                20, 21, 22, 25, 26, 30)
    ) +
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

    x_center <- median(data$ptm,  na.rm = TRUE)
    y_center <- median(data$iptm, na.rm = TRUE)

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
# 🖼 Generate and Save Plots (raw + sigmoidal axes)
# ────────────────────────────────────────────────────────────────────────────────

# 1) Untransformed pTM vs ipTM (linear axes)
plot_raw <- plot_fun(
  Conf_scores,
  x          = "ptm",
  y          = "iptm",
  xlab       = ProtNames,
  min_Psize  = 0.2,
  max_Psize  = 3.5,
  xlim       = NULL,   # not used in function, so can be NULL
  x_title    = "pTM score",
  y_title    = "ipTM score",
  use_sigmoid_ticks = FALSE
)

base_name_raw <- paste0("P2_pTMvsipTM_raw_", JobID, "_", current_date)
base_path_raw <- file.path(output_folder, base_name_raw)

ggsave(
  file      = paste0(base_path_raw, ".svg"),
  plot      = plot_raw,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(plot_raw, file = paste0(base_path_raw, ".rds"))

# 2) Sigmoid-transformed plot:
#    - data: ptm_sig / iptm_sig (per-axis centered at their own medians)
#    - ticks: positions = sigmoid_spread(raw breaks, per-axis median)
#             labels    = raw breaks (0.0, 0.1, ..., 1.0)
#             limits    = c(-0.05, 1.05) as in raw plot
plot_sig <- plot_fun(
  Conf_scores,
  x          = "ptm_sig",
  y          = "iptm_sig",
  xlab       = ProtNames,
  min_Psize  = 0.2,
  max_Psize  = 3.5,
  xlim       = NULL,
  x_title    = "pTM score",
  y_title    = "ipTM score",
  use_sigmoid_ticks = TRUE
)

base_name_sig <- paste0("P2_pTMvsipTM_sig_", JobID, "_", current_date)
base_path_sig <- file.path(output_folder, base_name_sig)

ggsave(
  file      = paste0(base_path_sig, ".svg"),
  plot      = plot_sig,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

saveRDS(plot_sig, file = paste0(base_path_sig, ".rds"))

# ────────────────────────────────────────────────────────────────────────────────
# 🎛 Legend-only plot for Sample ↔ starshape mapping
# ────────────────────────────────────────────────────────────────────────────────
library(cowplot)  # make sure this is available

# Use unique Samples so the legend has one entry per Sample
legend_data <- Conf_scores %>%
  dplyr::distinct(Sample)

legend_plot <- ggplot(legend_data, aes(x = 1, y = 1, starshape = Sample)) +
  geom_star(
    size  = 3,
    fill  = "grey60",
    color = "#000000"
  ) +
  # same shape mapping as in plot_fun
  scale_starshape_manual(
    values = c(
      15, 13, 28, 11, 23, 1, 2, 4, 5, 29, 24, 27,
       3,  6,  7,  8,  9,10,12,14,16,17,18,19,
      20, 21, 22, 25, 26,30
    )
  ) +
  guides(
    starshape = guide_legend(title = "Sample")
  ) +
  theme_void() +
  theme(
    legend.position   = "right",
    legend.title      = element_text(size = 8, family = "dejavu"),
    legend.text       = element_text(size = 6, family = "dejavu"),
    legend.key.size   = unit(0.4, "cm"),
    legend.spacing.y  = unit(0.1, "cm")
  )

# extract legend as a grob
legend_only <- cowplot::get_legend(legend_plot)

# wrap legend grob in a ggplot object
legend_gg <- cowplot::ggdraw(legend_only)

# save legend as separate SVG
legend_name <- paste0("P2_legend_Sample_starshape_", JobID, "_", current_date, ".svg")
ggsave(
  file      = file.path(output_folder, legend_name),
  plot      = legend_gg,
  width     = 4,      # adjust as you like
  height    = 6,
  unit      = "cm",
  limitsize = FALSE
)

# ────────────────────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────────────────────