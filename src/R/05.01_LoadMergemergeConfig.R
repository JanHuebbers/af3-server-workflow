# src/R/05.01_LoadMergemergeConfig.R
# Reads YAML config into `params`, sets variables for Module 5 heatmaps:
# - merge_trivia, out_dir, SLw/SLh
# - Lx/Ly: named vectors for axis labels (names = letters, values = prot_name)
# - Px/Py: named vectors for wildcard mapping patterns (names = letters, values = pattern)
#
# Expects config keys:
#   merge_name: "AtMLOvsAtEXO70"
#   merges: ["AtMLO1vsAtEXO70", ...]   # not used here but kept in params
#   y_axis: { A: {mapping: "1atmlo4*", prot_name: "AtMLO4"}, ... }
#   x_axis: { A: {mapping: "*atexo70a1", prot_name: "AtEXO70A1"}, ... }
#   WiP1, HiP1, sep, ItalChars (optional)

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

# ---- core parameters ---------------------------------------------------------
merge_trivia <- params$merge_name %||% tools::file_path_sans_ext(basename(config_path))

# Output folder: prefer wrapper-provided env, else default to ./Mergemerge/<merge_name>
merge_dir <- Sys.getenv("MERGEMERGE_DIR", unset = "")
if (!nzchar(merge_dir)) {
  merge_dir <- file.path(".", "Mergemerge", merge_trivia)
}
out_dir <- normalizePath(merge_dir, winslash = "/", mustWork = FALSE)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# plotting defaults (cm)
SLw <- params$WiP1 %||% 7.5
SLh <- params$HiP1 %||% 5.5
sep <- params$sep %||% ","
ItalChars <- params$ItalChars %||% 0

# ---- axis label expressions from prot_name -----------------------------------
# Supported:
#   - "AtMLO12"     -> italic("At")*plain("MLO")*bold("12")
#   - "AtEXO70H7"   -> italic("At")*plain("EXO70")*bold("H7")
#   - "HvMlo"       -> italic("Hv")*bold("Mlo")
make_label_expr <- function(x) {

  # AtMLO12
  if (grepl("^AtMLO\\d+$", x)) {
    num <- sub("^AtMLO", "", x)
    return(bquote(italic("At")*plain("MLO")*bold(.(num))))
  }

  # HvMlo / HvMlo1 etc.
  if (grepl("^HvMlo", x)) {
    rest <- sub("^Hv", "", x)  # "Mlo", "Mlo1", ...
    return(bquote(italic("Hv")*bold(.(rest))))
  }

  # AtEXO70A1 / AtEXO70H7 etc.
  if (grepl("^AtEXO70", x)) {
    suf <- sub("^AtEXO70", "", x)
    return(bquote(italic("At")*plain("EXO70")*bold(.(suf))))
  }

  # fallback
  bquote(plain(.(x)))
}

# Build letter-keyed label vectors (names are letters A..; values are expressions)
# We use prot_name from config, NOT mapping patterns.
build_axis_maps <- function(axis_block, axis_name = "axis") {
  if (is.null(axis_block) || length(axis_block) == 0) {
    stop("❌ Config is missing '", axis_name, "' block or it is empty.")
  }
  letters <- names(axis_block)
  if (is.null(letters) || any(!nzchar(letters))) {
    stop("❌ '", axis_name, "' must be a named mapping like A:, B:, C: ...")
  }

  pat <- vapply(axis_block, function(z) as.character(z$mapping %||% ""), character(1))
  lab <- vapply(axis_block, function(z) as.character(z$prot_name %||% ""), character(1))

  if (any(!nzchar(pat))) stop("❌ Some entries in '", axis_name, "' are missing mapping patterns.")
  if (any(!nzchar(lab))) stop("❌ Some entries in '", axis_name, "' are missing prot_name labels.")

  names(pat) <- letters
  names(lab) <- letters

  # expressions
  lab_expr <- do.call("expression", lapply(lab, make_label_expr))
  names(lab_expr) <- letters

  list(P = pat, L = lab, Lex = lab_expr)
}

y_maps <- build_axis_maps(params$y_axis, "y_axis")
x_maps <- build_axis_maps(params$x_axis, "x_axis")

Py <- y_maps$P
Ly <- y_maps$Lex   # <- expressions for ggplot labels
Px <- x_maps$P
Lx <- x_maps$Lex   # <- expressions for ggplot labels

# ---- echo --------------------------------------------------------------------
message("✅ Config loaded: ", normalizePath(config_path))
message("   merge_trivia: ", merge_trivia)
message("   out_dir: ", out_dir)
message("   x_axis letters: ", paste(names(Lx), collapse = ", "))
message("   y_axis letters: ", paste(names(Ly), collapse = ", "))