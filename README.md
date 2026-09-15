# Geodetic Sketch Generator

<img width="1991" height="1276" alt="image" src="https://github.com/user-attachments/assets/7d00a376-ba34-4aa7-8144-39143c667dea" />

## Multileader

Use the **Multileader** toolbar tool, `M, L`, or `MLEADER` to place an annotation arrowhead first, then its optional landing point, text position, and text. The standard workflow creates a straight leader with a closed-filled arrowhead. `MLEADER SPLINE OPEN`, `MLEADER DOT NOLANDING`, and the `LEFT` or `RIGHT` options select the supported curved, arrowhead, landing, and text-attachment variants.

Multileaders are saved as a compatible DXF fallback: line or spline geometry, arrow geometry, and TEXT linked by the `GSG_MLEADER` application metadata. This displays in common CAD tools even when they do not support native `MLEADER`; Geodetic Sketch Generator uses the metadata to keep all parts selectable, transformable, deletable, and undoable as one annotation after DXF or project reopen.
