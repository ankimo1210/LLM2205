/* app.js — Local LLM Chat frontend */

let currentConversationId = null;
let isStreaming = false;

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  setupEventListeners();
  await loadConversations();
}

function setupEventListeners() {
  const input = document.getElementById('msg-input');

  document.getElementById('send-btn').addEventListener('click', sendMessage);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea as user types
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  });

  document.getElementById('new-chat-btn').addEventListener('click', startNewChat);
}

// ── Sidebar ───────────────────────────────────────────────────────────────
async function loadConversations() {
  try {
    const resp = await fetch('/conversations');
    if (!resp.ok) return;
    const convs = await resp.json();
    renderConversations(convs);
  } catch (e) {
    console.warn('Failed to load conversations:', e);
  }
}

function renderConversations(convs) {
  const list = document.getElementById('conv-list');
  list.innerHTML = '';
  for (const conv of convs) {
    const el = document.createElement('div');
    el.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');
    el.textContent = formatConvLabel(conv);
    el.dataset.id = conv.id;
    el.addEventListener('click', () => loadConversation(conv.id));
    list.appendChild(el);
  }
}

function formatConvLabel(conv) {
  const d = new Date(conv.created_at);
  // created_at is ISO-8601 with UTC timezone from the API
  return d.toLocaleDateString('ja-JP', { month: '2-digit', day: '2-digit' })
    + ' ' + d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
    + ' #' + conv.id.slice(0, 6);
}

// ── Load conversation history ─────────────────────────────────────────────
async function loadConversation(id) {
  currentConversationId = id;
  highlightActiveConv(id);

  try {
    const resp = await fetch(`/conversations/${id}`);
    if (!resp.ok) return;
    const conv = await resp.json();

    const messagesEl = document.getElementById('messages');
    messagesEl.innerHTML = '';
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
  document.getElementById('messages').innerHTML = '';
  document.querySelectorAll('.conv-item').forEach((el) => el.classList.remove('active'));
  document.getElementById('msg-input').focus();
}

// ── Message rendering ─────────────────────────────────────────────────────
function appendMessage(role, content) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = content;

  wrapper.appendChild(bubble);
  document.getElementById('messages').appendChild(wrapper);
  return bubble;
}

function scrollToBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

// ── Send & stream ─────────────────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) return;

  const input = document.getElementById('msg-input');
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  // Reset textarea height after clearing
  input.style.height = 'auto';
  setStreaming(true);

  appendMessage('user', message);
  const assistantBubble = appendMessage('assistant', '');
  assistantBubble.classList.add('streaming');
  scrollToBottom();

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

      // Process complete SSE lines
      const lines = buffer.split('\n');
      buffer = lines.pop(); // last (possibly incomplete) line stays in buffer

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
    scrollToBottom();
    document.getElementById('msg-input').focus();
  }
}

function setStreaming(active) {
  isStreaming = active;
  document.getElementById('send-btn').disabled = active;
  document.getElementById('msg-input').disabled = active;
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
