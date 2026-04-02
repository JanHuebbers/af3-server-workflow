# src/R/03.03_LoadConfig.R

# ────────────────────────────────────────────────────────────────────────────────
# 📄 Load Configuration
# ────────────────────────────────────────────────────────────────────────────────
config_path <- args[1]
if (!file.exists(config_path)) {
  stop("❌ Config file not found: ", config_path)
}
# load yaml if not already
if (!requireNamespace("yaml", quietly=TRUE)) {
  stop("Please install the yaml package")
}
params <- yaml::read_yaml(config_path)

# derive run_name and simID
run_name <- tools::file_path_sans_ext(basename(config_path))
# expecting “RunXXXX_YYYY-MM-DD_…” 
simID <- sub("^Run(\\d{4})_.*$", "\\1", run_name)

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

# ────────────────────────────────────────────────────────────────────────────────
# 📊 Assign Parameters from Config
# ────────────────────────────────────────────────────────────────────────────────
WiP1            <- params$WiP1  %||% 10
HiP1            <- params$HiP1  %||% 8
WiP2            <- params$WiP2  %||% 10
sep             <- params$sep   %||% ","
ItalChars       <- params$ItalChars %||% 2

ProtNames       <- params$ProtNames %||% list()

at <- params$AxisTitle %||% ""
axis_title_expr <- tryCatch(as.expression(parse(text = at)), error = function(e) expression(""))

FacetTitles_raw <- params$FacetTitles %||% list()
FacetTitles <- unlist(FacetTitles_raw)




