---
name: Consumo eléctrico por distribuidora — Panamá
description: A grid dispatch control room for ASEP distributor data; a raised control desk drives an operations wall.
colors:
  wall-ground: "#0E1417"
  wall-panel: "#16212A"
  wall-panel-raised: "#1C2933"
  panel-rule: "#2C3C48"
  chart-grid: "#25333E"
  ink: "#EEF2F3"
  ink-secondary: "#B0BEC7"
  ink-tertiary: "#93A3AE"
  busbar: "#C9D4DA"
  edemet-blue: "#3987e5"
  ensa-orange: "#d95926"
  edechi-green: "#199e70"
  effect-clients-violet: "#9085e9"
  effect-consumption-magenta: "#e0609a"
  lamp-amber: "#F0B13A"
  amber-ink: "#F3C766"
  lamp-green: "#3DCB7A"
  lamp-red: "#E5534B"
  lamp-off: "#3B4952"
  instrument-well: "#090E11"
  desk-face: "#2D3D48"
  desk-face-low: "#22303A"
  desk-ink: "#EEF2F3"
  desk-ink-secondary: "#B7C5CD"
  log-paper: "#ECE8DE"
  log-panel: "#FAF8F3"
  log-ink: "#151A1D"
typography:
  display:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "50px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.005em"
  headline:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "31px"
    fontWeight: 500
    lineHeight: 1.22
  title:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0.01em"
  readout:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "27px"
    fontWeight: 600
    lineHeight: 1.1
  body:
    fontFamily: "Barlow, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "tnum"
  label:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.1em"
  engraved:
    fontFamily: "Barlow Condensed, Arial Narrow, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.14em"
rounded:
  wall: "3px"
  control: "4px"
  pushbutton: "6px"
spacing:
  desk-gutter: "24px"
  group-gap: "32px"
  panel-gap: "20px"
  panel-pad: "20px"
components:
  pushbutton:
    backgroundColor: "#4D606C"
    textColor: "#F6F9FA"
    typography: "{typography.label}"
    rounded: "{rounded.pushbutton}"
    padding: "12px 17px"
  key-tab:
    backgroundColor: "#33444F"
    textColor: "{colors.desk-ink-secondary}"
    rounded: "{rounded.control}"
    padding: "11px 14px"
  key-tab-selected:
    backgroundColor: "#1A252C"
    textColor: "#FFFFFF"
  well-input:
    backgroundColor: "{colors.instrument-well}"
    textColor: "#F6F9FA"
    rounded: "{rounded.control}"
    padding: "6px 32px 6px 11px"
  segmented-selector:
    backgroundColor: "{colors.instrument-well}"
    textColor: "{colors.desk-ink-secondary}"
    rounded: "5px"
    padding: "3px"
  segmented-selector-active:
    backgroundColor: "#425461"
    textColor: "#FFFFFF"
  wall-panel:
    backgroundColor: "{colors.wall-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.wall}"
    padding: "14px 20px 18px"
  readout:
    backgroundColor: "{colors.instrument-well}"
    textColor: "#F6F9FA"
    typography: "{typography.readout}"
    rounded: "{rounded.control}"
    padding: "7px 16px"
---

# Design System: Consumo eléctrico por distribuidora — Panamá

## Overview

**Creative North Star: "Sala de control del despacho"**

The dashboard is the operations wall of a grid dispatch center. A sticky control desk (pupitre de mando) runs full width across the top in a distinct raised material: brushed slate gradient, recessed instrument wells, breakers, knobs, a segmented selector and a pushbutton. Below it, the wall is flat dark slate: the answer in large condensed type, then a single-line (unifilar) mimic diagram where one busbar feeds three distributor feeders, then flat instrument panels with charts and tables. Everything is dense but read from the back of a classroom: secondary text never drops below 16px, chart labels never below 14px.

State is carried only by indicator lamps and the electrical symbols themselves. Green means normal or selected, amber means changed or imputed, red means a source fault kept and flagged. Nothing on the wall uses those colors for decoration. The desk is hardware: it keeps its dark material in both themes. The light theme is the printed operations log (logbook paper, same grammar), used for figure capture.

Dark is the default because the dashboard is projected. The build does not follow `prefers-color-scheme`; the light log is reached only with `?tema=claro` (and dark forced with `?tema=oscuro`). This diverges from PRODUCT.md, which lists system preference; it is a known, disclosed deviation, not a rule to copy.

**Key Characteristics:**
- A raised control desk that is never another card: gradient face, recessed wells, physical controls.
- A flat dark wall with hairline-ruled panels (3px corners, 1px rule, no shadow).
- The busbar and breaker symbol as the structural motif, repeated on the desk switches and the mimic.
- Lamps as the only state color: green normal, amber changed or imputed, red source fault.
- One condensed industrial face for every number and label; a humanist sans for reading text.

## Colors

A dark slate control-room palette where hue is reserved for meaning: three fixed distributor colors, two effect colors, and three lamp colors.

### Primary
- **EDEMET Blue** (edemet-blue), **ENSA Orange** (ensa-orange), **EDECHI Green** (edechi-green): fixed brand commitments shared with the report, slides and figures. They color the feeder names, feeder conductors in the mimic, breaker handles when closed, series lines, bars and end labels. Light log variants: #2a78d6, #eb6834, #1baf7a.

### Secondary
- **Clients-Effect Violet** (effect-clients-violet; log #6250d6): the LMDI clients effect, in bars, legend swatches and effect bars.
- **Consumption-Effect Magenta** (effect-consumption-magenta; log and exported figures #c2417f): the LMDI consumption-per-client effect. It was moved off amber so that amber has one meaning.

### Tertiary
- **Lamp Amber** (lamp-amber): changed or imputed only. The change flash, the imputed-month diamonds and axis ticks, the imputed lamp, the US$/kWh warning glyph, focus outlines and text selection. **Amber Ink** (amber-ink; log #7A5200) is its text-safe form for links in the annunciator.
- **Lamp Green** (lamp-green): normal, in service, selected.
- **Lamp Red** (lamp-red): a source fault conserved and flagged.
- **Lamp Off** (lamp-off): unlit lamps, open feeders, the empty rail of an open breaker.

### Neutral
- **Wall Ground** (wall-ground): page background. **Wall Panel** (wall-panel): instrument panels and the mimic. **Raised Panel** (wall-panel-raised): table row hover, effect-bar tracks, tooltips.
- **Panel Rule** (panel-rule): 1px panel borders and dividers. **Chart Grid** (chart-grid): gridlines and table row rules.
- **Ink / Secondary / Tertiary** (ink, ink-secondary, ink-tertiary): primary text, supporting text and axis labels, zero lines and disabled feeder names.
- **Busbar** (busbar; log #36424A): the bus bar and its junction dots.
- **Desk Face** (desk-face to desk-face-low gradient), **Instrument Well** (instrument-well), **Desk Ink** (desk-ink, desk-ink-secondary): the desk's hardware palette, identical in both themes.
- **Log Paper / Log Panel / Log Ink** (log-paper, log-panel, log-ink): the light log's ground, panel and ink. Rules there are #CBC4B4 and gridlines #E2DCCF.

### Named Rules
**The Lamp Rule.** Green, amber and red are lamp states, never decoration. Amber means changed or imputed and nothing else; any new series or category gets a different hue.

**The Fixed Feeders Rule.** EDEMET is blue, ENSA orange, EDECHI green, everywhere, in every theme and every exported figure.

## Typography

**Display Font:** Barlow Condensed (with Arial Narrow, sans-serif), embedded in the file.
**Body Font:** Barlow (with sans-serif), embedded in the file.

**Character:** Barlow Condensed reads like engraved panel labels and instrument numerals; Barlow keeps prose and notes readable. All numbers use tabular figures.

### Hierarchy
- **Display** (700, 50px, 1): feeder growth percentage, the largest number on the wall (40px on mobile).
- **Headline** (500, 31px, 1.22, max 60ch): the answer sentence, with bold distributor names and figures (22px on mobile).
- **Readout** (600, 27px): the desk readout of the current setting (19px on mobile, wrapping).
- **Title** (600, 26px, 1.15): panel headings (21px on mobile); feeder names at 700, 25px, 0.05em, in their distributor color; sub-panel titles 600, 20px.
- **Body** (400, 16px, 1.55): notes, subtitles, legends, table cells and feeder detail. The question line is 17px in ink-secondary.
- **Label** (600, 14px, 0.1em, uppercase): table headers, unit labels beside feeder figures, the AI mode plate, details summaries (15px).
- **Engraved** (600, 12px, 0.14em, uppercase, 1px dark text-shadow): desk group and control labels only.
- **Chart text**: Barlow Condensed 500 at 14px for ticks and axis titles, 15px bold for distributor end labels.

### Named Rules
**The Back-Row Rule.** Secondary text is 16px and chart text at least 14px; the wall is read on a projector.

**The Engraving Rule.** Uppercase tracking belongs to labels that name a control or a column, a few words long. Running text and headings stay in sentence case.

## Layout

The desk is `position: sticky` at the top, full width, with content capped at 1560px and 24px gutters. Row one holds the nameplate (max 300px), the readout well (flexes), and the tab keys. Row two holds the control groups (distributors, period, metric, reset pushed right), separated by a 32px gap and a hairline groove. On the Calidad tab, row two is hidden and the readout is hidden.

The wall uses the same 1560px measure: answer block, then the mimic (three equal feeder columns divided by 1px rules), the annunciator strip, then full-width panels stacked with 20px gaps. Paired panels use an auto-fit grid with a 560px minimum column.

Below 1280px the nameplate narrows and the reset pushbutton becomes icon-only. Below 760px the desk collapses: nameplate, readout and keys stack, and a "Mandos" key opens the controls; the mimic's busbar becomes a vertical rail on the left with a colored tap to each stacked feeder.

## Elevation & Depth

The wall is flat; depth belongs to the desk. Wall panels have no shadow and are separated by tone and a 1px rule. The desk is lit from above: gradient face, inset top highlight, and a 7px dark lip below it that casts a soft shadow onto the wall. Instrument wells (readout, selects, segmented selector, search) are recessed with a strong inset shadow. Keys and the pushbutton are raised and press in when active.

### Shadow Vocabulary
- **Desk lip** (`box-shadow: 0 8px 14px -2px rgba(0,0,0,.6)` on a 7px #141D23 to #0B1013 strip): the desk's edge over the wall.
- **Recessed well** (`box-shadow: inset 0 2px 5px rgba(0,0,0,.85), 0 1px 0 rgba(255,255,255,.08)`): any input or readout set into the desk.
- **Raised key** (`box-shadow: inset 0 1px 0 rgba(255,255,255,.1), 0 2px 3px rgba(0,0,0,.5)`): tab keys at rest.
- **Pushbutton** (`box-shadow: inset 0 1px 0 rgba(255,255,255,.22), inset 0 -2px 0 rgba(0,0,0,.25), 0 3px 5px rgba(0,0,0,.6)`): the reset and clear buttons.
- **Tooltip** (`box-shadow: 0 6px 12px -4px var(--sombra)`): the only floating element on the wall.

### Named Rules
**The Flat Wall Rule.** Wall panels never take a shadow; if it has relief, it belongs on the desk.

## Shapes

Small, machined corners: 3px on wall panels, 4px on desk controls and wells, 5px on the segmented selector, 6px on the pushbutton, 2px on swatches and the AI plate. Lamps are solid circles with no specular or glow. The mimic is drawn in strict single-line-diagram geometry: a 6px busbar, round junctions, 3px feeder conductors, and a 14px square breaker (filled = closed; hollow with an angled open blade = open). The desk's distributor switches use the same breaker symbol on a vertical rail. Imputed points are amber-stroked diamonds.

## Components

### Buttons
- **Pushbutton:** tactile and heavy. Slate gradient (#4D606C to #34444F), 6px corners, 14px condensed bold uppercase at 0.14em, 12px 17px padding. Hover lightens the gradient; active presses down 2px and flattens the shadow.
- **Key (tabs):** a smaller raised key, 15px condensed uppercase, with a lamp that lights green when selected. Selected keys appear pressed in (dark gradient, inset shadow).

### Inputs / Fields
- **Style:** recessed well (instrument-well, 1px black border, 4px corners), 20 to 24px condensed numerals in near-white, custom chevron for selects.
- **Focus:** 2px amber outline with offset, the global focus treatment. Hover brightens the border to #4A5C68.
- **Desk grammar everywhere:** the Calidad incident filters sit on a desk-face plate with the same wells and a pushbutton, never as plain form fields.

### Navigation
Two tab keys on the desk (Análisis, Calidad de datos). On mobile a third key, Mandos, toggles the control rows.

### Cards / Containers
- **Wall panel:** wall-panel ground, 1px panel-rule border, 3px corners, no shadow; header 14px 20px 12px with a bottom rule, body 14px 20px 18px.
- **Annunciator strip:** a single-row panel with a leading lamp, for notices (imputed counts, links to the quality tab).

### Distributor Breaker (signature)
Each distributor is a breaker switch on the desk: the mimic's breaker symbol on a vertical rail, the distributor name in 17px condensed bold, an "en servicio" state line, and a lamp. Closed paints the rail, the square and the lamp in the distributor color; open shows a hollow square with an open blade and an unlit lamp.

### Single-Line Mimic (signature)
A busbar across the mimic panel feeds three feeder columns. Each feeder carries its name, period, growth display, GWh change, the two LMDI effects with diverging bars about a center tick, and a ruled detail list. Deselected feeders dim their name and draw an open breaker.

### Annunciator Counters
On the Calidad tab, counts sit in a recessed strip of dark tiles, each with a 14px lamp, a 30px figure and an uppercase label; the strip keeps its hardware colors in both themes.

### Change Flash (signature interaction)
When a desk setting changes, the affected wall elements flash a 2px amber outline at a 5px offset that fades over 1.4s (cubic-bezier(.16,1,.3,1)); the answer gets an amber bar in its left margin instead. Text color is not repainted on the wall. The readout well's border flashes amber with it. Disabled under `prefers-reduced-motion`.

## Do's and Don'ts

### Do:
- **Do** keep the desk a distinct raised console (gradient #2D3D48 to #22303A, recessed wells, physical controls) and the wall flat.
- **Do** mark every imputed value with the amber diamond or amber axis tick, and keep its original value in the tooltip.
- **Do** keep secondary text at 16px and chart text at 14px or larger.
- **Do** draw any new on/off control for a distributor with the mimic's breaker symbol.
- **Do** keep EDEMET blue, ENSA orange and EDECHI green fixed across themes and figures.

### Don't:
- **Don't** use amber, green or red for anything but lamp state; the consumption effect uses magenta (#c2417f in figures) for that reason.
- **Don't** add small uppercase category labels above headings or numbers; uppercase tracking is for control and column labels only.
- **Don't** give lamps a specular highlight or glow; they are solid discs.
- **Don't** put shadows on wall panels or render filters as plain cards on the wall.
- **Don't** set long passages in uppercase. The 44-character nameplate title on the desk is the one exception, engraved on the nameplate, and should not be extended.
