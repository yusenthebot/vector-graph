# TODO: Visualization Improvements

## Goal: Make the graph intuitive at first glance

The current 3D graph is powerful but requires learning to read. A new user should understand what they're seeing within 5 seconds.

---

## P0 -- Must Do

### 1. Smarter 3D edge rendering

**Problem**: In Logic/Deep mode, edges create a web of lines that obscures the node structure.

**Fix**:
- Show edges ONLY on hover/selection (not all the time)
- When hovering a node, only its direct edges fade in (1s transition)
- When nothing is hovered, show ZERO edges -- the nebula clustering already communicates structure
- Keep edge particles only for selected node and change highlights

### 2. Node size = importance

**Problem**: All functions are roughly the same size, so the eye doesn't know where to look.

**Fix**:
- Size nodes by connectivity (fan-in + fan-out)
- High-connectivity nodes are visually larger -- the "important" functions stand out
- File nodes sized by number of symbols they contain
- In Architecture mode: file size proportional to LOC

### 3. 2D impact graph label collision avoidance

**Problem**: When many changed nodes are close together in the 2D graph, labels overlap.

**Fix**:
- Use force-graph's built-in collision radius to push labels apart
- Show label only on hover when nodes > 15 (revert to current behavior for large graphs)
- Keep labels always visible when nodes <= 15

---

## P1 -- Should Do

### 4. Containment visualization

**Problem**: Methods belong to classes, functions belong to files, but this isn't visible -- everything floats at the same level.

**Fix**:
- In Logic mode: draw a subtle boundary around class nodes and their methods (convex hull)
- Class nodes act as "parent" containers -- methods orbit around them
- Click a class to expand/collapse its methods (progressive disclosure)

### 5. Edge bundling for cross-group connections

**Problem**: 20 CALLS edges from module A to module B create 20 separate lines crossing the graph.

**Fix**:
- Bundle edges between the same two nebulae into one thick conduit
- Show count label on the bundled edge ("12 calls")
- Click to expand individual edges

### 6. Minimap

**Problem**: When zoomed in, the developer loses spatial context -- where am I in the codebase?

**Fix**:
- Small 2D overview in the bottom-right corner showing all nebulae as colored dots
- Current viewport shown as a rectangle
- Click a nebula in the minimap to fly there

---

## P2 -- Nice to Have

### 7. Animated change replay

- "Replay session" button that re-plays all changes in chronological order
- Each change triggers the normal camera fly-to + highlight + ripple
- Speed control: 1x / 2x / 5x
- Shows the narrative timeline alongside

### 8. Graph diff view

- Split-screen: graph structure BEFORE session vs NOW
- New nodes/edges highlighted in green, removed in red
- Useful for reviewing what an AI coding session actually changed

### 9. Sound design

- Subtle ambient sound when the graph is stable
- Soft "ping" on change arrival (pitch proportional to risk level)
- Can be muted (off by default)

### 10. Performance LOD

- Level of Detail: zoom out -> groups collapse to single mega-nodes
- Zoom in -> expand to show individual functions
- WebGL InstancedMesh for same-type nodes (10K nodes at 60fps)
- Lazy loading: browser requests group contents on demand
