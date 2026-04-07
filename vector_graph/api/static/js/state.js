// ── state.js — All mutable application state ──

// ── State ───────────────────────────────────────────────────
let allNodes = [], allLinks = [];
let enabledLabels = new Set(Object.keys(COLORS));
// Hide structural edges by default — they clutter the graph without showing code flow
const _STRUCTURAL_EDGES = new Set(['CONTAINS','HAS_METHOD','DEFINES','HAS_PROPERTY']);
let enabledEdges = new Set(Object.keys(EDGE_COLORS).filter(e => !_STRUCTURAL_EDGES.has(e)));
let selectedId = null;
let hoveredId = null;
let sidebarCollapsed = localStorage.getItem('vg-sidebar-collapsed') === 'true';
let highlightNodes = new Set();
let highlightLinks = new Set();
let depthFilter = 0; // 0 = all
let graph3d = null;
let linkIndex = {from: {}, to: {}}; // pre-built for O(1) lookups
let GROUP_COLORS = {}; // populated in loadData after nodes arrive
let nebulaGroup = null;
let healthMode = false; // OFF by default — show per-type label colors
let hotspotMode = false; // OFF by default — git change frequency heatmap

let currentMode = localStorage.getItem('vg-mode') || 'logic';
let sessionChangeCount = {};  // symbol name -> change count this session
let cmdOpen = false;
let cmdIdx = 0;
let cmdItems = [];
let impactGraph2d = null; // ForceGraph 2D instance (canvas-based, vasturiano/force-graph)
let changeViewMode = 'summary'; // 'summary' or 'detail'
let modeCache = {}; // {architecture: {nodes, links}, logic: {nodes, links}, deep: {nodes, links}}

// ── Change tracking state (Live Radar) ──
let activeChangeIds = new Set();    // nodes directly changed (persistent until next change)
let activeImpactIds = new Set();    // impact chain nodes (depth 1-2 callers)
let cumulativeHeat = {};            // nodeId -> change count this session
let changeHighlightActive = false;  // true when showing change overlay
let _changeGlowGroup = null;        // THREE.Group of pulsing glow spheres for changed nodes
let _selectionGlowGroup = null;     // THREE.Group of pulsing glow spheres for selected node
let _constellationTimeout = null;   // handle for constellation force removal timer

// ── Change grouping state (5-second debounce window) ──
let changeGroupBuffer = [];       // buffered change events
let changeGroupTimer = null;      // debounce timer
const CHANGE_GROUP_WINDOW = 5000; // 5 seconds

let _expandedNode2d = null; // currently expanded node in 2D graph
let hovered2dId = null; // hover-to-show labels when >15 nodes
