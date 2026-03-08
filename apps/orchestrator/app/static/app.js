/* app.js — Local LLM Chat frontend */

let currentConversationId = null;
let isStreaming = false;
let defaultModel = null;

// ── DOM refs ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  setupEventListeners();
  await Promise.all([loadModels(), loadConversations()]);
}

// ── Model selector ────────────────────────────────────────────────────────
async function loadModels() {
  const select = $('model-select');
  try {
    const resp = await fetch('/models');
    if (!resp.ok) throw new Error(resp.statusText);
    const body = await resp.json();
    defaultModel = body.default_model || null;
    const models = body.data || [];

    select.innerHTML = '';
    if (models.length === 0) {
      // No models returned — use default
      const opt = document.createElement('option');
      opt.value = defaultModel || '';
      opt.textContent = defaultModel || '(default)';
      select.appendChild(opt);
    } else {
      for (const m of models) {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.id;
        select.appendChild(opt);
      }
    }

    // Restore from localStorage
    const saved = localStorage.getItem('selectedModel');
    if (saved && [...select.options].some((o) => o.value === saved)) {
      select.value = saved;
    } else if (defaultModel && [...select.options].some((o) => o.value === defaultModel)) {
      select.value = defaultModel;
    }
  } catch (e) {
    console.warn('Failed to load models:', e);
    select.innerHTML = '';
    const opt = document.createElement('option');
    opt.value = defaultModel || '';
    opt.textContent = (defaultModel || 'default') + ' (offline)';
    select.appendChild(opt);
  }
}

function getSelectedModel() {
  const v = $('model-select').value;
  return v || defaultModel || undefined;
}

function setupEventListeners() {
  const input = $('msg-input');

  $('send-btn').addEventListener('click', sendMessage);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener('input', autoResize);

  $('new-chat-btn').addEventListener('click', startNewChat);

  $('model-select').addEventListener('change', () => {
    localStorage.setItem('selectedModel', $('model-select').value);
  });
}

function autoResize() {
  const input = $('msg-input');
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
}

// ── Sidebar ───────────────────────────────────────────────────────────────
async function loadConversations() {
  try {
    const resp = await fetch('/conversations');
    if (!resp.ok) return;
    const convs = await resp.json();

    // Fetch first user message for each conversation (in parallel, max 20)
    const details = await Promise.all(
      convs.slice(0, 30).map(async (conv) => {
        try {
          const r = await fetch(`/conversations/${conv.id}`);
          if (!r.ok) return { ...conv, preview: '' };
          const d = await r.json();
          const first = d.messages.find((m) => m.role === 'user');
          return { ...conv, preview: first ? first.content : '' };
        } catch {
          return { ...conv, preview: '' };
        }
      })
    );

    renderConversations(details);
  } catch (e) {
    console.warn('Failed to load conversations:', e);
  }
}

function renderConversations(convs) {
  const list = $('conv-list');
  list.innerHTML = '';
  for (const conv of convs) {
    const el = document.createElement('div');
    el.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');
    el.dataset.id = conv.id;

    const preview = document.createElement('span');
    preview.className = 'conv-preview';
    preview.textContent = conv.preview
      ? conv.preview.slice(0, 40) + (conv.preview.length > 40 ? '…' : '')
      : '#' + conv.id.slice(0, 8);

    const time = document.createElement('span');
    time.className = 'conv-time';
    time.textContent = formatTime(conv.created_at);

    el.appendChild(preview);
    el.appendChild(time);
    el.addEventListener('click', () => loadConversation(conv.id));
    list.appendChild(el);
  }
}

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('ja-JP', { month: '2-digit', day: '2-digit' })
    + ' ' + d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
}

// ── Load conversation history ─────────────────────────────────────────────
async function loadConversation(id) {
  currentConversationId = id;
  highlightActiveConv(id);

  try {
    const resp = await fetch(`/conversations/${id}`);
    if (!resp.ok) return;
    const conv = await resp.json();

    clearMessages();
    for (const msg of conv.messages) {
      appendMessage(msg.role, msg.content);
    }
    scrollToBottom();
  } catch (e) {
    console.warn('Failed to load conversation:', e);
  }
}

function highlightActiveConv(id) {
  document.querySelectorAll('.conv-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
}

// ── New chat ──────────────────────────────────────────────────────────────
function startNewChat() {
  currentConversationId = null;
  clearMessages();
  document.querySelectorAll('.conv-item').forEach((el) => el.classList.remove('active'));
  $('msg-input').focus();
}

function clearMessages() {
  const el = $('messages');
  el.innerHTML = '';
  // Restore empty state
  const empty = document.createElement('div');
  empty.id = 'empty-state';
  empty.innerHTML = '<div class="empty-icon">💬</div><p>メッセージを送信して会話を始めましょう</p>';
  el.appendChild(empty);
}

function hideEmptyState() {
  const empty = $('empty-state');
  if (empty) empty.remove();
}

// ── Markdown / math rendering ─────────────────────────────────────────────
function renderMarkdown(text) {
  // Convert \( ... \) and \[ ... \] to KaTeX-safe placeholders,
  // then run marked, sanitize, and render math.
  const mathBlocks = [];
  const placeholder = (i) => `%%MATH_${i}%%`;

  // Collect block math \[ ... \] (must come before inline)
  let processed = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, expr) => {
    const i = mathBlocks.length;
    mathBlocks.push({ expr: expr.trim(), display: true });
    return placeholder(i);
  });
  // Collect inline math \( ... \)
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, expr) => {
    const i = mathBlocks.length;
    mathBlocks.push({ expr: expr.trim(), display: false });
    return placeholder(i);
  });

  // marked → DOMPurify
  const rawHtml = marked.parse(processed, { breaks: true, gfm: true });
  let clean = DOMPurify.sanitize(rawHtml, {
    ADD_TAGS: ['span'],
    ADD_ATTR: ['class', 'style', 'aria-hidden'],
  });

  // Re-inject KaTeX rendered math
  for (let i = 0; i < mathBlocks.length; i++) {
    const { expr, display } = mathBlocks[i];
    let rendered;
    try {
      rendered = katex.renderToString(expr, { displayMode: display, throwOnError: false });
    } catch {
      rendered = display ? `\\[${expr}\\]` : `\\(${expr}\\)`;
    }
    clean = clean.replace(placeholder(i), rendered);
  }
  return clean;
}

// ── Message rendering ─────────────────────────────────────────────────────
function appendMessage(role, content) {
  hideEmptyState();

  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const inner = document.createElement('div');
  inner.className = 'message-inner';

  const badge = document.createElement('div');
  badge.className = 'role-badge';
  badge.textContent = role === 'user' ? 'You' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (role === 'assistant' && content) {
    bubble.classList.add('markdown-body');
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }

  inner.appendChild(badge);
  inner.appendChild(bubble);
  row.appendChild(inner);
  $('messages').appendChild(row);
  return bubble;
}

function scrollToBottom() {
  const el = $('messages');
  el.scrollTop = el.scrollHeight;
}

// ── Status bar ────────────────────────────────────────────────────────────
function showStatus(text) {
  let bar = $('status-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'status-bar';
    $('input-area').parentNode.insertBefore(bar, $('input-area'));
  }
  bar.textContent = text;
  bar.classList.add('visible');
}

function hideStatus() {
  const bar = $('status-bar');
  if (bar) bar.classList.remove('visible');
}

// ── Send & stream ─────────────────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) return;

  const input = $('msg-input');
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  input.style.height = 'auto';
  setStreaming(true);

  let streamedText = '';
  appendMessage('user', message);
  const assistantBubble = appendMessage('assistant', '');
  assistantBubble.classList.add('streaming');
  scrollToBottom();
  showStatus('生成中…');

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentConversationId || undefined,
        model: getSelectedModel(),
        message,
      }),
    });

    if (!response.ok) {
      assistantBubble.textContent = `エラー: ${response.status} ${response.statusText}`;
      assistantBubble.classList.add('error');
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let data;
        try { data = JSON.parse(jsonStr); } catch { continue; }

        if (data.type === 'start') {
          currentConversationId = data.conversation_id;
        } else if (data.type === 'token') {
          streamedText += data.content;
          assistantBubble.textContent = streamedText;
          scrollToBottom();
        } else if (data.type === 'error') {
          assistantBubble.textContent = `エラー: ${data.message}`;
          assistantBubble.classList.add('error');
        } else if (data.type === 'done') {
          // Final render: markdown + math
          assistantBubble.classList.add('markdown-body');
          assistantBubble.innerHTML = renderMarkdown(streamedText);
          await loadConversations();
        }
      }
    }
  } catch (e) {
    assistantBubble.textContent = `接続エラー: ${e.message}`;
    assistantBubble.classList.add('error');
  } finally {
    assistantBubble.classList.remove('streaming');
    setStreaming(false);
    hideStatus();
    scrollToBottom();
    $('msg-input').focus();
  }
}

function setStreaming(active) {
  isStreaming = active;
  const btn = $('send-btn');
  btn.disabled = active;
  $('msg-input').disabled = active;
  $('send-label').hidden = active;
  $('send-spinner').hidden = !active;
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
