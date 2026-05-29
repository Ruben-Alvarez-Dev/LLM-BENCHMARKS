Components.benchmarks = (main, state) => {
    const { benchmarks } = state;
    main.innerHTML = `
        <div class="section-title"><span>Benchmarks</span><span>${benchmarks.length} total</span></div>
        ${benchmarks.length ? '<table><tr><th>Model</th><th>Machine</th><th>tok/s</th><th>Context</th><th>RAM</th><th>Status</th></tr>' +
            benchmarks.map(b => `<tr><td>${b.model_name||'-'}</td><td>${b.machine_name||'-'}</td><td>${b.decode_speed ? b.decode_speed.toFixed(1) : '-'}</td><td>${b.context_len ? (b.context_len/1024).toFixed(0)+'K' : '-'}</td><td>${b.ram_peak_gb ? b.ram_peak_gb.toFixed(1)+' GB' : '-'}</td><td><span class="badge ${b.status}">${b.status}</span></td></tr>`).join('') + '</table>'
        : '<p style="color: var(--text-secondary)">No benchmarks yet.</p>'}
    `;
};
