# Design

## System

Internal product UI with a restrained light theme. The physical scene is: a document operations desk under neutral office light, where users need calm scanning, not visual spectacle.

## Palette

Use OKLCH custom properties only.

```css
--bg: oklch(1.000 0.000 0);
--surface: oklch(0.972 0.004 110);
--surface-strong: oklch(0.938 0.008 110);
--ink: oklch(0.205 0.015 110);
--muted: oklch(0.455 0.018 110);
--primary: oklch(0.470 0.105 110);
--primary-hover: oklch(0.405 0.110 110);
--accent: oklch(0.565 0.135 35);
--success: oklch(0.520 0.115 145);
--warning: oklch(0.690 0.145 75);
--danger: oklch(0.560 0.160 25);
--border: oklch(0.890 0.010 110);
```

## Typography

Use `Inter`, `Segoe UI`, `Arial`, `sans-serif`. Product UI uses fixed rem sizing: compact labels, readable body, and moderate headings. No display fonts.

## Components

Buttons use consistent 8px radius, visible focus rings, and icon + label where the action benefits from recognition. Panels use subtle borders without large decorative shadows. Status chips include text labels and color. Citations are compact source rows with filename, page, and excerpt.

## Layout

Desktop uses a two-column workbench: document/sidebar area and chat/search workspace. Mobile collapses into a single-column stacked workflow. Keep controls dense but not cramped.

## Motion

Use 150-200ms state transitions for hover, focus, status updates, and panel reveals. Disable nonessential movement under `prefers-reduced-motion`.
