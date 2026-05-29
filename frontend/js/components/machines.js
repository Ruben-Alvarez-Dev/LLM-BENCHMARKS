Components.machines = (main, state) => {
    const { machines } = state;
    main.innerHTML = `
        <div class="section-title"><span>Machines</span><button onclick="Components.showAddMachine()">+ Add Machine</button></div>
        <div id="machine-form"></div>
        ${machines.length ? '<table><tr><th>Name</th><th>Host</th><th>Chip</th><th>RAM</th><th>Engines</th><th>Status</th><th></th></tr>' +
            machines.map(m => `<tr><td><strong>${m.name}</strong></td><td>${m.host}${m.is_local?' (local)':''}</td><td>${m.chip||'-'}</td><td>${m.ram_gb ? m.ram_gb+' GB' : '-'}</td><td>${(m.engines||'').replace(/,/g,', ')}</td><td><span class="badge ${m.status==='online'?'ok':'pending'}">${m.status}</span></td><td><button class="danger" onclick="Components.deleteMachine(${m.id})">✕</button></td></tr>`).join('') + '</table>'
        : '<p style="color: var(--text-secondary)">No machines registered.</p>'}
    `;
};
Components.showAddMachine = () => {
    document.getElementById('machine-form').innerHTML = `
        <form onsubmit="Components.addMachine(event)">
            <label>Name</label><input name="name" placeholder="Mac Mini M1" required>
            <label>Host</label><input name="host" placeholder="mac-mini.local" required>
            <label>Port</label><input name="port" value="22">
            <label>User</label><input name="user" value="admin">
            <div style="margin-top:16px;display:flex;gap:8px">
                <button type="submit">Save</button>
                <button type="button" class="secondary" onclick="this.closest('form').remove()">Cancel</button>
            </div>
        </form>`;
};
Components.addMachine = async (e) => {
    e.preventDefault();
    await API.createMachine(Object.fromEntries(new FormData(e.target)));
    await App.loadInitialData();
};
Components.deleteMachine = async (id) => {
    if (!confirm('Delete this machine?')) return;
    await API.deleteMachine(id);
    await App.loadInitialData();
};
