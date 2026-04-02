# Make first n letters italic in axis labels (supports lookup via named list/env)
label_italic_prefix <- function(keys, lookup = NULL, n = 2L) {
  stopifnot(is.numeric(n), n >= 0)
  lapply(keys, function(key) {
    # Resolve label via lookup (e.g., ProtNames[["AtMLO6"]] -> "AtMLO6.1")
    full <- if (is.null(lookup)) key else { val <- lookup[[key]]; if (is.null(val)) key else val }
    if (is.na(full)) return(quote(NA))
    full <- as.character(full)
    
    first <- substr(full, 1L, n)
    rest  <- if (nchar(full) > n) substr(full, n + 1L, nchar(full)) else ""
    
    # expression: italic(first) * plain(rest)
    bquote(italic(.(first)) * plain(.(rest)))
  })
}