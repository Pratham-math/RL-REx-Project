'use strict';
(() => {
  const data = window.RESEARCH_DATA;
  const labels = {resample: 'Resampling', rex: 'REx', rex_progress_cost: 'Progress + cost'};
  const methods = Object.keys(labels);
  const colors = {resample: '#929a9b', rex: '#5d7d9b', rex_progress_cost: '#326b53'};
  const number = value => Number(value).toLocaleString('en-US');
  const menu = document.querySelector('#menu-button');
  const sidebar = document.querySelector('#sidebar');
  menu?.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    sidebar.classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') {
      menu.click();
      menu.focus();
    }
  });
  const tabs = [...document.querySelectorAll('[data-method]')];
  function selectMethod(button) {
    tabs.forEach(tab => {
      const active = tab === button;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
    });
  }
  tabs.forEach((button, index) => {
    button.addEventListener('click', () => selectMethod(button));
    button.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        selectMethod(tabs[next]);
        tabs[next].focus();
      }
    });
  });
  const parent = document.querySelector('#parent-score');
  const child = document.querySelector('#child-score');
  function updateProgress() {
    if (!parent || !child) return;
    document.querySelector('#parent-output').value = Number(parent.value).toFixed(2);
    document.querySelector('#child-output').value = Number(child.value).toFixed(2);
    document.querySelector('#progress-reward').textContent = (0.5 * Math.max(0, Number(child.value) - Number(parent.value))).toFixed(2);
  }
  parent?.addEventListener('input', updateProgress);
  child?.addEventListener('input', updateProgress);
  updateProgress();
  const axis = document.querySelector('#budget-axis');
  const budget = document.querySelector('#budget-value');
  function renderCheckpoint() {
    if (!axis || !budget || !data) return;
    const selected = data.evaluationRows.filter(row => row.axis === axis.value && row.budget === Number(budget.value));
    const chart = document.querySelector('#checkpoint-chart');
    const tbody = document.querySelector('#checkpoint-table');
    chart.replaceChildren();
    tbody.replaceChildren();
    methods.forEach(method => {
      const rows = selected.filter(row => row.method === method);
      const solved = rows.filter(row => row.solved).length;
      const percent = rows.length ? solved / rows.length * 100 : 0;
      const bar = document.createElement('div');
      bar.className = 'checkpoint-bar';
      bar.innerHTML = `<div><span>${labels[method]}</span><b>${percent.toFixed(0)}% <small>(${solved}/5)</small></b></div><div class="checkpoint-track"><span style="--width:${percent}%;--bar-color:${colors[method]}"></span></div>`;
      chart.append(bar);
      const tr = document.createElement('tr');
      [labels[method], `${solved}/5 (${percent.toFixed(0)}%)`, number(rows.reduce((s,r) => s+r.prefix_calls, 0)), number(rows.reduce((s,r) => s+r.prefix_tokens, 0))].forEach(value => {
        const td = document.createElement('td');
        td.textContent = value;
        tr.append(td);
      });
      tbody.append(tr);
    });
    const description = axis.value === 'calls' ? `Recorded comparison at ${budget.value} completed calls per trial. Each solved problem contributes 20 percentage points.` : `Recorded comparison at ${number(budget.value)} tokens. Only completed prefixes at or below the threshold are eligible.`;
    document.querySelector('#checkpoint-description').textContent = description;
    chart.setAttribute('aria-label', description + ' ' + methods.map(m => {
      const solved = selected.filter(r => r.method===m && r.solved).length;
      return `${labels[m]}: ${solved} of 5 tasks.`;
    }).join(' '));
  }
  axis?.addEventListener('change', () => {
    budget.replaceChildren();
    const values = axis.value === 'calls' ? [1,2,3,4,5,6,7,8] : [1024,2048];
    values.forEach(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = axis.value === 'calls' ? `${value} calls` : `${number(value)} tokens`;
      budget.append(option);
    });
    budget.value = String(values.at(-1));
    renderCheckpoint();
  });
  budget?.addEventListener('change', renderCheckpoint);
  renderCheckpoint();
  document.querySelector('#method-filter')?.addEventListener('change', event => {
    document.querySelectorAll('[data-trial-method]').forEach(row => {
      row.hidden = event.target.value !== 'all' && row.dataset.trialMethod !== event.target.value;
    });
  });
  const suite = document.querySelector('#test-suite');
  const search = document.querySelector('#test-search');
  function renderTests() {
    if (!suite || !data) return;
    const text = (search?.value || '').toLowerCase().trim();
    const all = data.verification[suite.value].cases;
    const shown = all.filter(test => `${test.group} ${test.name}`.toLowerCase().includes(text));
    const tbody = document.querySelector('#test-cases');
    tbody.replaceChildren();
    if (!shown.length) {
      const row = tbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 2;
      cell.className = 'test-empty';
      cell.textContent = 'No matching test cases.';
    }
    shown.forEach(test => {
      const row = tbody.insertRow();
      row.insertCell().textContent = `${test.group.replace(/^tests\./,'')} · ${test.name}`;
      row.insertCell().textContent = test.status;
    });
    document.querySelector('#test-count').textContent = `${shown.length} of ${all.length} recorded tests`;
  }
  suite?.addEventListener('change', renderTests);
  search?.addEventListener('input', renderTests);
  renderTests();
  const dialog = document.querySelector('#image-dialog');
  let previousFocus;
  document.querySelectorAll('[data-zoom]').forEach(button => {
    button.addEventListener('click', () => {
      const source = button.querySelector('img');
      const image = dialog.querySelector('img');
      image.src = source.src;
      image.alt = source.alt;
      dialog.querySelector('p').textContent = source.alt;
      previousFocus = button;
      dialog.showModal();
    });
  });
  dialog?.querySelector('.dialog-close')?.addEventListener('click', () => dialog.close());
  dialog?.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
  dialog?.addEventListener('close', () => previousFocus?.focus());
})();
