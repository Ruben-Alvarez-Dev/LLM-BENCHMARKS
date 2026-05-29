Components.reports = (main, state) => {
    const { summary } = state;
    main.innerHTML = `
        <div class="section-title"><span>Reports & Comparison</span></div>
        ${summary.length ? '<table><tr><th>Machine</th><th>Tests</th><th>Passed</th><th>Avg tok/s</th><th>Max Ctx</th></tr>' +
            summary.map(s => `<tr><td>${s.machine_name}</td><td>${s.total_tests}</td><td>${s.passed}</td><td>${s.avg_speed||'-'}</td><td>${s.max_context ? (s.max_context/1024).toFixed(0)+'K' : '-'}</td></tr>`).join('') + '</table>'
        : '<p style="color: var(--text-secondary)">Run benchmarks to see reports.</p>'}
    `;
};
