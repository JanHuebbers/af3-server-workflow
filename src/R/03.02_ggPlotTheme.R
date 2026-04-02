# src/R/03.02_ggPlotTheme.R
# Register full DejaVu Sans font family with all styles
font_add("ubuntu",
         regular = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
         bold = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
         italic = "/usr/share/fonts/truetype/ubuntu/Ubuntu-RI.ttf",
         bolditalic = "/usr/share/fonts/truetype/ubuntu/Ubuntu-BI.ttf")

showtext_auto()

# Set base theme
theme_set(
  theme_light(
    base_size = 8,
    base_family = "dejavu"  # Explicit family
  )
)

# Update theme
theme_update(
  rect = element_rect(fill = "transparent"),
  plot.background = element_blank(),
  panel.grid = element_blank(),
  panel.border = element_blank(),
  panel.background = element_rect(fill = "transparent", color = NA),
  strip.background = ggplot2::element_rect(
        fill   = "white",
        colour = "black",
        linewidth = 1),
  strip.text = ggplot2::element_text(
        size   = 8,
        colour = "black",
        face   = "bold"
      ),
  legend.background = element_rect(fill = "transparent", linetype = "blank"),
  legend.box.background = element_rect(fill = "transparent", linetype = "blank"),
  legend.title = element_blank(),
  legend.text.align = 0,
  legend.key = element_rect(colour = "transparent", fill = "white"),
  legend.position = "bottom",
  axis.title.x = element_text(
    size = 7, face = "bold", family = "dejavu", color = "black", vjust = 0.5, hjust = 0.5),
  axis.title.y = element_text(
    size = 7, face = "bold", family = "dejavu", color = "black", vjust = 0.5, hjust = 0.5),
  axis.text.x = element_text(
    size = 6, family = "dejavu", hjust = 1.0, angle = 45),
  axis.text.y = element_text(
    size = 6, family = "dejavu", face = "plain"),
  axis.line = element_line(
    color = "black", lineend = "round", linetype = "solid", linewidth = 0.5),
  axis.ticks = element_line(
    color = "black", linewidth = 0.5, lineend = "round")
)
