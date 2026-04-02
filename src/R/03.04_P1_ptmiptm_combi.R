# src/R/03.04_P1_ptmiptm_combi.R

# ────────────────────────────────────────────────────────────────────────────────
# Parse argument, load packages/theme **and** config+params+simID
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop("Usage: Rscript 03.04_P1_ptmiptm_combi.R <config.yml>")
# this next line pulls in 03.00_RunSetup.R which in turn sources your loader
source('src/R/03.00_RunSetup.R')

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
# 🧮 Process and Annotate Confidence Data
# ────────────────────────────────────────────────────────────────────────────────
Conf_scores <- read_csv(Path_import) %>%
  arrange(job_folder, model_index) %>%
  separate_wider_delim(job_folder, names = c("JobID", "simID", "Name"),
                       delim = "_", too_many = "merge", cols_remove = FALSE) %>%
  rename(JobName = job_folder) %>%
  relocate(JobName, .before = JobID) %>%
  mutate(ID = row_number()) %>%
  group_by(JobName) %>%
  nest() %>%
  ungroup() %>%
  mutate(Sample = sapply(row_number(), int2col)) %>%
  mutate(
    mean_ptm  = map_dbl(data, ~mean(.x$ptm, na.rm = TRUE)),
    mean_iptm = map_dbl(data, ~mean(.x$iptm, na.rm = TRUE))
  ) %>%
  unnest(data, keep_empty = TRUE) %>%
  ungroup() %>%
  relocate(ID, .before = Name) %>%
  relocate(Sample, .before = Name) %>%
  mutate(
    mean_ptm_norm = mean_ptm * 0.1,
    model_index = as.factor(model_index)
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
# 💾 Export Processed Data
# ────────────────────────────────────────────────────────────────────────────────
timestamp <- format(Sys.time(), "%H%M")
write_csv(Conf_scores, file = file.path(output_folder, paste0("Conf_scores_", timestamp, ".csv")))

# ────────────────────────────────────────────────────────────────────────────────
# 📊 Summary
# ────────────────────────────────────────────────────────────────────────────────
S <- n_distinct(Conf_scores$Sample)  # Number of simulations
E <- n_distinct(Conf_scores$model_index) # Number of models

message("✅ Data prepared: ", S, " samples × ", E, " experiments.")

# ────────────────────────────────────────────────────────────────────────────────
# 📈 Plotting Function
# ────────────────────────────────────────────────────────────────────────────────
plot_fun <- function(data, x, y, xlab, min_Psize, max_Psize, xlim) {

  # Decide order of x-axis levels
  x_levels <- xlim

  # Precompute labels as expressions ONCE
  labs_expr <- label_italic_prefix(x_levels, lookup = ProtNames, n = ItalChars)
  names(labs_expr) <- x_levels   # important so scale_x_discrete knows what is what

  ggplot(data = data, aes(x = .data[[x]], y = .data[[y]])) +
    stat_summary(
      aes(fill = mean_ptm_norm, color = mean_ptm_norm, size = mean_ptm_norm),
      geom = "star", starshape = 15, alpha = 0.9, fun = "mean",
      position = position_identity()
    ) +
    geom_star(
      aes(starshape = model_index),
      alpha = 0.7, size = 0.7, color = "#000000", fill = "#646567",
      position = position_dodge(width = 0.5)
    ) +
    scale_x_discrete(
      labels = labs_expr,      # <- vector/list of expressions, no function
      limits = x_levels,
      name   = axis_title_expr,
      expand = c(0.03, 0.03)
    ) +
    scale_y_continuous(
      breaks = seq(0.0, 1.00, 0.1),
      limits = c(-0.05, 1.05),
      name   = "ipTM score",
      expand = c(0.001, 0.001)
    ) +
    scale_fill_gradientn(
      colours  = c("#006165","#2D7F83","#B65256","#A11035"),
      values   = c(0, 0.3, 0.5, 1.0),
      limits   = c(0.0, 0.1),
      na.value = "white"
    ) +
    scale_colour_gradientn(
      colours  = c("#006165","#2D7F83","#B65256","#A11035"),
      values   = c(0, 0.3, 0.5, 1.0),
      limits   = c(0.0, 0.1),
      na.value = "white"
    ) +
    scale_size_continuous(
      limits = c(0.0, 0.1),
      range  = c(min_Psize, max_Psize)
    ) +
    scale_starshape_manual(
      limits = paste0(0:4),
      values = c(15, 13, 28, 11, 23)
    ) +
    guides(
      fill = "none", color = "none", size = "none",
      shape = "none", starshape = "none", alpha = "none"
    )
}

# ────────────────────────────────────────────────────────────────────────────────
# 🖼 Generate and Save Plot
# ────────────────────────────────────────────────────────────────────────────────
Lx <- unique(Conf_scores$Sample)

plot <- plot_fun(
  Conf_scores,
  x         = "Sample",
  y         = "iptm",
  xlab      = ProtNames,
  min_Psize = 0.2,
  max_Psize = 3.5,
  xlim      = Lx
)

# Base path and name
base_name <- paste0("P1_Score_", JobID, "_", current_date)
base_path <- file.path(output_folder, base_name)

# Save SVG
ggsave(
  file   = paste0(base_path, ".svg"),
  plot   = plot,
  width  = WiP1,
  height = HiP1,
  unit   = "cm",
  limitsize = FALSE
)

# Save RDS
saveRDS(plot, file = paste0(base_path, ".rds"))
# ────────────────────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────────────────────