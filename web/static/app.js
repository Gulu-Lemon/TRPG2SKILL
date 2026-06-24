// TRPG-to-SKILL — Web GUI
var S = {
    currentTab: 'compile',
    compiledDir: '',
    gameLoaded: false,
};

// ═══════════════════ Tab Switching ═══════════════════

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        var tabId = this.dataset.tab;
        S.currentTab = tabId;
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.getElementById(tabId + '-tab').classList.add('active');
        if (tabId === 'settings') loadSettings();
        if (tabId === 'play') loadGameList();
    });
});

// ═══════════════════ Compile ═══════════════════

function loadFile() {
    var f = document.getElementById('compile-file-input').files[0];
    if (!f) return;
    document.getElementById('compile-name').value = f.name.replace(/\.[^.]+$/, '');
    var reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('compile-input').value = e.target.result;
    };
    reader.readAsText(f);
}

function initDragDrop() {
    var area = document.getElementById('compile-input');
    if (!area) return;
    area.addEventListener('dragover', function(e) {
        e.preventDefault();
        area.style.borderColor = 'var(--accent)';
    });
    area.addEventListener('dragleave', function() {
        area.style.borderColor = '';
    });
    area.addEventListener('drop', function(e) {
        e.preventDefault();
        area.style.borderColor = '';
        var f = e.dataTransfer.files[0];
        if (!f) return;
        document.getElementById('compile-name').value = f.name.replace(/\.[^.]+$/, '');
        var reader = new FileReader();
        reader.onload = function(ev) { area.value = ev.target.result; };
        reader.readAsText(f);
    });
}

function startCompile() {
    var text = document.getElementById('compile-input').value.trim();
    if (!text) { alert('请粘贴世界书内容或上传文件'); return; }
    var name = document.getElementById('compile-name').value.trim() || 'my_game';
    startCompileInternal(text, name, '');
}

function startCompileInternal(text, name, feedback) {
    document.getElementById('compile-submit').disabled = true;
    document.getElementById('progress-bar-wrap').style.display = 'block';
    document.getElementById('compile-result').style.display = 'none';
    document.getElementById('compile-result').classList.remove('show');
    document.getElementById('compile-review').style.display = 'none';

    setProgress(0, '准备...');

    fetch('/api/compile/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ world_book_text: text, output_name: name, feedback: feedback })
    }).then(function(resp) {
        if (!resp.ok) throw new Error('编译启动失败');
        return readSSE(resp);
    }).catch(function(err) {
        setProgress(0, '错误: ' + err.message);
        document.getElementById('compile-submit').disabled = false;
    });
}

function readSSE(resp) {
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    function pump() {
        reader.read().then(function(result) {
            if (result.done) return;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';

            var eventType = '';
            var eventData = '';
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    eventData = line.slice(6).trim();
                    handleCompileEvent(eventType, eventData);
                }
            }
            pump();
        });
    }
    pump();
}

function handleCompileEvent(type, dataStr) {
    var data = {};
    try { data = JSON.parse(dataStr); } catch(e) {}

    if (type === 'error') {
        setProgress(0, '错误: ' + (data.message || dataStr));
        document.getElementById('compile-submit').disabled = false;
        return;
    }
    if (type === 'ok') {
        setProgress(100, '完成!');
        S.compiledDir = data.output_dir;
        document.getElementById('compile-submit').disabled = false;
        var resultDiv = document.getElementById('compile-result');
        resultDiv.style.display = 'block';
        resultDiv.classList.add('show');
        var score = (data.review && data.review.score) || '?';
        var passText = (score >= 60 || score === '?') ? '编译通过!' : '编译未通过';
        var cls = (score >= 60 || score === '?') ? 'success' : 'fail';
        resultDiv.querySelector('.result-text').innerHTML =
            '<span class="' + cls + '">' + passText + '</span> 评分: ' + score + '%' +
            ' — ' + (data.output_dir || '');
        document.getElementById('btn-play-compiled').style.display = 'inline-block';
        if (data.review) {
            S._analysis = data.review;
            showCompileResult(data.review);
        }
        return;
    }

    // 通用进度事件: {phase}_progress → {progress}% {detail}
    var pct = data.progress || 0;
    var detail = data.detail || '';
    if (data.phase) {
        var labels = {
            'parse': '解析', 'entity': '实体', 'rules': '规则',
            'structure': '结构', 'tools': '工具', 'validate': '校验',
            'correct': '修正', 'map': '映射', 'generate': '生成',
            'done': '完成'
        };
        detail = (labels[data.phase] || data.phase) + ': ' + detail;
    }
    setProgress(pct, detail);

    // 保存实体数据供审核面板使用
    if ((type === 'entity_progress' || type === 'entity_done') && data.entities) {
        S._analysis = data.entities;
    }
}

function setProgress(pct, text) {
    document.getElementById('progress-bar').style.width = pct + '%';
    document.getElementById('progress-text').textContent = pct + '% ' + text;
}

function showCompileResult(data) {
    var cls = data.score >= 60 ? 'success' : 'fail';
    var text = data.score >= 60 ? '编译通过!' : '编译未通过';
    document.getElementById('compile-submit').disabled = false;

    var review = document.getElementById('compile-review');
    var detail = document.getElementById('review-detail');
    var a = data;
    var lines = [];

    lines.push('<div style="font-size:15px;font-weight:bold;margin-bottom:6px">' +
               escapeHtml(a.game_name || '?') + '</div>');
    if (a.genre || a.tone) {
        lines.push('<span style="color:var(--text2)">' +
                   escapeHtml(a.genre || '?') + ' · ' + escapeHtml(a.tone || '?') +
                   '</span>');
    }

    lines.push('<div style="margin-top:8px;display:grid;grid-template-columns:auto 1fr;gap:3px 12px">');
    if (a.npcs && a.npcs.length) {
        var npcNames = a.npcs.map(function(n){return escapeHtml(n.name||'?');}).join(', ');
        lines.push('<b>NPC</b><span>' + npcNames + ' (' + a.npcs.length + ')</span>');
    }
    if (a.locations && a.locations.length) {
        var locNames = a.locations.map(function(l){return escapeHtml(l.name||'?');}).join(', ');
        lines.push('<b>地点</b><span>' + locNames + ' (' + a.locations.length + ')</span>');
    }
    if (a.items && a.items.length) {
        var itemNames = a.items.map(function(it){return escapeHtml(it.name||'?');}).join(', ');
        lines.push('<b>物品</b><span>' + itemNames + ' (' + a.items.length + ')</span>');
    }
    if (a.bans && a.bans.length) {
        lines.push('<b>禁令</b><span>' + a.bans.length + ' 条</span>');
    }
    if (a.phases && a.phases.length) {
        var phaseFlow = a.phases.map(function(p){
            return escapeHtml(p.name) + (p.next ? ' → ' + escapeHtml(p.next) : '');
        }).join(', ');
        lines.push('<b>阶段</b><span>' + phaseFlow + '</span>');
    }
    if (a.lorebook_count !== undefined) {
        lines.push('<b>Lorebook</b><span>' + a.lorebook_count + ' 条目</span>');
    }
    lines.push('<b>评分</b><span style="color:' + (a.score >= 60 ? 'var(--green)' : 'var(--red)') + '">' +
               (a.score || '?') + '%</span>');
    lines.push('</div>');

    detail.innerHTML = lines.join('');
    review.style.display = 'block';
}

function loadCompiledGame() {
    if (!S.compiledDir) return;
    switchTab('play');
    loadGameByPath(S.compiledDir);
}

function recompileWithFeedback() {
    var feedback = document.getElementById('review-feedback').value.trim();
    var text = document.getElementById('compile-input').value.trim();
    var name = document.getElementById('compile-name').value.trim() || 'my_game';
    if (!text) { alert('请先粘贴世界书内容'); return; }
    document.getElementById('compile-review').style.display = 'none';
    startCompileInternal(text, name, feedback);
}

// ═══════════════════ Drawer + Edit Panel ═══════════════════

function toggleLeftDrawer() {
    document.getElementById('left-drawer').classList.toggle('collapsed');
}

function toggleRightDrawer() {
    document.getElementById('right-drawer').classList.toggle('collapsed');
    if (!document.getElementById('right-drawer').classList.contains('collapsed') && S.compiledDir) {
        switchEditTab(S._editTab || 'bans');
    }
}

function openEditPanel(tab) {
    document.getElementById('right-drawer').classList.remove('collapsed');
    switchEditTab(tab);
}

function switchEditTab(tab) {
    S._editTab = tab;
    document.querySelectorAll('.edit-tab').forEach(function(t) { t.classList.toggle('active', t.dataset.editTab === tab); });
    var editContent = document.getElementById('edit-content');
    var statusPanel = document.getElementById('status-panel');
    if (tab === 'status') {
        editContent.style.display = 'none';
        statusPanel.style.display = 'block';
        loadStatusToPanel();
    } else {
        editContent.style.display = 'block';
        statusPanel.style.display = 'none';
        if (tab === 'bans') loadBansToPanel();
        else if (tab === 'lorebook') loadLorebookToPanel();
        else if (tab === 'toolpool') loadToolPoolToPanel();
        else if (tab === 'agents') loadAgentsToPanel();
    }
}

// ── Bans ──

function loadBansToPanel() {
    if (!S.compiledDir) return renderEditMsg('请先编译一个游戏');
    fetch('/api/edit/bans?dir=' + encodeURIComponent(S.compiledDir))
    .then(r => r.json()).then(function(data) {
        var bans = data.bans || [];
        var html = '';
        bans.forEach(function(b, i) {
            html += '<div class="edit-item">' +
                '<div class="ei-title">' + (i+1) + '. ' + escapeHtml(b.title) + '</div>' +
                '<div class="ei-text">' + escapeHtml(b.text) + '</div>' +
                '<div class="ei-actions">' +
                '<button onclick="editBanItem(' + i + ')">编辑</button>' +
                '<button class="btn-danger" onclick="deleteBanItem(' + i + ')">×</button>' +
                '</div></div>';
        });
        html += '<div style="display:flex;gap:6px;margin-top:8px">' +
            '<button onclick="newBanItem()">+ 新建</button>' +
            '<button onclick="smartDedupBans()">智能去重</button>' +
            '<button onclick="saveBansPanel()">保存全部</button></div>';
        document.getElementById('edit-content').innerHTML = html;
        S._editCache = {bans: bans};
    });
}

function editBanItem(idx) {
    var b = S._editCache.bans[idx];
    var title = prompt('禁令标题:', b ? b.title : '');
    if (title === null) return;
    var text = prompt('禁令内容:', b ? b.text : '');
    if (text === null) return;
    if (b) { b.title = title; b.text = text; }
    else { S._editCache.bans.push({title: title, text: text}); }
    loadBansToPanel();
}

function deleteBanItem(idx) {
    S._editCache.bans.splice(idx, 1);
    loadBansToPanel();
}

function newBanItem() { editBanItem(-1); }

function saveBansPanel() {
    showLoading(true, '保存中...');
    fetch('/api/edit/bans', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({dir: S.compiledDir, bans: S._editCache.bans})
    }).then(r => r.json()).then(function(d) {
        showLoading(false);
        if (d.ok) renderEditMsg('禁令已保存 ✓');
    });
}

function smartDedupBans() {
    if (!S.compiledDir) return;
    showLoading(true, '智能去重中...');
    fetch('/api/edit/bans/smart-dedup', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({dir: S.compiledDir})
    }).then(r => r.json()).then(function(data) {
        showLoading(false);
        if (data.error) { renderEditMsg('去重失败: ' + data.error); return; }
        S._editCache.bans = data.bans || [];
        loadBansToPanel();
        renderEditMsg('去重完成，可继续编辑后保存');
    });
}

// ── Lorebook ──

function loadLorebookToPanel() {
    if (!S.compiledDir) return renderEditMsg('请先编译');
    fetch('/api/edit/lorebook?dir=' + encodeURIComponent(S.compiledDir))
    .then(r => r.json()).then(function(data) {
        var entries = data.entries || [];
        S._editCache = {entries: entries};
        var opts = entries.map(function(e, i) {
            return '<option value="' + i + '">' + e.type + '/' + e.title + '</option>';
        }).join('');
        var html = '<select id="lorebook-select" class="edit-input" onchange="selectLorebookEntry()">' +
            '<option value="">-- 选择条目 --</option>' + opts + '</select>' +
            '<input id="lorebook-title" class="edit-input" placeholder="标题">' +
            '<textarea id="lorebook-content" class="edit-area" placeholder="内容"></textarea>' +
            '<div style="display:flex;gap:6px">' +
            '<button onclick="saveLorebookEdit()">保存</button>' +
            '<button onclick="newLorebookEntry()">+ 新建</button>' +
            '<button class="btn-danger" onclick="deleteLorebookEntry()">删除</button></div>';
        document.getElementById('edit-content').innerHTML = html;
    });
}

function selectLorebookEntry() {
    var idx = parseInt(document.getElementById('lorebook-select').value);
    if (isNaN(idx)) return;
    var e = S._editCache.entries[idx];
    document.getElementById('lorebook-title').value = e.title;
    document.getElementById('lorebook-content').value = e.content;
}

function saveLorebookEdit() {
    var idx = parseInt(document.getElementById('lorebook-select').value);
    var title = document.getElementById('lorebook-title').value;
    var content = document.getElementById('lorebook-content').value;
    if (!title) return;
    if (!isNaN(idx)) {
        S._editCache.entries[idx].title = title;
        S._editCache.entries[idx].content = content;
    } else {
        S._editCache.entries.push({id: 'custom_' + Date.now(), title: title, content: content, type: 'custom',
            keys: [], strategy: 'normal', position: 'after_instr', scan_depth: 5, priority: 10, recursive: false, is_dynamic: false});
    }
    showLoading(true, '保存...');
    fetch('/api/edit/lorebook', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({dir: S.compiledDir, entries: S._editCache.entries})
    }).then(r => r.json()).then(function(d) {
        showLoading(false);
        if (d.ok) loadLorebookToPanel();
    });
}

function newLorebookEntry() {
    document.getElementById('lorebook-select').value = '';
    document.getElementById('lorebook-title').value = '';
    document.getElementById('lorebook-content').value = '';
}

function deleteLorebookEntry() {
    var idx = parseInt(document.getElementById('lorebook-select').value);
    if (isNaN(idx)) return;
    S._editCache.entries.splice(idx, 1);
    saveLorebookEdit();
}

// ── Tool Pool ──

function loadToolPoolToPanel() {
    if (!S.compiledDir) return renderEditMsg('请先编译');
    document.getElementById('edit-content').innerHTML =
        '<input id="toolpool-name" class="edit-input" placeholder="工具文件名 (如 encounter_roller.py)">' +
        '<textarea id="toolpool-json" class="edit-area" style="min-height:200px" placeholder="JSON数据池"></textarea>' +
        '<div style="display:flex;gap:6px"><button onclick="fetchToolPool()">加载</button><button onclick="saveToolPool()">保存</button></div>';
}

function fetchToolPool() {
    var name = document.getElementById('toolpool-name').value.trim();
    if (!name) return;
    showLoading(true, '加载...');
    fetch('/api/edit/tool-pool?dir=' + encodeURIComponent(S.compiledDir) + '&tool=' + name)
    .then(r => r.json()).then(function(data) {
        showLoading(false);
        document.getElementById('toolpool-json').value = JSON.stringify(data.pool || [], null, 2);
    });
}

function saveToolPool() {
    var name = document.getElementById('toolpool-name').value.trim();
    if (!name) return;
    try {
        var pool = JSON.parse(document.getElementById('toolpool-json').value);
        showLoading(true, '保存...');
        fetch('/api/edit/tool-pool', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({dir: S.compiledDir, tool: name, pool: pool})
        }).then(r => r.json()).then(function(d) {
            showLoading(false);
            if (d.ok) renderEditMsg('数据池已保存 ✓');
        });
    } catch(e) { renderEditMsg('JSON错误: ' + e.message); }
}

// ── AGENTS.md ──

function loadAgentsToPanel() {
    if (!S.compiledDir) return renderEditMsg('请先加载游戏');
    fetch('/api/edit/agents?dir=' + encodeURIComponent(S.compiledDir))
    .then(r => r.json()).then(function(data) {
        document.getElementById('edit-content').innerHTML =
            '<textarea id="agents-edit" class="edit-area" style="min-height:300px">' + escapeHtml(data.text || '') + '</textarea>' +
            '<button onclick="saveAgentsEdit()" style="margin-top:6px">保存 AGENTS.md</button>' +
            '<span style="font-size:11px;color:var(--text2);margin-left:8px">保存后继续游戏自动生效</span>';
    });
}

function loadStatusToPanel() {
    var panel = document.getElementById('status-panel');
    if (!S.gameLoaded) {
        panel.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">未加载游戏</div>';
        return;
    }
    fetch('/api/play/state').then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) { panel.innerHTML = '<div style="color:var(--red)">' + escapeHtml(data.error) + '</div>'; return; }
        var lines = [];
        lines.push('<table style="width:100%;border-collapse:collapse">');
        var stdFields = [
            ['轮次', data.turn], ['天数', data.day], ['阶段', data.phase], ['位置', data.location]
        ];
        stdFields.forEach(function(f) {
            lines.push('<tr><td style="color:var(--text2);width:50px;padding:3px 6px">' + f[0] + '</td><td style="padding:3px 6px">' + escapeHtml(String(f[1] || '')) + '</td></tr>');
        });
        if (data.inventory && data.inventory.length) {
            lines.push('<tr><td style="color:var(--text2);padding:3px 6px">持有</td><td style="padding:3px 6px">' + escapeHtml(data.inventory.join(', ')) + '</td></tr>');
        }
        lines.push('</table>');

        // 自定义字段（优先按 state_fields 顺序，再补 custom 中的额外字段）
        var customKeys = [];
        var sf = data.state_fields || [];
        var seen = {};
        sf.forEach(function(f) {
            customKeys.push(f.name);
            seen[f.name] = true;
        });
        var custom = data.custom || {};
        Object.keys(custom).forEach(function(k) {
            if (!seen[k]) { customKeys.push(k); seen[k] = true; }
        });
        if (customKeys.length) {
            lines.push('<div style="border-top:1px solid var(--border);margin:6px 0 4px;font-size:11px;color:var(--text2)">游戏数据</div>');
            lines.push('<table style="width:100%;border-collapse:collapse">');
            customKeys.forEach(function(k) {
                var v = custom[k] !== undefined ? custom[k] : '';
                var sfDef = null;
                sf.forEach(function(f) { if (f.name === k) sfDef = f; });
                lines.push('<tr><td style="color:var(--text2);width:50px;padding:3px 6px">' + escapeHtml(k) + '</td><td style="padding:3px 6px">' + escapeHtml(String(v)) + '</td></tr>');
            });
            lines.push('</table>');
        }

        if (data.flags && data.flags.length) {
            lines.push('<div style="border-top:1px solid var(--border);margin:6px 0 4px;font-size:11px;color:var(--text2)">标记</div>');
            lines.push('<div style="display:flex;flex-wrap:wrap;gap:4px">');
            data.flags.forEach(function(f) {
                lines.push('<span style="background:var(--border);padding:2px 6px;border-radius:3px;font-size:11px">' + escapeHtml(f) + '</span>');
            });
            lines.push('</div>');
        }
        panel.innerHTML = lines.join('');
    }).catch(function(err) {
        panel.innerHTML = '<div style="color:var(--red)">加载失败: ' + escapeHtml(err.message) + '</div>';
    });
}

function saveAgentsEdit() {
    var text = document.getElementById('agents-edit').value;
    showLoading(true, '保存...');
    fetch('/api/edit/agents', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({dir: S.compiledDir, text: text})
    }).then(r => r.json()).then(function(d) {
        showLoading(false);
        if (d.ok) renderEditMsg('AGENTS.md 已保存 ✓ 继续游戏自动生效');
    });
}

function renderEditMsg(msg) {
    document.getElementById('edit-content').innerHTML = '<p style="color:var(--text2);padding:12px">' + msg + '</p>';
}

// ═══════════════════ Review Panel (compile tab) ═══════════════════

function recompileSinglePhase(phaseId) {
    var text = document.getElementById('compile-input').value.trim();
    var name = document.getElementById('compile-name').value.trim() || 'my_game';
    if (!text) { alert('请先粘贴世界书内容'); return; }
    showLoading(true, '重编译 Phase ' + phaseId + '...');
    fetch('/api/compile/phase', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({world_book_text: text, output_name: name, phase_id: phaseId})
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(data) {
        showLoading(false);
        if (data.error) { alert(data.error); return; }
        S.compiledDir = data.output_dir;
        alert('Phase ' + phaseId + ' 重编译完成。');
    }).catch(function(e) {
        showLoading(false);
        alert('错误: ' + (e.message || e));
    });
}

// ═══════════════════ Play ═══════════════════

function loadGameList() {
    var builtIn = fetch('/api/play/list').then(r => r.json()).then(function(d) { return d.skills || []; }).catch(function() { return []; });
    // 扫描已存储的自定义路径
    var customPaths = getCustomPaths();
    var customPromises = customPaths.map(function(p) {
        return fetch('/api/play/scan', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dir: p })
        }).then(r => r.json()).then(function(d) {
            return (d.skills || []).map(function(s) {
                s._customPath = p;
                return s;
            });
        }).catch(function() { return []; });
    });

    Promise.all([builtIn].concat(customPromises)).then(function(results) {
        var allSkills = [];
        var seen = {};
        results.forEach(function(arr) {
            arr.forEach(function(s) {
                if (!seen[s.path]) { seen[s.path] = true; allSkills.push(s); }
            });
        });

        var hidden = getHiddenSkills();
        var showHidden = localStorage.getItem('trpg-show-hidden') === '1';
        document.getElementById('toggle-hidden-btn').style.display = 'inline-block';
        document.getElementById('toggle-hidden-btn').textContent = showHidden ? '隐藏已屏蔽' : '显示已隐藏';

        var groups = {};
        allSkills.forEach(function(s) {
            var key = s._customPath || s.path.replace(/[/\\][^/\\]*$/, '');
            if (!groups[key]) groups[key] = [];
            groups[key].push(s);
        });

        var html = '';

        Object.keys(groups).forEach(function(pathKey) {
            var isHidden = hidden._paths && hidden._paths[pathKey];
            var isPermanent = pathKey.endsWith('generated') || pathKey.replace(/\\/g,'/').endsWith('generated');
            var isCustom = !isPermanent && customPaths.indexOf(pathKey) >= 0;
            var skills = groups[pathKey];
            var visSkills = skills.filter(function(s) { return !hidden[s.path]; });

            if (isHidden && isPermanent) {
                isHidden = false;
                delete (hidden._paths || {})[pathKey];
                setHiddenSkills(hidden);
            }
            if (isHidden && !isPermanent && !isCustom) return;

            html += '<div class="path-group-header">' + escapeHtml(pathKey) +
                (isPermanent ? '' : 
                 (isCustom ?
                  '<button class="btn-icon" style="margin-left:8px;font-size:11px;padding:2px 8px" ' +
                  'onclick="removeCustomPath(\'' + escapeHtmlAttr(pathKey) + '\')">移除路径</button>' :
                  '<button class="btn-icon path-hide-btn" style="margin-left:8px;font-size:11px;padding:2px 8px"' +
                  ' data-path="' + escapeHtml(pathKey) + '">停止扫描</button>')) +
                '</div>';

            var cards = (showHidden ? skills : visSkills);
            cards.forEach(function(s) {
                var hiddenBySelf = !!hidden[s.path];
                if (hiddenBySelf && !showHidden) return;
                var info = s.turn ? ' 轮:' + s.turn + ' ' + (s.phase || '') : '新游戏';
                if (s.saved) info += ' ' + s.saved.slice(0, 10);
                html += '<div class="game-card' + (hiddenBySelf ? ' hidden-skill' : '') + '">' +
                    '<div style="display:flex;justify-content:space-between;align-items:center">' +
                    '<span style="font-weight:600;font-size:14px">' + escapeHtml(s.name) + '</span>' +
                    '<span style="font-size:12px;color:var(--text2)">' + info +
                    (s.loadable === false ? ' [旧格式]' : '') + '</span>' +
                    '</div>' +
                    '<div style="font-size:11px;color:var(--text2);margin:4px 0 8px">' + escapeHtml(s.dir) + '</div>' +
                    '<div style="display:flex;gap:6px">' +
                    (s.loadable === false ?
                        '<button class="btn-icon" style="padding:5px 14px;font-size:12px;opacity:0.5" disabled>需重新编译</button>' +
                        '<button class="btn-icon save-view-btn" style="padding:5px 14px;font-size:12px"' +
                        ' data-path="' + escapeHtml(s.path) + '">查看存档</button>'
                        :
                        '<button class="btn-icon new-game-btn" style="padding:5px 14px;font-size:12px"' +
                        ' data-path="' + escapeHtml(s.path) + '">开始新游戏</button>' +
                        '<button class="btn-icon save-view-btn" style="padding:5px 14px;font-size:12px"' +
                        ' data-path="' + escapeHtml(s.path) + '">查看存档</button>'
                    ) +
                    '<button class="btn-icon btn-danger skill-toggle-btn" style="padding:5px 8px;font-size:11px;min-width:auto"' +
                    ' data-path="' + escapeHtml(s.path) + '"' +
                    ' data-hidden="' + (hiddenBySelf ? '1' : '0') + '">' +
                    (hiddenBySelf ? '恢复' : '×') + '</button>' +
                    '</div></div>';
            });
        });
        document.getElementById('game-list').innerHTML = html || '<p style="color:var(--text2)">暂无可用游戏。</p>';
        bindGameListEvents();
    }).catch(function(e) {
        document.getElementById('game-list').innerHTML = '<p style="color:var(--red)">加载失败: ' + (e.message || e) + '</p>';
    });
}

function getCustomPaths() {
    try { return JSON.parse(localStorage.getItem('trpg-custom-paths') || '[]'); }
    catch(e) { return []; }
}

function saveCustomPaths(paths) {
    localStorage.setItem('trpg-custom-paths', JSON.stringify(paths));
}

function removeCustomPath(path) {
    var paths = getCustomPaths().filter(function(p) { return p !== path; });
    saveCustomPaths(paths);
    loadGameList();
}

function bindGameListEvents() {
    document.querySelectorAll('.path-hide-btn').forEach(function(btn) {
        btn.addEventListener('click', function() { hidePath(this.dataset.path); });
    });
    document.querySelectorAll('.new-game-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); loadGameWithReset(this.dataset.path); });
    });
    document.querySelectorAll('.save-view-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); viewGameSaves(this.dataset.path); });
    });
    document.querySelectorAll('.skill-toggle-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (this.dataset.hidden === '1') { unhideSkill(this.dataset.path); }
            else { hideSkill(this.dataset.path); }
        });
    });
}

function getHiddenSkills() {
    try { return JSON.parse(localStorage.getItem('trpg-hidden-skills') || '{}'); }
    catch(e) { return {}; }
}

function setHiddenSkills(obj) {
    localStorage.setItem('trpg-hidden-skills', JSON.stringify(obj));
}

function hideSkill(path) {
    var h = getHiddenSkills();
    h[path] = true;
    setHiddenSkills(h);
    loadGameList();
}

function unhideSkill(path) {
    var h = getHiddenSkills();
    delete h[path];
    setHiddenSkills(h);
    loadGameList();
}

function hidePath(pathKey) {
    var h = getHiddenSkills();
    if (!h._paths) h._paths = {};
    h._paths[pathKey] = true;
    setHiddenSkills(h);
    loadGameList();
}

function toggleHiddenSkills() {
    var cur = localStorage.getItem('trpg-show-hidden') === '1';
    localStorage.setItem('trpg-show-hidden', cur ? '0' : '1');
    loadGameList();
}

function loadGameWithReset(path) {
    S.compiledDir = path;
    showLoading(true, '初始化新游戏...');
    fetch('/api/play/load', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_dir: path })
    }).then(r => r.json()).then(function(data) {
        if (data.error) { showLoading(false); alert(data.error); return; }
        return fetch('/api/play/reset', { method: 'POST' });
    }).then(r => r.json()).then(function(data) {
        showLoading(false);
        if (!data.ok) { alert('重置失败'); return; }
        startPlaySession(data.game_name);
    }).catch(function(e) { showLoading(false); });
}

function viewGameSaves(path) {
    S.compiledDir = path;
    showLoading(true, '加载中...');
    // 加载引擎（保存功能需要）+ 读取存档
    fetch('/api/play/load', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_dir: path })
    }).then(function(r) { return r.ok ? r.json() : { ok: false }; })
    .then(function(ld) {
        if (ld.error) { showLoading(false); alert(ld.error); return; }
        return fetch('/api/save/slots');
    }).then(function(r) { return r.json(); })
    .then(function(data) {
        showLoading(false);
        S.gameLoaded = true;
        document.getElementById('save-btn-top').style.display = 'inline-block';
        document.getElementById('save-overlay').classList.add('show');
        document.getElementById('save-drawer').classList.add('show');
        var html = '';
        (data.slots || []).forEach(function(s) {
            html += '<div class="slot-item">';
            html += '<div><div class="slot-info">' + escapeHtml(s.name) + '</div>';
            html += '<div class="slot-date">轮:' + s.turn + ' | ' + (s.date || '') + '</div></div>';
            html += '<div>';
            html += '<button class="save-load-btn" data-save-name="' + escapeHtml(s.name) + '" data-save-path="' + escapeHtml(path) + '">读取</button>';
            if (!s.is_auto) html += '<button class="del" onclick="deleteSave(\'' + escapeHtmlAttr(s.name) + '\')">删除</button>';
            html += '</div></div>';
        });
        document.getElementById('save-list').innerHTML = html || '<p style="color:var(--text2)">无存档</p>';
        bindSaveButtons();
    }).catch(function(e) {
        showLoading(false);
        alert('加载存档列表失败: ' + (e.message || ''));
    });
}

function loadGameByPath(path) {
    if (!path) { alert('请输入游戏目录路径'); return; }
    S.compiledDir = path;
    showLoading(true, '加载游戏中...');
    fetch('/api/play/load', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_dir: path })
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(data) {
        showLoading(false);
        if (data.error) { alert(data.error); return; }
        startPlaySession(data.game_name, data);
    }).catch(function(e) {
        showLoading(false);
        alert('加载失败: ' + (e.message || e));
    });
}

function scanCustomDir() {
    var dir = document.getElementById('game-dir-input').value.trim();
    if (!dir) { alert('请输入目录路径'); return; }
    showLoading(true, '扫描中...');
    fetch('/api/play/scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dir: dir })
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(data) {
        showLoading(false);
        if (data.error) { alert(data.error); return; }
        if (!data.skills || !data.skills.length) {
            alert('该目录下未发现 SKILL 子目录');
            return;
        }
        var paths = getCustomPaths();
        if (paths.indexOf(dir) < 0) {
            paths.push(dir);
            saveCustomPaths(paths);
        }
        loadGameList();
    }).catch(function(e) {
        showLoading(false);
        alert('扫描失败: ' + (e.message || e));
    });
}


function startPlaySession(gameName, loadData) {
    switchTab('play');
    S.gameLoaded = true;
    document.getElementById('save-btn-top').style.display = 'inline-block';
    document.getElementById('play-load').style.display = 'none';
    document.getElementById('play-active').style.display = 'flex';
    document.getElementById('narrative-area').innerHTML = '';
    document.getElementById('game-name-display').textContent = gameName;
    if (loadData) {
        updateGameInfo(loadData);
        renderHistory(loadData.history || []);
    } else {
        document.getElementById('game-info-display').textContent = '轮: 0';
    }
    nextRound();
}

function backToGameList() {
    S.gameLoaded = false;
    document.getElementById('save-btn-top').style.display = 'none';
    document.getElementById('play-load').style.display = 'flex';
    document.getElementById('play-active').style.display = 'none';
    document.getElementById('narrative-area').innerHTML = '';
    loadGameList();
}

function nextRound() {
    showLoadingBubble('推演中');
    fetch('/api/play/narrate', { method: 'POST' }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(data) {
        removeLoadingBubble();
        if (data.error) { alert(data.error); return; }
        appendNarrative(data.narrative);
        if (data.waiting) document.getElementById('player-input').focus();
        loadStatusToPanel();
    }).catch(function(err) {
        removeLoadingBubble();
        alert('错误: ' + (err.message || err));
    });
}

function appendNarrative(text) {
    if (!text) return;
    removeLoadingBubble();
    var area = document.getElementById('narrative-area');
    var div = document.createElement('div');
    div.className = 'gm-msg';
    div.textContent = text;
    // 动作按钮
    var actions = document.createElement('div');
    actions.className = 'gm-actions';
    actions.innerHTML = '<button onclick="editNarrative(this.parentElement.parentElement)">✏️</button>' +
        '<button onclick="rollbackNarrative(this.parentElement.parentElement)">↩</button>' +
        '<button onclick="regenerateNarrative(this.parentElement.parentElement)">🔄</button>';
    div.appendChild(actions);
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function removeLoadingBubble() {
    var loadings = document.querySelectorAll('#narrative-area .loading-msg');
    loadings.forEach(function(el) { el.remove(); });
}

function showLoadingBubble(text) {
    removeLoadingBubble();
    var area = document.getElementById('narrative-area');
    var div = document.createElement('div');
    div.className = 'loading-msg';
    div.textContent = text || '推演中';
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function editNarrative(gmDiv) {
    var current = gmDiv.textContent.replace(/✏️↩🔄/g, '').trim();
    var result = prompt('编辑叙事:', current);
    if (result !== null && result !== current) {
        gmDiv.firstChild.textContent = result;
    }
}

function rollbackNarrative(gmDiv) {
    if (!confirm('回滚到本轮开始？本轮叙事将被移除。')) return;
    // 移除当前及之后的 GM 和 player 消息
    var area = document.getElementById('narrative-area');
    var next = gmDiv.nextElementSibling;
    while (next) {
        var toRemove = next;
        next = next.nextElementSibling;
        toRemove.remove();
    }
    gmDiv.remove();
    // 重新生成
    fetch('/api/play/narrate', { method: 'POST' }).then(function(r) {
        if (!r.ok) throw new Error('请求失败');
        return r.json();
    }).then(function(data) {
        if (data.error) { alert(data.error); return; }
        appendNarrative(data.narrative);
        if (data.waiting) document.getElementById('player-input').focus();
    }).catch(function(err) { alert('错误: ' + err.message); });
}

function regenerateNarrative(gmDiv) {
    if (!confirm('重新生成本段叙事？这将调用 LLM 生成新的回复。')) return;
    gmDiv.remove();
    showLoadingBubble('重新生成中');
    fetch('/api/play/narrate', { method: 'POST' }).then(function(r) {
        return r.json();
    }).then(function(data) {
        if (data.error) { alert(data.error); return; }
        appendNarrative(data.narrative);
        if (data.waiting) document.getElementById('player-input').focus();
    }).catch(function(err) { alert('错误: ' + err.message); });
}

function sendInput() {
    var text = document.getElementById('player-input').value.trim();
    if (!text) return;

    // 显示玩家输入
    var userMsg = document.createElement('div');
    userMsg.className = 'player-msg';
    userMsg.textContent = text;
    document.getElementById('narrative-area').appendChild(userMsg);
    document.getElementById('narrative-area').scrollTop = document.getElementById('narrative-area').scrollHeight;

    document.getElementById('player-input').value = '';
    showLoadingBubble('处理中');

    fetch('/api/play/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(data) {
        removeLoadingBubble();
        if (data.error) { alert(data.error); return; }
        appendNarrative(data.narrative);
        updateGameInfo(data);
        if (data.waiting) document.getElementById('player-input').focus();
        loadStatusToPanel();
    }).catch(function(err) {
        removeLoadingBubble();
        alert('错误: ' + (err.message || err));
    });
}

function updateGameInfo(data) {
    var info = '轮: ' + (data.turn || 0) + ' | ' + (data.phase || '');
    if (data.location) info += ' | ' + data.location;
    document.getElementById('game-info-display').textContent = info;
}

// ═══════════════════ Settings ═══════════════════

function loadSettings() {
    loadProfiles();
    loadGameConfig();
}

function loadProfiles() {
    fetch('/api/config/profiles').then(r => r.json()).then(function(data) {
        var html = '';
        (data.profiles || []).forEach(function(p) {
            var active = p.name === (data.active.name || data.active);
            html += '<div style="padding:4px 0">';
            html += '<label style="cursor:pointer">';
            html += '<input type="radio" name="active-profile" ' + (active ? 'checked' : '') +
                    ' onchange="activateProfile(\'' + p.name + '\')" style="margin-right:6px" title="激活配置: ' + escapeHtml(p.name) + '">';
            html += escapeHtml(p.name) + ' (' + escapeHtml(p.model) + ') ' + (p.has_key ? '🔑' : '');
            html += '</label>';
            html += ' <button class="btn-icon" onclick="deleteProfile(\'' + p.name + '\')" style="padding:2px 6px;font-size:11px">删除</button>';
            html += '</div>';
        });
        document.getElementById('profile-list').innerHTML = html;

        // Fill form with active
        var a = data.active;
        if (a && a.name) {
            document.getElementById('pf-name').value = a.name || '';
            document.getElementById('pf-url').value = a.base_url || '';
            document.getElementById('pf-key').value = a.api_key || '';
            document.getElementById('pf-model').value = a.model || '';
            document.getElementById('pf-analyzer').value = a.analyzer_model || '';
        }
    });
}

function saveProfile() {
    var data = {
        name: document.getElementById('pf-name').value,
        base_url: document.getElementById('pf-url').value,
        api_key: document.getElementById('pf-key').value,
        model: document.getElementById('pf-model').value,
        analyzer_model: document.getElementById('pf-analyzer').value,
        temperature: 1.0, top_p: 0.95
    };
    fetch('/api/config/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }).then(r => r.json()).then(function() {
        loadProfiles();
    });
}

function activateProfile(name) {
    fetch('/api/config/profiles/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    }).then(r => r.json()).then(loadProfiles);
}

function deleteProfile(name) {
    if (!confirm('删除配置 ' + name + '?')) return;
    fetch('/api/config/profiles/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    }).then(r => r.json()).then(loadProfiles);
}

function testConnection() {
    document.getElementById('test-result').textContent = '测试中...';
    fetch('/api/config/test').then(r => r.json()).then(function(d) {
        if (d.ok) {
            document.getElementById('test-result').textContent =
                'OK ' + d.model + ' (' + d.latency_ms + 'ms): ' + d.response;
        } else {
            document.getElementById('test-result').textContent = '失败: ' + d.error;
        }
    });
}

function loadGameConfig() {
    fetch('/api/config/game').then(r => r.json()).then(function(d) {
        if (d.error) { document.getElementById('game-config-sliders').innerHTML = '<p style="color:var(--text2)">需先加载游戏</p>'; return; }
        var html = '';
        var labels = {
            'lorebook.max_injection_tokens': '注入量上限',
            'lorebook.default_scan_depth': '关键词扫描深度',
            'lorebook.recursive_depth': '递归触发深度',
            'lorebook.single_char_penalty': '单字惩罚系数',
            'memory.recent_window_rounds': '近期窗口轮数',
            'memory.summary_interval_rounds': '摘要间隔轮数',
            'memory.max_summary_entries': '最大摘要条目',
            'narrative.temperature': '叙事温度',
            'narrative.max_tokens': '输出上限',
            'protocol_guard.enabled': '协议检查',
            'protocol_guard.check_interval_rounds': '检查间隔',
            'protocol_guard.review_window_rounds': '审查窗口',
            'debug.show_token_usage': '显示Token用量',
            'debug.show_lorebook_hits': '显示Lorebook命中',
        };
        (d.fields || []).forEach(function(f) {
            var label = labels[f.key] || f.key.split('.').pop();
            html += '<div style="margin-bottom:8px">';
            html += '<div style="font-size:12px;color:var(--text2);margin-bottom:2px" title="' + (f.description || '') + '">' + label + '</div>';
            html += '<div class="config-row">';
            if (f.type === 'bool') {
                html += '<input type="checkbox" ' + (f.current ? 'checked' : '') +
                        ' onchange="updateGameConfig(\'' + f.key + '\', this.checked)" style="margin-right:auto">';
            } else if (f.type === 'float') {
                html += '<input type="range" min="' + (f.min || 0) + '" max="' + (f.max || 2) +
                        '" step="0.1" value="' + f.current + '" onchange="updateGameConfigSlider(this, \'' + f.key + '\')">';
                html += '<span class="config-val">' + f.current + '</span>';
            } else {
                html += '<input type="range" min="' + (f.min || 0) + '" max="' + (f.max || 100) +
                        '" step="1" value="' + f.current + '" onchange="updateGameConfigSlider(this, \'' + f.key + '\')">';
                html += '<span class="config-val">' + f.current + '</span>';
            }
            html += '</div></div>';
        });
        document.getElementById('game-config-sliders').innerHTML = html;
    });
}

function updateGameConfigSlider(slider, key) {
    slider.nextElementSibling.textContent = slider.value;
    updateGameConfig(key, slider.value, slider);
}

function updateGameConfig(key, value, slider) {
    fetch('/api/config/game/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key, value: value })
    }).then(r => r.json()).then(function() {
        if (slider) {
            slider.style.outline = '2px solid var(--green)';
            setTimeout(function() { slider.style.outline = ''; }, 800);
        }
    });
}

function resetGameConfig() {
    fetch('/api/config/game/reset', { method: 'POST' }).then(r => r.json()).then(loadGameConfig);
}

// ═══════════════════ Save Panel ═══════════════════

function toggleSavePanel(show) {
    if (show === undefined) show = !document.getElementById('save-drawer').classList.contains('show');
    document.getElementById('save-overlay').classList.toggle('show', show);
    document.getElementById('save-drawer').classList.toggle('show', show);
    if (show) loadSaves();
}

function bindSaveButtons() {
    document.querySelectorAll('.save-load-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            loadSave(this.dataset.saveName, this.dataset.savePath);
        });
    });
}

function loadSaves() {
    fetch('/api/save/slots').then(r => r.json()).then(function(data) {
        var html = '';
        (data.slots || []).forEach(function(s) {
            html += '<div class="slot-item">';
            html += '<div><div class="slot-info">' + s.name + '</div>';
            html += '<div class="slot-date">轮:' + s.turn + ' | ' + (s.date || '') + '</div></div>';
            html += '<div>';
            html += '<button class="save-load-btn" data-save-name="' + escapeHtml(s.name) + '" data-save-path="' + escapeHtml(S.compiledDir || '') + '">读取</button>';
            if (!s.is_auto) html += '<button class="del" onclick="deleteSave(\'' + escapeHtmlAttr(s.name) + '\')">删除</button>';
            html += '</div></div>';
        });
        document.getElementById('save-list').innerHTML = html || '<p style="color:var(--text2)">无存档</p>';
        bindSaveButtons();
    });
}

function manualSave() {
    fetch('/api/save/manual', { method: 'POST' }).then(r => r.json()).then(function(d) {
        if (d.ok) { loadSaves(); }
    });
}

function loadSave(name, gamePath) {
    if (!gamePath) gamePath = S.compiledDir || '';
    if (gamePath) S.compiledDir = gamePath;
    showLoading(true, '读取存档...');

    var ready;
    if (gamePath) {
        ready = fetch('/api/play/load', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_dir: gamePath })
        }).then(function(r) { return r.json(); });
    } else {
        ready = fetch('/api/play/state').then(function(r) { return r.ok ? r.json() : { ok: true }; });
    }

    ready.then(function(loadResult) {
        if (loadResult.error) throw new Error(loadResult.error);
        return fetch('/api/save/load/' + name, { method: 'POST' });
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(d) {
        showLoading(false);
        if (!d.ok) { alert(d.error || '读取失败'); return; }
        toggleSavePanel(false);
        document.getElementById('play-load').style.display = 'none';
        document.getElementById('play-active').style.display = 'flex';
        document.getElementById('save-btn-top').style.display = 'inline-block';
        updateGameInfo(d);
        renderHistory(d.history || []);
        nextRound();
    }).catch(function(e) {
        showLoading(false);
        alert('读取失败: ' + (e.message || e));
    });
}

function manualSave() {
    fetch('/api/save/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    }).then(function(r) {
        if (!r.ok) throw new Error('请求失败: ' + r.status);
        return r.json();
    }).then(function(d) {
        if (d.ok) { loadSaves(); }
        else { alert(d.error || '保存失败'); }
    }).catch(function(e) {
        alert('保存失败: ' + (e.message || e));
    });
}

function deleteSave(name) {
    if (!confirm('删除存档 ' + name + '?')) return;
    fetch('/api/save/' + name, { method: 'DELETE' }).then(r => r.json()).then(loadSaves);
}

// ═══════════════════ Lorebook Panel ═══════════════════

function toggleLorebook() {
    var panel = document.getElementById('lorebook-panel');
    panel.classList.toggle('show');
    if (panel.classList.contains('show')) loadLorebook();
}

// ═══════════════════ History Render ═══════════════════

function renderHistory(history) {
    var area = document.getElementById('narrative-area');
    area.innerHTML = '';
    if (!history || !history.length) return;
    for (var i = 0; i < history.length; i++) {
        var r = history[i];
        if (r.narrative) {
            var g = document.createElement('div');
            g.className = 'gm-msg';
            g.textContent = r.narrative;
            area.appendChild(g);
        }
        if (r.player_input) {
            var div = document.createElement('div');
            div.className = 'player-msg';
            div.textContent = r.player_input;
            area.appendChild(div);
        }
    }
    area.scrollTop = area.scrollHeight;
}

function loadLorebook() {
    fetch('/api/lorebook/entries').then(r => r.json()).then(function(data) {
        var html = '';
        (data.entries || []).forEach(function(e) {
            html += '<div class="lorebook-entry" onclick="this.classList.toggle(\'expanded\')">';
            html += '<div class="le-title">' + e.title + '</div>';
            html += '<div class="le-type">' + e.type + ' | ' + e.strategy + ' | P=' + e.priority;
            if (e.keys.length) html += ' | keys: ' + e.keys.join(', ');
            html += '</div>';
            html += '<div class="le-content">' + e.content + '</div>';
            html += '</div>';
        });
        document.getElementById('lorebook-list').innerHTML = html || '<p style="color:var(--text2)">无条目</p>';
    });
}

// ═══════════════════ Utils ═══════════════════

function editAgentsMd() {
    openEditPanel('agents');
}

function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function escapeHtmlAttr(s) {
    return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function showToast(msg) {
    var toast = document.getElementById('topbar-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'topbar-toast';
        toast.style.cssText = 'position:fixed;top:50px;left:50%;transform:translateX(-50%);'
            + 'padding:6px 16px;background:var(--accent);color:var(--btn-text);'
            + 'border-radius:6px;font-size:13px;z-index:300;opacity:0;transition:opacity 0.3s;'
            + 'pointer-events:none;white-space:nowrap';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(toast._tid);
    toast._tid = setTimeout(function() { toast.style.opacity = '0'; }, 3000);
}

function showLoading(show, text) {
    document.getElementById('loading-overlay').classList.toggle('show', show);
    if (text) document.getElementById('loading-text').textContent = text;
}

function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === name);
    });
    document.querySelectorAll('.tab-content').forEach(t => {
        t.classList.toggle('active', t.id === name + '-tab');
    });
    S.currentTab = name;
}

// Init
loadProfiles();
initDragDrop();
loadGameList();

// ═══════════════════ Theme Switcher ═══════════════════

var THEMES = [
    { id: 'dark', name: '暗色', css: '/themes/dark.css' },
    { id: 'oled', name: 'OLED', css: '/themes/oled.css' },
    { id: 'paper', name: '纸质', css: '/themes/paper.css' },
    { id: 'glass', name: '玻璃', css: '/themes/glass.css' },
    { id: 'cyberpunk', name: '赛博', css: '/themes/cyberpunk.css' },
];

initThemeSwitcher();

function initThemeSwitcher() {
    var html = '';
    var saved = localStorage.getItem('trpg-theme') || 'dark';
    THEMES.forEach(function(t) {
        html += '<label class="theme-option' + (t.id === saved ? ' active' : '') + '"' +
            ' data-theme="' + t.id + '">' +
            '<input type="radio" name="theme" value="' + t.id + '" ' +
            (t.id === saved ? 'checked' : '') +
            ' onchange="switchTheme(\'' + t.id + '\')">' +
            t.name + '</label>';
    });
    document.getElementById('theme-selector').innerHTML = html;
    applyTheme(saved);
}

function switchTheme(id) {
    localStorage.setItem('trpg-theme', id);
    applyTheme(id);
    initThemeSwitcher(); // refresh radio states
}

function applyTheme(id) {
    var t = THEMES.find(function(t) { return t.id === id; });
    if (t) {
        document.getElementById('theme-link').href = t.css;
    }
}

function getCurrentTheme() {
    return localStorage.getItem('trpg-theme') || 'dark';
}

// refresh theme selector border on settings tab
var origLoadSettings = loadSettings;
loadSettings = function() {
    origLoadSettings();
    initThemeSwitcher();
};

// ═══════════════════ Shutdown ═══════════════════

function shutdownServer() {
    if (!confirm('退出服务器？游戏状态会自动保存。')) return;
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#1a1a2e;color:#eee;font-size:20px;flex-direction:column;font-family:Segoe UI,Microsoft YaHei,sans-serif;"><div style="font-size:48px;">&#9632;</div><div style="margin-top:20px;font-weight:600;">TRPG-to-SKILL 已关闭</div><div style="font-size:13px;color:#aaa;margin-top:10px;">请关闭此窗口</div></div>';
    fetch('/api/config/shutdown');
}
