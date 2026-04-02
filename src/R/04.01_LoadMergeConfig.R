# src/R/04.01_LoadMergeConfig.R
# Reads YAML config into `params`, sets your usual variables, color vectors,
# and provides `apply_exclusions(df)`.

# ---- args & YAML -------------------------------------------------------------
if (!exists("args")) args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 1)
config_path <- args[1]
if (!file.exists(config_path)) stop("❌ Config file not found: ", config_path)

params <- yaml::read_yaml(config_path)

# ---- helpers (safe getters + defaults) --------------------------------------
`%||%` <- function(x, y) if (is.null(x) || length(x) == 0) y else x
get_in <- function(x, keys, default = NULL) {
  out <- x
  for (k in keys) {
    if (is.null(out) || is.null(out[[k]])) return(default)
    out <- out[[k]]
  }
  out
}

# ---- assign the parameters you already use ----------------------------------
merge_trivia    <- params$merge_name %||% tools::file_path_sans_ext(basename(config_path))
alpha           <- params$alpha %||% 0.05
WiP1            <- params$WiP1  %||% 10
HiP1            <- params$HiP1  %||% 8
sep             <- params$sep   %||% ","
ItalChars       <- params$ItalChars %||% 2

# Optional: still read ProtNames if you want them for axis labels
ProtNames       <- params$ProtNames %||% list()
axis_title_expr <- tryCatch(
  eval(parse(text = params$AxisTitle %||% '""')),
  error = function(e) quote("")
)

# ✅ Minimal addition: FacetTitles (plotmath strings for label_parsed)
FacetTitles_raw <- params$FacetTitles %||% list()
FacetTitles     <- unlist(FacetTitles_raw)

# ---- colors (recycle/trim to S) ---------------------------------------------
# S = number of samples for colour vectors.
# Prefer length(ProtNames), then length(Colors$Point), fallback to 1.
colors_point <- get_in(params, c("Colors", "Point"), character())

raw_S <- c(
  length(ProtNames),
  length(colors_point)
)

S <- max(c(raw_S, 1L), na.rm = TRUE)

box_col    <- rep(get_in(params, c("Colors","Box","default"), "#FFFFFF"), S)
point_col  <- rep_len(colors_point, S)
mpoint_col <- rep_len(get_in(params, c("Colors","MPoint"), character()), S)

names(box_col)    <- paste0("Box_",    seq_len(S))
names(point_col)  <- paste0("Point_",  seq_len(S))
names(mpoint_col) <- paste0("MPoint_", seq_len(S))

f <- c(box_col, point_col, mpoint_col)

# ---- exclusions parsed from YAML --------------------------------------------
# Supported keys:
#   params$exclude$job_ids           e.g., ["01"]  -> drop first job across runs
#   params$exclude$models            e.g., [1]     -> drop model_index 1
drop_job_ids <- get_in(params, c("exclude","job_ids"),          character())
drop_models  <- as.integer(get_in(params, c("exclude","models"), integer()))

apply_exclusions <- function(df) {
  if (!is.data.frame(df) || nrow(df) == 0L) return(df)

  # Derive job_id if missing, using second underscore-separated token of job_folder
  if (!"job_id" %in% names(df)) {
    if (!"job_folder" %in% names(df)) {
      stop("apply_exclusions: 'job_id' not present and 'job_folder' missing; cannot derive job_id.")
    }
    tmp <- tidyr::separate_wider_delim(
      df,
      "job_folder",
      names = c("sim_id__", "job_id__", "seed__", "rest__"),
      delim = "_",
      too_many = "merge",
      cols_remove = FALSE
    )
    df$job_id <- tmp$job_id__
  }

  # Normalize types / missing values
  df$job_id <- stringr::str_pad(
    tidyr::replace_na(df$job_id, ""),
    width = 2, pad = "0"
  )

  if ("model_index" %in% names(df)) {
    suppressWarnings(df$model_index <- readr::parse_integer(df$model_index))
  } else {
    df$model_index <- NA_integer_
  }

  # Apply exclusions, but KEEP rows where the key is NA (only drop definite matches)
  if (length(drop_job_ids)) {
    df <- dplyr::filter(df, is.na(job_id) | !(job_id %in% drop_job_ids))
  }
  if (length(drop_models)) {
    df <- dplyr::filter(df, is.na(model_index) | !(model_index %in% drop_models))
  }

  df
}

# Echo
message("✅ Config loaded: ", normalizePath(config_path))
message("   merge_trivia: ", merge_trivia)
if (length(drop_job_ids)) message("   exclude.job_ids: ", paste(drop_job_ids, collapse = ", "))
if (length(drop_models))  message("   exclude.models: ", paste(drop_models, collapse = ", "))