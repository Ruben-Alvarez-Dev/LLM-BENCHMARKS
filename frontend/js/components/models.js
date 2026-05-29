Components.models = (main, state) => {
    const { models } = state;
    main.innerHTML = `
        <div class="section-title"><span>Models Catalog</span><span>${models.length} found</span></div>
        ${models.length ? '<table><tr><th>Name</th><th>Format</th><th>Size</th><th>Params</th><th>Context</th><th>Machine</th></tr>' +
            models.map(m => `<tr><td><strong>${m.name}</strong></td><td>${m.format}</td><td>${m.size_bytes ? (m.size_bytes/1e9).toFixed(1)+' GB' : '-'}</td><td>${m.params_b ? m.params_b+'B' : '-'}</td><td>${m.context_max ? (m.context_max/1024).toFixed(0)+'K' : '-'}</td><td>${m.machine_name||'-'}</td></tr>`).join('') + '</table>'
        : '<p style="color: var(--text-secondary)">No models discovered yet.</p>'}
    `;
};
