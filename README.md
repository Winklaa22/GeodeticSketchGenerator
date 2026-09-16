# Geodetic Sketch Generator

<img width="1991" height="1276" alt="image" src="https://github.com/user-attachments/assets/7d00a376-ba34-4aa7-8144-39143c667dea" />

## Multileader

Use the **Multileader** toolbar tool, `M, L`, or `MLEADER` to place an annotation arrowhead first, then its optional landing point, text position, and text. The standard workflow creates a straight leader with a closed-filled arrowhead. `MLEADER SPLINE OPEN`, `MLEADER DOT NOLANDING`, and the `LEFT` or `RIGHT` options select the supported curved, arrowhead, landing, and text-attachment variants.

Multileaders are saved as a compatible DXF fallback: line or spline geometry, arrow geometry, and TEXT linked by the `GSG_MLEADER` application metadata. This displays in common CAD tools even when they do not support native `MLEADER`; Geodetic Sketch Generator uses the metadata to keep all parts selectable, transformable, deletable, and undoable as one annotation after DXF or project reopen.

## Detail view

Use the **Detail view** toolbar tool, `D, V`, or `DETAIL`. It takes two dragged rectangles: first drag out the area of the drawing you want magnified, then drag the frame that will display it. The magnification follows from the two sizes - the same area shown in a bigger frame simply reads bigger - and the scale fits whichever side is tighter, so everything you marked always ends up inside the frame. Only the rectangle you are currently dragging is drawn, so neither gets in the way of the other.

While the frame stays selected it behaves like a PDF viewer: the mouse wheel inside it zooms around the cursor and dragging pans the view inside it, each gesture landing as a single undo step. Click away to deselect and the wheel goes back to its normal meaning. Move or resize the frame itself with the `MOVE` and `SCALE` tools.

The magnified content is a view only - it cannot be selected, deleted, edited or snapped to, and clicking anywhere inside the frame selects the frame. It is drawn with the paper palette on a paper ground, so a detail view looks the same in the DXF editor as it does in the PDF preview and the exported PDF.

A detail view is stored as a closed LWPOLYLINE frame carrying `GSG_DETAIL` metadata, and its content is a live view of the drawing - edit the drawing and every detail view showing that area follows.
