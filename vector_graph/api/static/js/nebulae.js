// ── nebulae.js — Nebula cluster rendering, groups panel ──
function updateNebulae() {
  if (!graph3d || typeof THREE === 'undefined') return;
  const scene = graph3d.scene();
  if (!scene) return;

  // Remove old nebulae
  if (nebulaGroup) {
    nebulaGroup.traverse(function(obj) {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) { if (obj.material.map) obj.material.map.dispose(); obj.material.dispose(); }
    });
    scene.remove(nebulaGroup);
  }
  nebulaGroup = new THREE.Group();

  // Group real nodes by group field
  const groups = {};
  graph3d.graphData().nodes.forEach(n => {
    const g = n.group || 'other';
    if (!groups[g]) groups[g] = [];
    groups[g].push(n);
  });

  Object.entries(groups).forEach(([name, nodes]) => {
    if (nodes.length < 2) return;

    // Centroid
    let cx = 0, cy = 0, cz = 0;
    nodes.forEach(n => { cx += n.x||0; cy += n.y||0; cz += n.z||0; });
    cx /= nodes.length; cy /= nodes.length; cz /= nodes.length;

    // Radius
    let maxDist = 0;
    nodes.forEach(n => {
      const d = Math.sqrt(((n.x||0)-cx)**2 + ((n.y||0)-cy)**2 + ((n.z||0)-cz)**2);
      if (d > maxDist) maxDist = d;
    });
    const radius = Math.max(maxDist * 1.4, 20);

    const color = new THREE.Color(GROUP_COLORS[name] || '#888888');

    // ── 1. Transparent sphere shell ──
    const shellGeo = new THREE.SphereGeometry(radius, 32, 24);
    const shellMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.07,
      depthWrite: false,
      side: THREE.BackSide,
    });
    const shell = new THREE.Mesh(shellGeo, shellMat);
    shell.position.set(cx, cy, cz);
    shell.userData = { groupName: name, isNebula: true };
    nebulaGroup.add(shell);

    // ── 2. Inner glow sphere ──
    const glowGeo = new THREE.SphereGeometry(radius * 0.4, 16, 12);
    const glowMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.05,
      depthWrite: false,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.position.set(cx, cy, cz);
    nebulaGroup.add(glow);

    // ── 3. Stardust particles ──
    const dustCount = Math.min(Math.max(Math.floor(nodes.length * 0.5), 10), 80);
    const positions = new Float32Array(dustCount * 3);
    const colors = new Float32Array(dustCount * 3);

    for (let i = 0; i < dustCount; i++) {
      // Uniform distribution inside sphere
      let dx, dy, dz;
      do {
        dx = (Math.random() - 0.5) * 2;
        dy = (Math.random() - 0.5) * 2;
        dz = (Math.random() - 0.5) * 2;
      } while (dx*dx + dy*dy + dz*dz > 1);

      positions[i*3]     = cx + dx * radius * 0.85;
      positions[i*3 + 1] = cy + dy * radius * 0.85;
      positions[i*3 + 2] = cz + dz * radius * 0.85;

      // Slight color variation
      const brightness = 0.7 + Math.random() * 0.3;
      colors[i*3]     = color.r * brightness;
      colors[i*3 + 1] = color.g * brightness;
      colors[i*3 + 2] = color.b * brightness;
    }

    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    dustGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const dustMat = new THREE.PointsMaterial({
      size: 1.5,
      transparent: true,
      opacity: 0.5,
      vertexColors: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    nebulaGroup.add(new THREE.Points(dustGeo, dustMat));

    // ── 4. Orbital ring ──
    const ringGeo = new THREE.TorusGeometry(radius * 0.95, 0.4, 8, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.15,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(cx, cy, cz);
    ring.rotation.x = Math.random() * Math.PI;
    ring.rotation.z = Math.random() * Math.PI * 0.5;
    nebulaGroup.add(ring);

    // ── 5. Group name label (always visible sprite) ──
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 1024;
    canvas.height = 128;

    // Glow background
    ctx.shadowColor = GROUP_COLORS[name] || '#888';
    ctx.shadowBlur = 30;
    ctx.font = 'bold 60px monospace';
    ctx.fillStyle = GROUP_COLORS[name] || '#cdd6f4';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const shortName = name.split('/').pop() || name;
    // Dark background for readability
    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(17, 17, 27, 0.6)';
    const textWidth = ctx.measureText(shortName).width;
    ctx.fillRect(512 - textWidth/2 - 10, 20, textWidth + 20, 45);
    ctx.shadowBlur = 30;
    ctx.fillStyle = GROUP_COLORS[name] || '#cdd6f4';
    ctx.fillText(shortName, 512, 50);
    // Count subtitle
    ctx.shadowBlur = 0;
    ctx.font = '28px monospace';
    ctx.globalAlpha = 0.6;
    ctx.fillText(nodes.length + ' nodes', 512, 100);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const sprite = new THREE.Sprite(spriteMat);
    const scale = Math.max(radius * 1.2, 50);
    sprite.position.set(cx, cy + radius + 10, cz);
    sprite.scale.set(scale, scale * 0.125, 1);
    sprite.userData = { groupName: name, isLabel: true };
    nebulaGroup.add(sprite);
  });

  scene.add(nebulaGroup);
}

// ── Groups sidebar panel ─────────────────────────────────────
function buildGroupsPanel() {
  const el = document.getElementById('panel-groups');
  const groupCounts = {};
  allNodes.forEach(n => {
    const g = n.group || 'other';
    groupCounts[g] = (groupCounts[g] || 0) + 1;
  });

  const sorted = Object.entries(groupCounts).sort((a,b) => b[1] - a[1]);
  let html = '<div class="filter-group"><h3 title="Nebula clusters — each group is a directory in the project. Click to fly camera to that group.">Packages</h3>';
  sorted.forEach(([name, count]) => {
    const color = GROUP_COLORS[name] || '#888';
    const shortName = name.split('/').pop() || name;
    html += `<div class="ftoggle" onclick="focusGroup('${name.replace(/'/g, "\\'")}')\" title="Click to focus on ${name} (${count} nodes) — camera will fly to this nebula">
      <span class="fdot" style="background:${color}"></span>
      ${shortName}
      <span class="fcount">${count}</span>
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

function focusGroup(groupName) {
  const groupNodes = graph3d.graphData().nodes.filter(n => n.group === groupName);
  if (!groupNodes.length) return;

  let cx = 0, cy = 0, cz = 0;
  groupNodes.forEach(n => { cx += n.x||0; cy += n.y||0; cz += n.z||0; });
  cx /= groupNodes.length; cy /= groupNodes.length; cz /= groupNodes.length;

  let maxDist = 0;
  groupNodes.forEach(n => {
    const d = Math.sqrt(((n.x||0)-cx)**2 + ((n.y||0)-cy)**2 + ((n.z||0)-cz)**2);
    if (d > maxDist) maxDist = d;
  });
  const dist = Math.max(maxDist * 2, 50);

  graph3d.cameraPosition(
    {x: cx + dist * 0.7, y: cy + dist * 0.4, z: cz + dist * 0.7},
    {x: cx, y: cy, z: cz},
    1500
  );

  // Nebula highlight for focused group
  if (nebulaGroup) {
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      const match = child.userData.groupName === groupName;
      if (child.userData.isNebula) child.material.opacity = match ? 0.18 : 0.02;
      if (child.userData.isLabel) child.material.opacity = match ? 1.0 : 0.25;
    });
  }
}
