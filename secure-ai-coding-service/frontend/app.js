/* ─────────────────────────────────────────────────────────────────────────
   Secure AI Coding Service – Frontend Logic
   ───────────────────────────────────────────────────────────────────────── */

'use strict';

const API_BASE = '';   // Same-origin; change to 'http://localhost:8000' for dev

// ── Tab switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${target}`).classList.add('active');
  });
});

// ── Flow step helpers ──────────────────────────────────────────────────────
const STEPS = ['step1', 'step2', 'step3', 'step4', 'step5', 'step6'];

function resetSteps() {
  STEPS.forEach((id) => {
    const el = document.getElementById(id);
    el.classList.remove('active', 'done');
  });
}

function activateStep(n) {
  // Mark previous steps as done, current as active
  STEPS.forEach((id, i) => {
    const el = document.getElementById(id);
    if (i < n) {
      el.classList.remove('active');
      el.classList.add('done');
    } else if (i === n) {
      el.classList.remove('done');
      el.classList.add('active');
    } else {
      el.classList.remove('active', 'done');
    }
  });
}

function completeAllSteps() {
  STEPS.forEach((id) => {
    const el = document.getElementById(id);
    el.classList.remove('active');
    el.classList.add('done');
  });
}

// ── Loading state ──────────────────────────────────────────────────────────
function setLoading(loading) {
  const btn = document.getElementById('generateBtn');
  const label = document.getElementById('btnLabel');
  const spinner = document.getElementById('btnSpinner');
  btn.disabled = loading;
  if (loading) {
    label.textContent = '生成中...';
    spinner.classList.remove('hidden');
  } else {
    label.textContent = '🚀 SQL を生成する';
    spinner.classList.add('hidden');
  }
}

// ── Error display ──────────────────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById('errorBanner');
  el.textContent = `❌ エラー: ${msg}`;
  el.classList.remove('hidden');
}

function clearError() {
  const el = document.getElementById('errorBanner');
  el.textContent = '';
  el.classList.add('hidden');
}

// ── Clipboard ──────────────────────────────────────────────────────────────
function copyToClipboard(elementId) {
  const text = document.getElementById(elementId).textContent;
  if (!text || text === '-') return;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.currentTarget;
    const orig = btn.textContent;
    btn.textContent = '✅ コピー完了';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

// ── Main generate function ─────────────────────────────────────────────────
async function generate() {
  clearError();
  resetSteps();

  const createStatements = document.getElementById('createStatements').value.trim();
  const activeTab = document.querySelector('.tab.active').dataset.tab;
  const requirements =
    activeTab === 'json'
      ? document.getElementById('requirementsJson').value.trim()
      : document.getElementById('requirementsNatural').value.trim();

  if (!createStatements) {
    showError('CREATE文を入力してください。');
    return;
  }
  if (!requirements) {
    showError('抽出要件を入力してください。');
    return;
  }

  setLoading(true);
  activateStep(0);   // Step 1: sending

  // Simulate step progression while waiting for the API
  const stepTimer = simulateSteps();

  try {
    const response = await fetch(`${API_BASE}/api/generate-sql`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ create_statements: createStatements, requirements }),
    });

    clearInterval(stepTimer);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    document.getElementById('resultSql').textContent = data.sql || '(空のレスポンス)';
    document.getElementById('abstractSql').textContent = data.abstracted_sql || '-';
    completeAllSteps();

  } catch (err) {
    clearInterval(stepTimer);
    resetSteps();
    showError(err.message);
    document.getElementById('resultSql').textContent = 'SQL の生成に失敗しました。';
    document.getElementById('abstractSql').textContent = '-';
  } finally {
    setLoading(false);
  }
}

/** Animate flow steps during the API call (roughly 1 step / 1.2 s). */
function simulateSteps() {
  let current = 0;
  return setInterval(() => {
    if (current < STEPS.length - 1) {
      current++;
      activateStep(current);
    }
  }, 1200);
}
