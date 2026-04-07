// ── search.js — Search bar, command palette ──
// ── Search ──────────────────────────────────────────────────
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
let searchTimeout = null;

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(async () => {
    const q = searchInput.value.trim();
    if (!q) { searchResults.style.display = 'none'; return; }
    const r = await fetch('/api/search?q=' + encodeURIComponent(q)).then(r=>r.json());
    if (!r.results || !r.results.length) { searchResults.style.display = 'none'; return; }
    searchResults.innerHTML = r.results.map(n =>
      `<div class="sr" onclick="selectNode('${n.id}');searchResults.style.display='none';searchInput.value='';">
        <span class="fdot" style="background:${COLORS[n.label]||'#cdd6f4'}"></span>
        <span>${escHtml(n.name)}</span>
        <span style="color:var(--overlay0);font-size:10px">${n.label} · ${n.file}</span>
      </div>`
    ).join('');
    searchResults.style.display = 'block';
  }, 200);
});

searchInput.addEventListener('blur', () => { setTimeout(() => searchResults.style.display = 'none', 200); });
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); if (cmdOpen) closeCmdPalette(); else openCmdPalette(); return; }
  // Mode keyboard shortcuts — only when not typing in an input
  if (!document.activeElement || document.activeElement.tagName !== 'INPUT') {
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') { e.preventDefault(); toggleSidebar(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === 'i') { e.preventDefault(); toggleInspector(); return; }
    if (e.key === '1') { switchMode('architecture'); return; }
    if (e.key === '2') { switchMode('logic'); return; }
    if (e.key === '3') { switchMode('deep'); return; }
    if (e.key === '/') { e.preventDefault(); openCmdPalette(); return; }
  }
  if (e.key === 'Escape') { if (cmdOpen) { closeCmdPalette(); return; } deselectNode(); clearChangeHighlight(); searchResults.style.display = 'none'; searchInput.blur(); }
});

// ── Command Palette ─────────────────────────────────────────
const CMD_COMMANDS = [
  {name:'Switch to Architecture mode', key:'1', fn:function(){switchMode('architecture');}},
  {name:'Switch to Logic mode', key:'2', fn:function(){switchMode('logic');}},
  {name:'Switch to Deep mode', key:'3', fn:function(){switchMode('deep');}},
  {name:'Toggle health colors', key:'h', fn:function(){toggleHealthMode();}},
  {name:'Toggle hotspot colors', key:'', fn:function(){toggleHotspotMode();}},
  {name:'Toggle sidebar', key:'Ctrl+B', fn:function(){toggleSidebar();}},
  {name:'Clear selection', key:'Esc', fn:function(){deselectNode();}},
  {name:'Clear change highlight', key:'Esc', fn:function(){clearChangeHighlight();}},
];

function openCmdPalette() {
  cmdOpen = true; cmdIdx = 0; cmdItems = [];
  var el = document.getElementById('cmd-palette');
  el.classList.add('open'); el.style.display = 'flex';
  var inp = document.getElementById('cmd-input');
  inp.value = ''; inp.focus();
  renderCmdResults('');
}

function closeCmdPalette() {
  cmdOpen = false;
  var el = document.getElementById('cmd-palette');
  el.classList.remove('open'); el.style.display = 'none';
}

var _cmdTimer = null;
document.addEventListener('DOMContentLoaded', function() {
  var cmdInput = document.getElementById('cmd-input');
  if (!cmdInput) return;
  cmdInput.addEventListener('input', function() {
    clearTimeout(_cmdTimer);
    var q = this.value.trim();
    _cmdTimer = setTimeout(function(){renderCmdResults(q);}, 150);
  });
  cmdInput.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); cmdIdx = Math.min(cmdIdx+1, cmdItems.length-1); updateCmdSel(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cmdIdx = Math.max(cmdIdx-1, 0); updateCmdSel(); }
    else if (e.key === 'Enter') { e.preventDefault(); execCmd(cmdIdx); }
    else if (e.key === 'Escape') { e.preventDefault(); closeCmdPalette(); }
  });
  document.getElementById('cmd-backdrop').addEventListener('click', closeCmdPalette);
});

function renderCmdResults(q) {
  var el = document.getElementById('cmd-results');
  cmdItems = []; var html = '';
  // Group commands that match query
  var groupCmds = CMD_COMMANDS.slice();
  // Add dynamic group-focus commands
  var groups = [...new Set(allNodes.map(function(n){return n.group;}))].filter(Boolean).sort();
  groups.forEach(function(g) {
    groupCmds.push({name:'Focus group: '+g.split('/').pop(), key:'', fn:function(){focusGroup(g);closeCmdPalette();}});
  });
  if (q) {
    // Fetch node search results
    fetch('/api/search?q='+encodeURIComponent(q)).then(function(r){return r.json();}).then(function(d) {
      var nodeHtml = '';
      if (d.results && d.results.length) {
        nodeHtml += '<div class="cmd-group">Nodes</div>';
        d.results.slice(0,10).forEach(function(n) {
          var icon = n.label==='Function'?'f':n.label==='Class'?'C':n.label==='Method'?'m':n.label==='File'?'#':'*';
          var idx = cmdItems.length;
          cmdItems.push({fn:function(){selectNode(n.id);closeCmdPalette();}});
          nodeHtml += '<div class="cmd-item'+(idx===cmdIdx?' selected':'')+'" data-idx="'+idx+'" onclick="execCmd('+idx+')" onmouseover="cmdIdx='+idx+';updateCmdSel()">';
          nodeHtml += '<span class="cmd-icon" style="color:'+(COLORS[n.label]||'#cdd6f4')+'">'+icon+'</span>';
          nodeHtml += '<span class="cmd-name">'+n.name+'</span>';
          nodeHtml += '<span class="cmd-hint">'+n.label+(n.file?' \u00b7 '+n.file.split('/').pop():'')+'</span>';
          nodeHtml += '</div>';
        });
      }
      // Filter commands
      var filtered = groupCmds.filter(function(c){return c.name.toLowerCase().indexOf(q.toLowerCase())>=0;});
      var cmdHtml = '';
      if (filtered.length) {
        cmdHtml += '<div class="cmd-group">Commands</div>';
        filtered.slice(0,8).forEach(function(c) {
          var idx = cmdItems.length;
          cmdItems.push({fn:function(){c.fn();closeCmdPalette();}});
          cmdHtml += '<div class="cmd-item'+(idx===cmdIdx?' selected':'')+'" data-idx="'+idx+'" onclick="execCmd('+idx+')" onmouseover="cmdIdx='+idx+';updateCmdSel()">';
          cmdHtml += '<span class="cmd-icon" style="color:var(--mauve)">></span>';
          cmdHtml += '<span class="cmd-name">'+c.name+'</span>';
          if (c.key) cmdHtml += '<span class="cmd-key">'+c.key+'</span>';
          cmdHtml += '</div>';
        });
      }
      el.innerHTML = nodeHtml + cmdHtml || '<div style="padding:14px;color:var(--overlay0);text-align:center;font-size:11px">No results</div>';
      cmdIdx = 0; updateCmdSel();
    }).catch(function(){});
  } else {
    // Show commands by default
    html += '<div class="cmd-group">Commands</div>';
    groupCmds.slice(0,12).forEach(function(c) {
      var idx = cmdItems.length;
      cmdItems.push({fn:function(){c.fn();closeCmdPalette();}});
      html += '<div class="cmd-item'+(idx===cmdIdx?' selected':'')+'" data-idx="'+idx+'" onclick="execCmd('+idx+')" onmouseover="cmdIdx='+idx+';updateCmdSel()">';
      html += '<span class="cmd-icon" style="color:var(--mauve)">></span>';
      html += '<span class="cmd-name">'+c.name+'</span>';
      if (c.key) html += '<span class="cmd-key">'+c.key+'</span>';
      html += '</div>';
    });
    el.innerHTML = html;
    cmdIdx = 0; updateCmdSel();
  }
}

function updateCmdSel() {
  document.querySelectorAll('.cmd-item').forEach(function(el,i) {
    el.classList.toggle('selected', i===cmdIdx);
  });
  var sel = document.querySelector('.cmd-item.selected');
  if (sel) sel.scrollIntoView({block:'nearest'});
}

function execCmd(idx) {
  if (idx>=0 && idx<cmdItems.length) cmdItems[idx].fn();
}

document.getElementById('insp-close').addEventListener('click', deselectNode);
