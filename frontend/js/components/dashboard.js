/* Dashboard Component */
const Components = Components || {};
Components.dashboard = (main, state) => {
    const { machines, models, benchmarks, summary } = state;
    const totalMachines = machines.length;
    const totalModels = models.length;
    const totalTests = benchmarks.length;
    const passedTests = benchmarks.filter(b => b.status === 'ok').length;
    main.innerHTML = `
        <div class="cards">
            <div class="card"><div class="value">${totalMachines}</div><div class="label">Machines</div></div>
            <div class="card"><div class="value">${totalModels}</div><div class="label">Models</div></div>
            <div class="card"><div class="value">${totalTests}</div><div class="label">Tests (${passedTests} ok)</div></div>
            <div class="card"><div class="value">${summary.length}</div><div class="label">Machine Reports</div></div>
        </div>
        <div class="section-title"><span>Benchmark Summary by Machine</span></div>
        ${summary.length ? renderSummaryTable(summary) : '<p style="color: var(--text-secondary)">No benchmarks yet.</p>'}
        <div class="section-title"><span>Activity Log</span><a href="#/logs" style="color:var(--accent);font-size:0.85em">View all →</a></div>
        <div id="activity-feed">Loading...</div>
    `;
    API.logs({ limit: 10 }).then(data => {
        const feed = document.getElementById('activity-feed');
        if (!data.logs || !data.logs.length) { feed.innerHTML = '<p style="color: var(--text-secondary)">No activity yet.</p>'; return; }
        feed.innerHTML = '<table><tr><th>Time</th><th>Action</th><th>Status</th><th>Duration</th></tr>' +
            data.logs.map(l => `<tr><td>${(l.created_at||'').slice(11,19)}</td><td>${l.action_type}</td><td><span class="badge ${l.status}">${l.status}</span></td><td>${l.duration_ms ? (l.duration_ms/1000).toFixed(1)+'s' : '-'}</td></tr>`).join('') + '</table>';
    }).catch(() => {});
};
function renderSummaryTable(summary) {
    return '<table><tr><th>Machine</th><th>Tests</th><th>Passed</th><th>Avg tok/s</th><th>Max Context</th></tr>' +
        summary.map(s => `<tr><td>${s.machine_name||'Unknown'}</td><td>${s.total_tests||0}</td><td>${s.passed||0}</td><td>${s.avg_speed||'-'}</td><td>${s.max_context ? (s.max_context/1024).toFixed(0)+'K' : '-'}</td></tr>`).join('') + '</table>';
}
