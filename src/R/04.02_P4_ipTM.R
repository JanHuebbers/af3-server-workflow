# src/R/04.02_P4_ipTM_comp.R

# ────────────────────────────────────────────────────────────────────────────────
# Parse argument, load packages/theme **and** config+params+simID
# ────────────────────────────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1) stop("Usage: Rscript 04.02_P4_ipTM_comp.R <config.yml>")
# this next line pulls in 04.00_RunMergeSetup.R which in turn sources your loader
source('src/R/04.00_RunMergeSetup.R')

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
    delim = "_", too_many = "merge", cols_remove = FALSE
  ) %>%
dplyr::mutate(
    job_id      = stringr::str_pad(as.character(job_id), width = 2, pad = "0"),
    # SAFE coercion (works for numeric/character/factor):
    model_index = suppressWarnings(as.integer(model_index))
  ) %>%
  # YAML-driven filters (no-ops if vectors are empty)
  { if (length(drop_job_ids)) dplyr::filter(., !(job_id %in% drop_job_ids)) else . } %>%
  { if (length(drop_models))  dplyr::filter(., !(model_index %in% drop_models)) else . } %>%
  dplyr::relocate(ID, .after = run_id) %>%
  dplyr::relocate(Sample, .after = ID)

# Make sure Sample is an ordered factor
if ("Sample" %in% names(Conf_scores)) {
  Conf_scores <- Conf_scores %>%
    dplyr::mutate(Sample = factor(Sample, levels = sort(unique(Sample))))
}

# ────────────────────────────────────────────────────────────────────────────────
# 📁 Setup Output Directory
# ────────────────────────────────────────────────────────────────────────────────
current_date <- Sys.Date()
base_dir <- "Merge"
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
# 💾 Export Processed Data
# ────────────────────────────────────────────────────────────────────────────────
timestamp <- format(Sys.time(), "%H%M")
write_csv(Conf_scores, file = file.path(output_folder, paste0("Conf_scores_", timestamp, ".csv")))

# ────────────────────────────────────────────────────────────────────────────────
# 📊 Summary
# ────────────────────────────────────────────────────────────────────────────────
S <- dplyr::n_distinct(Conf_scores$Sample)  # Number of different input chain combinations
E <- n_distinct(Conf_scores$seed) # Number of different seeds

message("✅ Data preapred: ", S, " input chain combinations ", E, " seeds ")

# ────────────────────────────────────────────────────────────────────────────────
# 📊 Statistics
# ────────────────────────────────────────────────────────────────────────────────
# Descriptive statistics
data_desc <- describeBy(Conf_scores$iptm, list(Conf_scores$seed, Conf_scores$Sample), mat = TRUE) %>%
  as_tibble() %>%
  select(group1, group2, mean, sd) %>%
  mutate(ID = row_number()) %>%
  rename(c(seed = group1, Sample = group2)) %>%
  relocate(ID, .before = seed) %>%
  na.omit() %>% 
  arrange(seed)

# Frequentist statistics
# Test for normal distribution and homogeneity of variances
# Levene-Test
data_levene <- data_desc %>%
  levene_test(`mean` ~ Sample) %>%
  transmute(lev_stat = statistic, lev_df1 = df1, lev_df2 = df2, p_levene = p)
#Shapiro-Wilk-Test
data_shapiro <- data_desc %>%
  group_by(Sample) %>%
  shapiro_test(`mean`) %>%
  ungroup() %>%
  transmute(Sample, p_shapiro = p, W = statistic)

data_norm <- data_shapiro %>%
  mutate(p_levene = data_levene$p_levene)

non_Norm <- data_norm %>% 
  filter(p_shapiro <= 0.05)

#Pairwise t-Test (~pairwise.t.test) or Mann Whitney U Test (~pairwise.wilcox.test) to assess differences among samples
posthoc_q <- data_desc %>%
  group_by() %>% 
  nest() %>%
  mutate(posthoc = map(.x = data, ~pairwise.wilcox.test(x = .x$mean, g = .x$Sample, p.adjust.method = "fdr", alternative = "two.sided", data = .x, paired = FALSE, exact = TRUE))) %>% 
  mutate(pV = map(.x = posthoc, ~tri.to.squ(.x$p.value))) %>% 
  mutate(pVal = map(.x = pV, ~data.matrix(.x))) %>%
  mutate(q = map(.x = pVal, ~tibble::as_tibble(.x, rownames = NA))) %>%
  mutate(q = map(.x = q, ~rownames_to_column(.x, var = "Sample")))

letters <- posthoc_q %>%
  mutate(letter = map(.x = pVal, ~multcompLetters(.x, compare = "<", threshold = alpha, reversed = FALSE))) %>%
  mutate(letter = map(.x = letter, ~data.frame(.x$Letters))) %>%
  select(letter) %>% 
  tidyr::unnest(cols = c(letter)) %>%
  ungroup()

asterisks <- data_desc %>%
  group_by(Sample) %>%
  summarise(ypos = max(`mean`, na.rm = TRUE), .groups = "drop") %>%
  mutate(letters = letters$.x.Letters) %>% 
  # Attach ProtNames from the CSV (one per Sample)
  left_join(
    Conf_scores %>% dplyr::distinct(Sample, ProtNames),
    by = "Sample"
  )

stats_sum <- data_norm %>%
  left_join(asterisks, by = "Sample") %>%
  relocate(ProtNames, .after = Sample)

#Save as csv (Note: sep = "," in lab and sep = ";" at home)
write.table(stats_sum, file = file.path(output_folder, "stats_sum.csv"), row.names = FALSE, sep = sep)
write.table(data_desc, file = file.path(output_folder, "descriptive_stats.csv"), row.names = FALSE, sep = sep)

# ────────────────────────────────────────────────────────────────────────────────
# 📈 Plotting data arrangement and function
# ────────────────────────────────────────────────────────────────────────────────
#Specify Box colors
Fill_box <- rep(paste0("Box_", 1:S), 1)
Fill_point <- rep(paste0("Point_", 1:S), 1)
Fill_mean <- rep(paste0("MPoint_", 1:S), 1)

#The final data frame for plotting, including the original data, letters for stats. and y-axis positions that can be used to position of letters
Data_plot <- Conf_scores %>%
  arrange(Sample) %>%  
  group_by(Sample) %>%
  nest() %>%
  add_column(Fill_box) %>%
  add_column(Fill_point) %>%
  add_column(Fill_mean) %>%
  unnest() %>% 
  ungroup()

# X-axis order = Sample order
Lx <- levels(Data_plot$Sample)
if (is.null(Lx)) {
  Lx <- unique(Data_plot$Sample)
}

# Precompute expression labels for Samples and bake into plot
# Build lookup Sample -> ProtNames from the merged CSV
lookup <- Conf_scores %>%
  dplyr::distinct(Sample, ProtNames) %>%
  dplyr::arrange(Sample) %>%
  { stats::setNames(.$ProtNames, .$Sample) }

labs_sample_expr <- label_italic_prefix(Lx, lookup = lookup, n = ItalChars)
names(labs_sample_expr) <- Lx

# Function for a plot that depicts the probability distribution of all replicates as violin plot. 
# The mean values of the individual technical replicates are shown as large data points and represent independent runs or experiments.
plot_fun <- function(data, x, y, xlab, xlim, f) {
  ggplot(data = data, aes(x = .data[[x]], y = .data[[y]])) +
    geom_violin(alpha = 0.8, width = 0.75, position = position_dodge(width = 0.75), scale = "width", size = 0.4, color = "#000000", aes(fill = Fill_box)) +
    # geom_star(aes(starshape = seed, size = seed, fill = Fill_point), alpha = 0.50, color = "#000000", stroke = 0.3, position = position_nudge(x = c(-0.20, -0.15, 0.15, 0.20))) +
    stat_summary(color = "#000000", geom = "crossbar", linewidth = 0.5, fun = median, position = position_dodge(width = 0.0), width = 0.70) +
    stat_summary(aes(starshape = seed, fill = Fill_mean), color = "#000000", geom = "star", size = 1.3, alpha = 0.80, fun = mean, position = position_dodge(width = 0.5)) +
    geom_text(
      data = asterisks,
      aes(x = Sample, y = 0.0, label = letters),
      inherit.aes = FALSE, size = 2.5, angle = 90, hjust = 0.0
    ) +
    #Setup plot design
    scale_x_discrete(
      labels = labs_sample_expr,  # <- baked labels
      limits = xlim,
      name   = axis_title_expr
    ) +
    scale_y_continuous(
      breaks = seq(0.0, 1.00, 0.1),
      limits = c(-0.05, 1.05),
      name = "ipTM score",
      expand = c(0.001, 0.001)
    ) +
    scale_color_manual(values = f) + 
    scale_fill_manual(values = f) +
    scale_starshape_manual(
      limits = c("1710", "1711", "1712", "1701", "1702", "1703", "1704", "1705", "1706", "1707", "1708", "1709"),
      values = c(15, 13, 28, 11, 23, 1, 2, 4, 5, 29, 24, 27)
    ) +  
    scale_size_manual(
      limits = c("1710", "1711", "1712", "1701", "1702", "1703", "1704", "1705", "1706", "1707", "1708", "1709"),
      values = c(rep((0.8), 12))
    ) +
    guides(fill = "none", color = "none", size = "none", shape = "none", starshape = "none", alpha = "none")
}

# ────────────────────────────────────────────────────────────────────────────────
# 🖼 Generate and Save Plot
# ────────────────────────────────────────────────────────────────────────────────
violin <- plot_fun(Data_plot, x = "Sample", y = "iptm", xlim = Lx, f = f)

svg_name <- paste0("P4_Score_", merge_trivia, "_", current_date, ".svg")
ggsave(
  file      = file.path(output_folder, svg_name),
  plot      = violin,
  width     = WiP1,
  height    = HiP1,
  unit      = "cm",
  limitsize = FALSE
)

rds_name <- paste0("P4_Score_", merge_trivia, "_", current_date, ".rds")
saveRDS(violin, file = file.path(output_folder, rds_name))


# ────────────────────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────────────────────