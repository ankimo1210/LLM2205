/* app.js — Local LLM Chat frontend */

let currentConversationId = null;
let isStreaming = false;

// ── DOM refs ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  setupEventListeners();
  await loadConversations();
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
  bubble.textContent = content;

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
          assistantBubble.textContent += data.content;
          scrollToBottom();
        } else if (data.type === 'error') {
          assistantBubble.textContent = `エラー: ${data.message}`;
          assistantBubble.classList.add('error');
        } else if (data.type === 'done') {
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
