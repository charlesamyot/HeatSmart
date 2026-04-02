/* Dashboard — live status + energy chart */

let energyChart = null;
let currentSetpoint = 120;

// ---- Force refresh ----
async function forceRefresh() {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = '↻ …';
  btn.disabled = true;
  try {
    await fetchWithTimeout('/api/refresh', { method: 'POST' });
    await loadStatus();
    await loadEnergy('day', document.querySelector('.tab-btn.active'));
    showToast('Refreshed from EcoNet.', 'success');
  } catch (e) {
    showToast('Refresh failed.', 'error');
  } finally {
    btn.textContent = '↻ Refresh';
    btn.disabled = false;
  }
}

// ---- Boot ----
loadStatus();
loadEnergy('day', document.querySelector('.tab-btn'));
setInterval(loadStatus, 30000);

// ---- Status ----
async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) return;
    const d = await r.json();

    // Hot water availability
    const avail = d.hot_water_avail;
    document.getElementById('hot-water-avail').textContent =
      avail !== null && avail !== undefined ? `${Math.round(avail)}%` : '—';
    document.getElementById('current-temp').textContent =
      d.current_temp ? `Temp: ${d.current_temp.toFixed(1)}°F` : '';

    // Setpoint
    currentSetpoint = d.setpoint;
    document.getElementById('setpoint-display').textContent = `${d.setpoint}°F`;

    // Mode — update popover button
    updateModeDisplay(d.mode);

    // Running indicator
    const dot = document.getElementById('running-dot');
    const label = document.getElementById('running-label');
    if (d.running) {
      dot.className = 'running-dot on';
      label.textContent = d.running_state || 'Heating';
    } else {
      dot.className = 'running-dot';
      label.textContent = 'Standby';
    }
  } catch (e) {
    console.warn('Status fetch failed:', e);
  }
}

// ---- Setpoint control ----
async function adjustSetpoint(delta) {
  const newTemp = Math.max(110, Math.min(140, currentSetpoint + delta));
  try {
    const r = await fetchWithTimeout('/api/setpoint', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({temperature: newTemp}),
    });
    if (r.ok) {
      currentSetpoint = newTemp;
      document.getElementById('setpoint-display').textContent = `${newTemp}°F`;
      showToast(`Setpoint set to ${newTemp}°F`, 'success');
    } else {
      showToast('Failed to update setpoint.', 'error');
    }
  } catch (e) {
    showToast(e.name === 'AbortError' ? 'Request timed out.' : 'Network error.', 'error');
  }
}

// ---- Mode change ----
// ---- Mode popover ----
const MODE_COLORS = {
  OFF: '#a0aec0', ENERGY_SAVING: '#38a169', HEAT_PUMP_ONLY: '#2b6cb0',
  HIGH_DEMAND: '#dd6b20', ELECTRIC_MODE: '#e53e3e', VACATION: '#805ad5',
};
let currentMode = 'OFF';

function updateModeDisplay(mode) {
  currentMode = mode;
  document.getElementById('mode-label').textContent = formatMode(mode);
  document.getElementById('mode-dot').style.background = MODE_COLORS[mode] || '#a0aec0';
  // Highlight active option
  document.querySelectorAll('.mode-option').forEach(el => {
    el.classList.toggle('active', el.dataset.mode === mode);
  });
}

function toggleModePopover() {
  document.getElementById('mode-popover').classList.toggle('open');
}

async function selectMode(mode) {
  document.getElementById('mode-popover').classList.remove('open');
  if (mode === currentMode) return;

  const btn = document.getElementById('mode-btn');
  btn.style.opacity = '.5';
  btn.style.pointerEvents = 'none';
  try {
    const r = await fetchWithTimeout('/api/mode', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode}),
    });
    if (r.ok) {
      updateModeDisplay(mode);
      showToast(`Mode set to ${formatMode(mode)}`, 'success');
    } else {
      const detail = await r.json().catch(() => ({}));
      showToast(detail.detail || `Failed to set mode`, 'error');
    }
  } catch (e) {
    showToast(e.name === 'AbortError' ? 'Timed out.' : 'Network error.', 'error');
  } finally {
    btn.style.opacity = '1';
    btn.style.pointerEvents = 'auto';
  }
}

// Close popover when clicking outside
document.addEventListener('click', (e) => {
  const popover = document.getElementById('mode-popover');
  const btn = document.getElementById('mode-btn');
  if (popover && !popover.contains(e.target) && !btn.contains(e.target)) {
    popover.classList.remove('open');
  }
});

// ---- Energy chart ----
async function loadEnergy(range, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const r = await fetch(`/api/energy?range=${range}`);
  const data = await r.json();

  document.getElementById('total-kwh').textContent = `${data.total_kwh.toFixed(3)} kWh`;
  document.getElementById('total-cost').textContent = `$${data.total_cost.toFixed(3)}`;

  const tierColor = {peak: '#e53e3e', mid_peak: '#dd6b20', off_peak: '#38a169'};
  const defaultColor = '#a0aec0';

  if (range === 'day' || range === 'yesterday') {
    // Hourly bars — filter to current hour for "today"
    let hourly = data.hourly || [];
    if (range === 'day') {
      const nowHour = new Date().getHours();
      hourly = hourly.filter(h => h.hour <= nowHour);
    }
    const labels = hourly.map(h => `${String(h.hour).padStart(2,'0')}:00`);
    const kwhs   = hourly.map(h => h.kwh);
    const colors = hourly.map(h => tierColor[h.tou_tier] || defaultColor);
    renderBar(labels, kwhs, colors, 'kWh');
  } else {
    // Daily bars for week/month
    const labels = data.daily.map(d => fmtDate(d.date));
    const kwhs   = data.daily.map(d => d.total_kwh);
    const colors = data.daily.map(() => '#2b6cb0');
    renderBar(labels, kwhs, colors, 'kWh');
  }

  // Update cost card
  const costLabel = range === 'yesterday' ? 'Yesterday' : 'Today';
  document.getElementById('today-cost').textContent = `${costLabel}: $${data.total_cost.toFixed(2)}`;
}

function renderBar(labels, values, colors, yLabel) {
  const ctx = document.getElementById('energy-chart').getContext('2d');
  if (energyChart) energyChart.destroy();
  energyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: yLabel,
        data: values,
        backgroundColor: colors,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {display: false}},
      scales: {
        y: {beginAtZero: true, title: {display: true, text: yLabel}},
        x: {ticks: {maxRotation: 45}},
      },
    },
  });
}

// ---- Helpers ----
function fmtDate(d) {
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', {month:'short', day:'numeric'});
}

function fmtDuration(secs) {
  if (!secs) return 'In progress';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatMode(mode) {
  const labels = {
    ENERGY_SAVING: 'Energy Saving',
    HEAT_PUMP_ONLY: 'Heat Pump Only',
    ELECTRIC_MODE: 'Electric Mode',
    HIGH_DEMAND: 'High Demand',
    VACATION: 'Vacation',
    PERFORMANCE: 'Performance',
    OFF: 'Off',
  };
  return labels[mode] || mode;
}
