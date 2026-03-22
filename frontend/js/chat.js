/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — AI Coach Chat
   Multi-conversation support, persistent memory, voice input
   ═══════════════════════════════════════════════════════════════════════════ */

const Chat = {
    recognition: null,
    isRecording: false,
    _currentConversationId: null,
    _conversations: [],
    _introShown: false,

    async init() {
        if (!App.state.currentUser) return;

        this.initInput();
        this.initVoice();
        this.initConversationControls();
        await this.loadConversations();
    },

    // ─── Conversation List ──────────────────────────────────────────────────

    async loadConversations() {
        try {
            this._conversations = await App.api(
                `/users/${App.state.currentUser.id}/conversations`
            );
        } catch (err) {
            console.error('Failed to load conversations:', err);
            this._conversations = [];
        }

        this.renderConversationList();

        // If there are conversations, load the most recent one
        if (this._conversations.length > 0) {
            this.switchConversation(this._conversations[0].id);
        } else {
            // No conversations yet — show welcome + trigger coach intro
            this._currentConversationId = null;
            this.showChatWelcome();
            this.triggerCoachIntro();
        }
    },

    renderConversationList() {
        const list = document.getElementById('conversation-list');
        if (!list) return;

        if (this._conversations.length === 0) {
            list.innerHTML = `
                <div class="conv-empty">
                    <p class="conv-empty-text">No conversations yet</p>
                </div>
            `;
            return;
        }

        list.innerHTML = this._conversations.map(conv => {
            const isActive = conv.id === this._currentConversationId;
            const date = new Date(conv.updated_at || conv.created_at);
            const timeStr = this._formatConvTime(date);
            const msgCount = conv.message_count || 0;

            return `
                <button class="conv-item ${isActive ? 'active' : ''}" data-conv-id="${conv.id}">
                    <div class="conv-item-content">
                        <span class="conv-item-title">${this._escapeHtml(conv.title || 'New Chat')}</span>
                        <span class="conv-item-meta">${msgCount} msg · ${timeStr}</span>
                    </div>
                    <button class="conv-delete-btn" data-conv-del="${conv.id}" title="Delete">✕</button>
                </button>
            `;
        }).join('');

        // Wire up click handlers
        list.querySelectorAll('.conv-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete-btn')) return;
                const id = parseInt(el.dataset.convId);
                this.switchConversation(id);
                this.hideDrawer();
            });
        });

        list.querySelectorAll('.conv-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.convDel);
                const conv = this._conversations.find(c => c.id === id);
                if (!confirm(`Delete "${conv?.title || 'this chat'}"?`)) return;
                await this.deleteConversation(id);
            });
        });
    },

    async switchConversation(convId) {
        this._currentConversationId = convId;
        this.renderConversationList();
        await this.loadHistory();

        // Update header title
        const conv = this._conversations.find(c => c.id === convId);
        const title = document.getElementById('chat-conv-title');
        if (title) title.textContent = conv?.title || 'Chat';
    },

    async deleteConversation(convId) {
        try {
            await App.api(
                `/users/${App.state.currentUser.id}/conversations/${convId}`,
                { method: 'DELETE' }
            );
            App.toast('Chat deleted', 'success');

            // Refresh list
            this._conversations = this._conversations.filter(c => c.id !== convId);

            if (this._currentConversationId === convId) {
                if (this._conversations.length > 0) {
                    this.switchConversation(this._conversations[0].id);
                } else {
                    this._currentConversationId = null;
                    this.showChatWelcome();
                }
            }
            this.renderConversationList();
        } catch (err) {
            App.toast('Failed to delete chat', 'error');
        }
    },

    async startNewChat() {
        this._currentConversationId = null;
        this.showChatWelcome();
        this.hideDrawer();

        // Update header
        const title = document.getElementById('chat-conv-title');
        if (title) title.textContent = App.state.currentUser?.coach_name || 'Coach';
    },

    showChatWelcome() {
        const container = document.getElementById('chat-messages');
        const coachName = App.state.currentUser?.coach_name || 'Coach';
        container.innerHTML = `
            <div class="chat-welcome">
                <p class="chat-welcome-icon">🤖</p>
                <p class="chat-welcome-text">
                    I'm <strong>${this._escapeHtml(coachName)}</strong>, your nutrition coach.<br>
                    Ask me anything about your diet, goals, or meal planning.
                </p>
            </div>
        `;
    },

    async triggerCoachIntro() {
        // Only trigger once per user session and only if zero conversations exist
        if (this._introShown || this._conversations.length > 0) return;
        this._introShown = true;

        // Check if user has any prior conversations at all
        if (this._conversations.length > 0) return;

        this.showTyping();
        try {
            const result = await App.api(
                `/users/${App.state.currentUser.id}/chat/intro`,
                { method: 'POST' }
            );

            this.hideTyping();
            this._currentConversationId = result.conversation_id;

            // Add welcome user message + coach response
            const container = document.getElementById('chat-messages');
            container.innerHTML = '';
            const coachName = App.state.currentUser?.coach_name || 'Coach';
            this.addBubble('user', `Hi ${coachName}! I just signed up and I'm ready to start my journey.`);
            this.addBubble('assistant', result.response);

            // Refresh conversation list
            this._conversations = await App.api(
                `/users/${App.state.currentUser.id}/conversations`
            );
            this.renderConversationList();
        } catch (err) {
            this.hideTyping();
            console.error('Coach intro failed:', err);
            // Non-critical — user can still chat normally
        }
    },

    initConversationControls() {
        // New chat button
        const newBtn = document.getElementById('new-chat-btn');
        if (newBtn) {
            const fresh = newBtn.cloneNode(true);
            newBtn.parentNode.replaceChild(fresh, newBtn);
            fresh.addEventListener('click', () => this.startNewChat());
        }

        // Drawer toggle
        const drawerBtn = document.getElementById('chat-drawer-btn');
        if (drawerBtn) {
            const fresh = drawerBtn.cloneNode(true);
            drawerBtn.parentNode.replaceChild(fresh, drawerBtn);
            fresh.addEventListener('click', () => this.toggleDrawer());
        }

        // Drawer backdrop
        const backdrop = document.getElementById('conv-drawer-backdrop');
        if (backdrop) {
            backdrop.addEventListener('click', () => this.hideDrawer());
        }
    },

    toggleDrawer() {
        const drawer = document.getElementById('conv-drawer');
        const backdrop = document.getElementById('conv-drawer-backdrop');
        if (!drawer) return;
        const open = drawer.classList.toggle('open');
        if (backdrop) backdrop.classList.toggle('visible', open);
    },

    hideDrawer() {
        document.getElementById('conv-drawer')?.classList.remove('open');
        document.getElementById('conv-drawer-backdrop')?.classList.remove('visible');
    },

    // ─── Input Handling ────────────────────────────────────────────────────

    initInput() {
        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('chat-send-btn');

        // Remove old listeners by cloning
        const newInput = input.cloneNode(true);
        input.parentNode.replaceChild(newInput, input);
        const newSend = sendBtn.cloneNode(true);
        sendBtn.parentNode.replaceChild(newSend, sendBtn);

        newInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        newSend.addEventListener('click', () => this.sendMessage());
    },

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (!message) return;

        input.value = '';

        // Add user bubble
        this.addBubble('user', message);

        // Show typing indicator
        this.showTyping();

        try {
            const body = { message };
            if (this._currentConversationId) {
                body.conversation_id = this._currentConversationId;
            }

            const result = await App.api(`/users/${App.state.currentUser.id}/chat`, {
                method: 'POST',
                body
            });

            this.hideTyping();
            this.addBubble('assistant', result.response);

            // Track conversation ID (auto-created on first message)
            if (result.conversation_id && !this._currentConversationId) {
                this._currentConversationId = result.conversation_id;
            }

            // Refresh conversation list to show new/updated conversations
            this._conversations = await App.api(
                `/users/${App.state.currentUser.id}/conversations`
            );
            this.renderConversationList();

        } catch (err) {
            this.hideTyping();
            this.addBubble('assistant', `Error: ${err.message}`);
        }
    },

    addBubble(role, content) {
        const container = document.getElementById('chat-messages');

        // Remove welcome message if present
        const welcome = container.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;

        if (role === 'assistant') {
            // Parse markdown for assistant responses
            bubble.innerHTML = this.parseMarkdown(content);
        } else {
            bubble.textContent = content;
        }

        container.appendChild(bubble);
        container.scrollTop = container.scrollHeight;
    },

    /**
     * Lightweight markdown → HTML parser.
     * Handles: headings, bold, italic, lists, numbered lists, line breaks.
     * No external dependencies.
     */
    parseMarkdown(text) {
        if (!text) return '';

        // Escape HTML to prevent XSS
        const escape = s => s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        const escaped = escape(text);
        const lines = escaped.split('\n');
        const output = [];
        let inList = false;
        let inOrderedList = false;

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];

            // Close open list if this line isn't a list item
            const isUnordered = /^\s*[\*\-]\s+/.test(line);
            const isOrdered = /^\s*\d+\.\s+/.test(line);

            if (inList && !isUnordered) {
                output.push('</ul>');
                inList = false;
            }
            if (inOrderedList && !isOrdered) {
                output.push('</ol>');
                inOrderedList = false;
            }

            // Headings (### → h4, ## → h3, etc.)
            if (/^###\s+(.+)/.test(line)) {
                const match = line.match(/^###\s+(.+)/);
                output.push(`<h4 class="chat-heading">${this.inlineFormat(match[1])}</h4>`);
                continue;
            }
            if (/^##\s+(.+)/.test(line)) {
                const match = line.match(/^##\s+(.+)/);
                output.push(`<h3 class="chat-heading">${this.inlineFormat(match[1])}</h3>`);
                continue;
            }

            // Unordered list items
            if (isUnordered) {
                const match = line.match(/^\s*[\*\-]\s+(.+)/);
                if (!inList) {
                    output.push('<ul class="chat-list">');
                    inList = true;
                }
                output.push(`<li>${this.inlineFormat(match[1])}</li>`);
                continue;
            }

            // Ordered list items
            if (isOrdered) {
                const match = line.match(/^\s*\d+\.\s+(.+)/);
                if (!inOrderedList) {
                    output.push('<ol class="chat-list">');
                    inOrderedList = true;
                }
                output.push(`<li>${this.inlineFormat(match[1])}</li>`);
                continue;
            }

            // Empty line → paragraph break
            if (line.trim() === '') {
                output.push('<div class="chat-spacer"></div>');
                continue;
            }

            // Normal paragraph
            output.push(`<p>${this.inlineFormat(line)}</p>`);
        }

        // Close any open lists
        if (inList) output.push('</ul>');
        if (inOrderedList) output.push('</ol>');

        return output.join('');
    },

    /** Format inline markdown: **bold**, *italic*, `code` */
    inlineFormat(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`(.+?)`/g, '<code class="chat-code">$1</code>');
    },

    showTyping() {
        const container = document.getElementById('chat-messages');
        const typing = document.createElement('div');
        typing.className = 'chat-typing';
        typing.id = 'typing-indicator';
        typing.innerHTML = '<span class="typing-dots"><span>.</span><span>.</span><span>.</span></span> Thinking...';
        container.appendChild(typing);
        container.scrollTop = container.scrollHeight;
    },

    hideTyping() {
        document.getElementById('typing-indicator')?.remove();
    },

    // ─── Voice Input (Web Speech API) ──────────────────────────────────────

    initVoice() {
        const btn = document.getElementById('voice-input-btn');
        if (!btn) return;

        // Clone to remove old listeners
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);

        // Check if Speech Recognition is available
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            newBtn.style.display = 'none';
            return;
        }

        newBtn.addEventListener('click', () => {
            if (this.isRecording) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        });
    },

    startRecording() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return;

        this.recognition = new SpeechRecognition();
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.lang = 'en-US';

        this.recognition.onresult = (event) => {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            document.getElementById('chat-input').value = transcript;
        };

        this.recognition.onend = () => {
            this.isRecording = false;
            const btn = document.getElementById('voice-input-btn');
            if (btn) {
                btn.classList.remove('recording');
                btn.textContent = '🎤';
            }
        };

        this.recognition.onerror = (event) => {
            console.error('Speech error:', event.error);
            if (event.error === 'not-allowed') {
                App.toast('Microphone access denied', 'error');
            }
            this.isRecording = false;
        };

        try {
            this.recognition.start();
            this.isRecording = true;
            const btn = document.getElementById('voice-input-btn');
            if (btn) {
                btn.classList.add('recording');
                btn.textContent = '⏹️';
            }
        } catch (err) {
            console.error('Speech start error:', err);
        }
    },

    stopRecording() {
        if (this.recognition) {
            this.recognition.stop();
        }
    },

    // ─── History ───────────────────────────────────────────────────────────

    async loadHistory() {
        try {
            let url = `/users/${App.state.currentUser.id}/chat/history?limit=50`;
            if (this._currentConversationId) {
                url += `&conversation_id=${this._currentConversationId}`;
            }
            const history = await App.api(url);
            const container = document.getElementById('chat-messages');

            if (!history.length) {
                this.showChatWelcome();
                return;
            }

            container.innerHTML = '';
            history.forEach(msg => {
                if (msg.role === 'system') return;
                this.addBubble(msg.role, msg.content);
            });
        } catch (err) {
            console.error('Chat history load failed:', err);
        }
    },

    // ─── Helpers ────────────────────────────────────────────────────────────

    _formatConvTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    },

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },
};
