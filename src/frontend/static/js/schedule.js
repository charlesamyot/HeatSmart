/* Schedule management + optimizer */

let pendingOptimized = null;
let currentEntries = [];

// ---- Boot ----
loadSchedule();
renderTouBar();

// ---- Schedule CRUD ----
async function loadSchedule() {
  const r = await fetch('/api/schedule');
  currentEntries = await r.json();
  renderScheduleTable(currentEntries);
}

function renderScheduleTable(entries) {
  const tbody = document.getElementById('schedule-body');
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-muted);text-align:center">No schedule entries</td></tr>';
    return;
  }
  tbody.innerHTML = entries.map(e => `
    <tr>
      <td>${e.time_of_day}</td>
      <td>${e.setpoint}°F</td>
      <td>${e.mode || 'Default'}</td>
      <td><span class="badge ${e.source === 'optimizer' ? 'badge--ok' : 'badge--unknown'}">${e.source}</span></td>
      <td><button class="btn btn--outline btn--sm" onclick="deleteEntry(${e.id})">Remove</button></td>
    </tr>
  `).join('');
}

function openAddForm() {
  const form = document.getElementById('add-form');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function addEntry() {
  const timeVal   = document.getElementById('new-time').value;
  const setpoint  = parseFloat(document.getElementById('new-setpoint').value);
  const mode      = document.getElementById('new-mode').value || null;

  if (!timeVal || isNaN(setpoint)) { showToast('Time and setpoint are required.', 'warn'); return; }
  if (setpoint < 110 || setpoint > 140) { showToast('Setpoint must be between 110°F and 140°F.', 'warn'); return; }

  const newEntries = [
    ...currentEntries.map(e => ({time_of_day: e.time_of_day, setpoint: e.setpoint, mode: e.mode})),
    {time_of_day: timeVal + ':00', setpoint, mode},
  ];

  if (newEntries.length > 4) { showToast('Maximum 4 schedule entries allowed.', 'warn'); return; }

  try {
    const r = await fetchWithTimeout('/api/schedule', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({entries: newEntries}),
    });
    if (r.ok) {
      document.getElementById('add-form').style.display = 'none';
      await loadSchedule();
      showToast('Schedule entry saved.', 'success');
    } else {
      showToast('Failed to save schedule entry.', 'error');
    }
  } catch (e) {
    showToast('Network error saving entry.', 'error');
  }
}

async function deleteEntry(id) {
  const remaining = currentEntries
    .filter(e => e.id !== id)
    .map(e => ({time_of_day: e.time_of_day, setpoint: e.setpoint, mode: e.mode}));

  try {
    const r = await fetchWithTimeout('/api/schedule', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({entries: remaining}),
    });
    if (r.ok) { await loadSchedule(); showToast('Entry removed.', 'success'); }
    else showToast('Failed to remove entry.', 'error');
  } catch (e) {
    showToast('Network error removing entry.', 'error');
  }
}

// ---- Optimizer ----
async function runOptimizer() {
  const btn = document.getElementById('optimize-btn');
  btn.textContent = '⏳ Optimizing…';
  btn.disabled = true;

  try {
    const r = await fetchWithTimeout('/api/schedule/optimize', {method: 'POST'}, 20000);
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      showToast(detail.detail || 'Optimization failed. Try again.', 'error');
      return;
    }
    const result = await r.json();
    pendingOptimized = result;
    showOptimizerResult(result);
  } catch (e) {
    const msg = e.name === 'AbortError'
      ? 'Optimization timed out. Try again.'
      : `Optimization error: ${e.message}`;
    showToast(msg, 'error');
  } finally {
    btn.textContent = '⚡ Optimize';
    btn.disabled = false;
  }
}

function showOptimizerResult(result) {
  document.getElementById('optimize-result').style.display = 'block';
  document.getElementById('current-cost-display').textContent =
    result.current_daily_cost ? `$${result.current_daily_cost.toFixed(4)}` : '—';
  document.getElementById('optimized-cost-display').textContent =
    `$${result.estimated_daily_cost.toFixed(4)}`;
  const badge = document.getElementById('savings-badge');
  if (result.savings_pct !== null && result.savings_pct !== undefined) {
    badge.textContent = `${result.savings_pct}% savings`;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
  document.getElementById('optimize-explanation').textContent = result.explanation;
}

async function applyOptimized() {
  if (!pendingOptimized) return;
  const r = await fetch('/api/schedule/apply', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({entries: pendingOptimized.suggested_entries}),
  });
  if (r.ok) {
    dismissOptimizer();
    await loadSchedule();
  } else {
    alert('Failed to apply schedule.');
  }
}

function dismissOptimizer() {
  document.getElementById('optimize-result').style.display = 'none';
  pendingOptimized = null;
}

// ---- TOU rate bar ----
function renderTouBar() {
  const ctx = document.getElementById('tou-bar-chart').getContext('2d');
  const now = new Date();
  const dow = (now.getDay() + 6) % 7; // convert Sun=0 to Mon=0
  const isWeekend = dow === 6; // Sunday

  // Build 24-hour color array per SCL TOU rules
  const colors = Array.from({length: 24}, (_, h) => {
    if (h < 6)                     return '#38a169'; // off-peak midnight-6
    if (!isWeekend && h >= 17 && h < 21) return '#e53e3e'; // peak 5-9 PM Mon-Sat
    return '#dd6b20';                                // mid-peak everything else
  });

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Array.from({length: 24}, (_, h) => `${String(h).padStart(2,'0')}:00`),
      datasets: [{data: Array(24).fill(1), backgroundColor: colors, borderWidth: 0}],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {display: false}, tooltip: {
        callbacks: {
          label: (ctx) => {
            const h = ctx.dataIndex;
            if (h < 6) return 'Off-Peak — $0.0837/kWh';
            if (!isWeekend && h >= 17 && h < 21) return 'Peak — $0.1674/kWh';
            return 'Mid-Peak — $0.1465/kWh';
          },
        },
      }},
      scales: {
        x: {ticks: {maxRotation: 45, font: {size: 10}}},
        y: {display: false},
      },
    },
  });
}
