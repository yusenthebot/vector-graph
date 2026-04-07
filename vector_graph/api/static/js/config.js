// ── config.js — Constants, shared geometries, node label factory ──

// ── Config ──────────────────────────────────────────────────
const COLORS = {
  File:'#585b70', Folder:'#585b70', Module:'#fab387',
  Function:'#89b4fa', Class:'#cba6f7', Method:'#94e2d5',
  Variable:'#a6adc8', Property:'#a6adc8', Decorator:'#f5c2e7',
  ROS2Node:'#f38ba8', Topic:'#f9e2af', Service:'#a6e3a1',
  Action:'#f5c2e7', Parameter:'#89dceb',
  Community:'#b4befe', Process:'#f2cdcd'
};
const SIZES = {
  File:2, Folder:2, Module:3, Function:4, Class:6, Method:3,
  Variable:2, Property:2, Decorator:2,
  ROS2Node:5, Topic:4, Service:4, Action:4, Parameter:3,
  Community:3, Process:3
};
const EDGE_COLORS = {
  CALLS:'#89b4fa', IMPORTS:'#fab387', HAS_METHOD:'#94e2d5',
  EXTENDS:'#cba6f7', IMPLEMENTS:'#cba6f7', CONTAINS:'#45475a',
  DEFINES:'#45475a', DECORATES:'#f5c2e7', HAS_PROPERTY:'#a6adc8',
  PUBLISHES_TO:'#a6e3a1', SUBSCRIBES_TO:'#f9e2af',
  PROVIDES_SERVICE:'#f38ba8', CALLS_SERVICE:'#f38ba8',
  PROVIDES_ACTION:'#f5c2e7', CALLS_ACTION:'#f5c2e7',
  USES_PARAMETER:'#89dceb', STEP_IN_PROCESS:'#b4befe', MEMBER_OF:'#b4befe'
};
const GROUPS = {
  Structure: ['File','Folder','Module'],
  Code: ['Function','Class','Method','Variable','Property','Decorator'],
  ROS2: ['ROS2Node','Topic','Service','Action','Parameter'],
};

// ── Shared geometries (one per node type, reused across all nodes) ──
const _GEO = {};
function _initGeo() {
  _GEO.File      = new THREE.CylinderGeometry(1, 1, 0.3, 6);     // flat hex disc
  _GEO.Class     = new THREE.BoxGeometry(1.4, 1.4, 1.4);          // cube
  _GEO.Function  = new THREE.SphereGeometry(1, 16, 12);            // sphere
  _GEO.Method    = new THREE.OctahedronGeometry(1);                 // diamond
  _GEO.Variable  = new THREE.TetrahedronGeometry(0.7);              // small pyramid
  _GEO.Property  = new THREE.BoxGeometry(0.7, 0.7, 0.7);           // small cube
  _GEO.Decorator = new THREE.TorusGeometry(0.7, 0.2, 8, 16);       // ring
  _GEO.Module    = new THREE.CylinderGeometry(1, 1, 0.4, 8);       // disc
  _GEO.ROS2Node  = new THREE.IcosahedronGeometry(1.2);              // icosahedron
  _GEO.Topic     = new THREE.ConeGeometry(0.8, 1.4, 6);            // cone
  _GEO.Service   = new THREE.CylinderGeometry(0.5, 0.5, 1.2, 8);   // cylinder
  _GEO.Action    = new THREE.DodecahedronGeometry(1);               // dodecahedron
  _GEO.Parameter = new THREE.SphereGeometry(0.6, 8, 6);             // small sphere
  _GEO._default  = new THREE.SphereGeometry(1, 12, 8);
}

// ── Node label sprite factory (one canvas per node, ~12KB each, ~7MB total) ──
function _makeNodeLabel(text, color) {
  var canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 48;
  var ctx = canvas.getContext('2d');
  ctx.font = '20px monospace';
  var label = text.length > 20 ? text.slice(0, 18) + '..' : text;
  var tw = ctx.measureText(label).width;
  // Background pill
  ctx.fillStyle = 'rgba(17, 17, 27, 0.7)';
  ctx.fillRect(128 - tw / 2 - 6, 8, tw + 12, 28);
  // Text
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, 128, 22);

  var texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  var spriteMat = new THREE.SpriteMaterial({map: texture, transparent: true, depthWrite: false});
  var sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(12, 2.25, 1);
  return sprite;
}
