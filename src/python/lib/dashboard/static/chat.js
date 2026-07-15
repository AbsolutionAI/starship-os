/* ── Chat View ──────────────────────────────────────────────────────────── */

let chatAbortController = null;
let chatStreaming = false;

async function renderChatView(area, data) {
  const agentName = data?.agent || '';
  area.innerHTML = `
    <div id="chat-container">
      <div id="chat-toolbar" style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
        <button class="chat-session-btn" id="chat-new-btn">+ New Session</button>
        <select id="chat-agent-select" style="background:#25264a;border:1px solid #3d3f6b;color:#ccc;padding:6px 10px;border-radius:6px;font-size:12px">
          ${S.agents.map(a => `<option value="${escapeHtml(a.name)}" ${a.name === agentName ? 'selected' : ''}>${escapeHtml(a.name)}</option>`).join('')}
        </select>
        <select id="chat-model-select" style="background:#25264a;border:1px solid #3d3f6b;color:#ccc;padding:6px 10px;border-radius:6px;font-size:12px">
          <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
          <option value="claude-4-opus">Claude 4 Opus</option>
          <option value="gpt-4.1">GPT 4.1</option>
          <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
        </select>
        <div style="flex:1"></div>
        <span id="chat-status" style="font-size:12px;color:#666"></span>
      </div>
      <div id="chat-messages"></div>
      <div id="chat-composer">
        <textarea id="chat-input" rows="1" placeholder="Type a message..." style="flex:1;background:#25264a;border:1px solid #3d3f6b;border-radius:8px;padding:10px 14px;color:#fff;resize:none;min-height:42px;max-height:120px;font-size:13px;line-height:1.5"></textarea>
        <button id="chat-send" class="btn btn-primary" style="height:42px;padding:10px 20px">Send</button>
      </div>
    </div>
  `;

  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const messages = document.getElementById('chat-messages');
  const agentSelect = document.getElementById('chat-agent-select');
  const modelSelect = document.getElementById('chat-model-select');
  const status = document.getElementById('chat-status');

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  // Enter to send (Shift+Enter for newline)
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);

  document.getElementById('chat-new-btn').addEventListener('click', () => {
    S.currentChatSession = null;
    messages.innerHTML = '';
    status.textContent = '';
    input.value = '';
    addSystemMessage('New chat session started. Select an agent and send a message.');
  });

  function addMessage(content, role, agent) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (agent && role === 'assistant') {
      div.innerHTML = `<strong>${escapeHtml(agent)}</strong><br>${escapeHtml(content)}`;
    } else {
      div.textContent = content;
    }
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function addToolCall(tool, status, preview) {
    const div = document.createElement('div');
    div.className = 'tool-call';
    div.innerHTML = `
      <div class="tool-call-header">
        <span>&#9881;</span> ${escapeHtml(tool)}
        <span class="tool-status ${status}">${escapeHtml(status)}</span>
      </div>
      ${preview ? `<div class="tool-preview">${escapeHtml(preview)}</div>` : ''}
    `;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || chatStreaming) return;

    const agent = agentSelect.value;
    const model = modelSelect.value;

    addMessage(text, 'user');
    input.value = '';
    input.style.height = '42px';

    chatStreaming = true;
    sendBtn.disabled = true;
    status.textContent = 'Connecting...';

    try {
      const res = await api(`/api/agent/${encodeURIComponent(agent)}/chat`, {
        method: 'POST',
        body: { message: text, model: model },
      });

      if (!res || !res.session_id) {
        addSystemMessage('Failed to start chat session.');
        chatStreaming = false;
        sendBtn.disabled = false;
        status.textContent = '';
        return;
      }

      S.currentChatSession = res.session_id;
      status.textContent = 'Streaming...';

      // Connect to SSE stream
      const streamUrl = `/api/agent/${encodeURIComponent(agent)}/stream?session=${res.session_id}`;
      const eventSource = new EventSource(streamUrl);

      let currentToolCall = null;

      eventSource.addEventListener('message', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.content && data.agent) {
            addMessage(data.content, 'assistant', data.agent);
          }
        } catch (err) { /* ignore parse errors */ }
      });

      eventSource.addEventListener('tool_call', (e) => {
        try {
          const data = JSON.parse(e.data);
          currentToolCall = addToolCall(data.tool, data.status, data.preview);
        } catch (err) { /* ignore */ }
      });

      eventSource.addEventListener('tool_result', (e) => {
        try {
          const data = JSON.parse(e.data);
          if (currentToolCall) {
            const statusEl = currentToolCall.querySelector('.tool-status');
            if (statusEl) {
              statusEl.className = `tool-status ${data.status}`;
              statusEl.textContent = data.status === 'complete' ? 'Complete' : data.status;
            }
            if (data.result) {
              const preview = currentToolCall.querySelector('.tool-preview');
              if (preview) {
                preview.textContent = data.result;
              } else {
                const div = document.createElement('div');
                div.className = 'tool-preview';
                div.textContent = data.result;
                currentToolCall.appendChild(div);
              }
            }
          }
        } catch (err) { /* ignore */ }
      });

      eventSource.addEventListener('done', () => {
        eventSource.close();
        chatStreaming = false;
        sendBtn.disabled = false;
        status.textContent = 'Ready';
      });

      eventSource.addEventListener('error', () => {
        eventSource.close();
        chatStreaming = false;
        sendBtn.disabled = false;
        status.textContent = 'Disconnected';
        addSystemMessage('Stream disconnected. Response may be incomplete.');
      });

      eventSource.addEventListener('timeout', () => {
        eventSource.close();
        chatStreaming = false;
        sendBtn.disabled = false;
        status.textContent = 'Ready';
      });

    } catch (err) {
      addSystemMessage(`Error: ${err.message}`);
      chatStreaming = false;
      sendBtn.disabled = false;
      status.textContent = 'Error';
    }
  }

  // Initial greeting
  if (!S.currentChatSession) {
    addSystemMessage(`Chat interface ready. ${agentName ? `Selected agent: ${agentName}.` : 'Select an agent and send a message to begin.'}`);
  }
}
