Components.logs = async (main, state) => {
    main.innerHTML = '<div class="section-title"><span>Action Log (Trazabilidad)</span></div><div id="log-content">Loading...</div>';
    try {
        const data = await API.logs({ limit: 100 });
        const el = document.getElementById('log-content');
        if (!data.logs || !data.logs.length) { el.innerHTML = '<p style="color: var(--text-secondary)">No logs yet.</p>'; return; }
        el.innerHTML = '<table><tr><th>Time</th><th>Action ID</th><th>Action</th><th>Resource</th><th>Status</th><th>Duration</th><th>Progress</th><th>Error</th></tr>' +
            data.logs.map(l => `<tr>
                <td style="font-size:0.8em">${(l.created_at||'').slice(11,19)}</td>
                <td style="font-size:0.7em;color:var(--text-secondary)">${(l.action_id||'').slice(0,8)}...</td>
                <td>${l.action_type}</td>
                <td>${l.resource_type||'-'}${l.resource_id ? '#'+l.resource_id : ''}</td>
                <td><span class="badge ${l.status}">${l.status}</span></td>
                <td>${l.duration_ms ? (l.duration_ms/1000).toFixed(1)+'s' : '-'}</td>
                <td>${l.progress_message ? l.progress_message : (l.progress_pct ? l.progress_pct+'%' : '-')}</td>
                <td style="color:var(--red);font-size:0.85em">${l.error_message||''}</td>
            </tr>`).join('') + '</table>';
    } catch(e) {
        document.getElementById('log-content').innerHTML = '<p style="color:var(--red)">Error loading logs: ' + e.message + '</p>';
    }
};
