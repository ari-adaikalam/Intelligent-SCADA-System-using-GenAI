// ============================================================================
// SWAT AI CHATBOT - CHAT INTERFACE LOGIC
// ============================================================================
// Location: D:\FYP - FINAL\SwatDashboard\wwwroot\js\chat.js
// Dependencies: Chart.js (loaded via CDN or local)
// ============================================================================

class SwatChatInterface {
    constructor() {
        // Session ID (persists during page session)
        this.sessionId = this.generateSessionId();

        // Message history (in-memory for current session)
        this.messageHistory = [];

        // Chart instances (for cleanup)
        this.chartInstances = {};

        // Processing state
        this.isProcessing = false;

        // DOM elements (initialized in init())
        this.elements = {};

        // Configuration
        this.config = {
            apiBaseUrl: '/api/chat',
            maxMessageLength: 2000,
            typingIndicatorDelay: 500,
            autoScrollDelay: 100
        };
    }

    // ========================================================================
    // INITIALIZATION
    // ========================================================================

    init() {
        console.log('🤖 Initializing SWAT Chat Interface...');

        // Get DOM elements
        this.elements = {
            container: document.getElementById('chat-container'),
            messagesArea: document.getElementById('chat-messages'),
            inputField: document.getElementById('chat-input'),
            sendButton: document.getElementById('chat-send-btn'),
            clearButton: document.getElementById('chat-clear-btn'),
            statusDot: document.getElementById('chat-status-dot'),
            statusText: document.getElementById('chat-status-text'),
            typingIndicator: document.getElementById('chat-typing-indicator'),
            emptyState: document.getElementById('chat-empty-state')
        };

        // Verify required elements
        if (!this.elements.messagesArea || !this.elements.inputField) {
            console.error('❌ Required chat elements not found in DOM');
            return;
        }

        // Bind event listeners
        this.bindEvents();

        // Check API health
        this.checkApiHealth();

        // Load suggestion chips
        this.loadSuggestions();

        console.log('✅ Chat interface initialized', { sessionId: this.sessionId });
    }

    bindEvents() {
        // Send button click
        this.elements.sendButton?.addEventListener('click', () => this.sendMessage());

        // Enter key to send (Shift+Enter for new line)
        this.elements.inputField?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Clear button
        this.elements.clearButton?.addEventListener('click', () => this.clearChat());

        // Input character count
        this.elements.inputField?.addEventListener('input', (e) => {
            this.updateCharCount(e.target.value.length);
        });

        // Auto-resize textarea
        this.elements.inputField?.addEventListener('input', (e) => {
            this.autoResizeTextarea(e.target);
        });
    }

    // ========================================================================
    // MESSAGE SENDING
    // ========================================================================

    async sendMessage() {
        const messageText = this.elements.inputField.value.trim();

        // Validation
        if (!messageText) return;
        if (this.isProcessing) return;
        if (messageText.length > this.config.maxMessageLength) {
            this.showError(`Message too long (max ${this.config.maxMessageLength} characters)`);
            return;
        }

        // Set processing state
        this.isProcessing = true;
        this.elements.sendButton.disabled = true;
        this.elements.inputField.disabled = true;

        // Clear input
        this.elements.inputField.value = '';
        this.updateCharCount(0);

        // Hide empty state
        if (this.elements.emptyState) {
            this.elements.emptyState.classList.add('hidden');
        }

        // Add user message to UI
        this.addMessageToUI('user', messageText);

        // Show typing indicator
        this.showTypingIndicator();

        try {
            // Call backend API
            const response = await this.callChatApi(messageText);

            // Hide typing indicator
            this.hideTypingIndicator();

            // Add bot response to UI
            this.addBotResponse(response);

            // Store in history
            this.messageHistory.push({
                user: messageText,
                bot: response.text,
                timestamp: new Date().toISOString()
            });

        } catch (error) {
            console.error('❌ Chat error:', error);
            this.hideTypingIndicator();
            this.addMessageToUI('bot', '❌ Sorry, I encountered an error processing your request. Please try again.');
            this.showError(error.message);
        } finally {
            // Reset processing state
            this.isProcessing = false;
            this.elements.sendButton.disabled = false;
            this.elements.inputField.disabled = false;
            this.elements.inputField.focus();
        }
    }

    async callChatApi(message) {
        const payload = {
            sessionId: this.sessionId,
            message: message,
            includeRealtime: this.shouldIncludeRealtime(message)
        };

        const response = await fetch(`${this.config.apiBaseUrl}/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status} ${response.statusText}`);
        }

        return await response.json();
    }

    shouldIncludeRealtime(message) {
        // Keywords that suggest user wants real-time data
        const realtimeKeywords = [
            'current', 'now', 'real-time', 'latest', 'today',
            'what is', 'status', 'anomaly', 'warning', 'alert'
        ];

        const messageLower = message.toLowerCase();
        return realtimeKeywords.some(keyword => messageLower.includes(keyword));
    }

    // ========================================================================
    // UI RENDERING
    // ========================================================================

    addMessageToUI(role, text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'chat-message-avatar';
        avatar.textContent = role === 'user' ? '👤' : '🤖';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'chat-message-content';

        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'chat-message-bubble';
        bubbleDiv.textContent = text;

        const timestamp = document.createElement('div');
        timestamp.className = 'chat-message-timestamp';
        timestamp.textContent = this.formatTime(new Date());

        contentDiv.appendChild(bubbleDiv);
        contentDiv.appendChild(timestamp);

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        this.elements.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addBotResponse(response) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot';

        const avatar = document.createElement('div');
        avatar.className = 'chat-message-avatar';
        avatar.textContent = '🤖';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'chat-message-content';

        // Text bubble
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'chat-message-bubble';
        bubbleDiv.innerHTML = this.formatBotText(response.text);

        contentDiv.appendChild(bubbleDiv);

        // ML Insights badge (if present)
        if (response.mlInsights) {
            const insightsBadge = this.createMlInsightsBadge(response.mlInsights);
            contentDiv.appendChild(insightsBadge);
        }

        // Chart (if present)
        if (response.chartConfig) {
            const chartContainer = this.createChartContainer(response.chartConfig);
            contentDiv.appendChild(chartContainer);
        }

        // Download buttons (if present)
        if (response.downloadLinks) {
            const downloadButtons = this.createDownloadButtons(response.downloadLinks);
            contentDiv.appendChild(downloadButtons);
        }

        // Timestamp
        const timestamp = document.createElement('div');
        timestamp.className = 'chat-message-timestamp';
        timestamp.textContent = this.formatTime(new Date());
        contentDiv.appendChild(timestamp);

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        this.elements.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }

    createMlInsightsBadge(insights) {
        const badge = document.createElement('div');

        let statusClass = 'normal';
        let icon = '✅';

        if (insights.state === 'WARNING' || insights.state === 'DEGRADING') {
            statusClass = 'warning';
            icon = '⚠️';
        } else if (insights.state === 'CRITICAL' || insights.state === 'FAULTED') {
            statusClass = 'critical';
            icon = '🚨';
        }

        badge.className = `chat-ml-insights ${statusClass}`;
        badge.innerHTML = `
            <span>${icon}</span>
            <span><strong>ML Analysis:</strong> ${insights.state}</span>
            ${insights.faultyComponent ? `<span>• ${insights.faultyComponent}</span>` : ''}
            <span>(${Math.round(insights.confidence * 100)}% confidence)</span>
        `;

        return badge;
    }

    createChartContainer(chartConfig) {
        const container = document.createElement('div');
        container.className = 'chat-chart-container';

        const canvas = document.createElement('canvas');
        const chartId = `chart-${Date.now()}`;
        canvas.id = chartId;

        container.appendChild(canvas);

        // Render chart after DOM insertion
        setTimeout(() => {
            this.renderChart(chartId, chartConfig);
        }, 100);

        return container;
    }

    renderChart(canvasId, config) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error('Canvas not found:', canvasId);
            return;
        }

        // Destroy existing chart if exists
        if (this.chartInstances[canvasId]) {
            this.chartInstances[canvasId].destroy();
        }

        // Create new chart
        try {
            this.chartInstances[canvasId] = new Chart(canvas, config);
        } catch (error) {
            console.error('Chart render error:', error);
            canvas.parentElement.innerHTML = '<p style="color: var(--color-critical);">❌ Error rendering chart</p>';
        }
    }

    createDownloadButtons(links) {
        const container = document.createElement('div');
        container.className = 'chat-download-buttons';

        if (links.pdf) {
            const pdfBtn = document.createElement('a');
            pdfBtn.href = links.pdf;
            pdfBtn.className = 'chat-download-btn';
            pdfBtn.download = true;
            pdfBtn.innerHTML = '📄 Download PDF';
            container.appendChild(pdfBtn);
        }

        if (links.excel) {
            const excelBtn = document.createElement('a');
            excelBtn.href = links.excel;
            excelBtn.className = 'chat-download-btn';
            excelBtn.download = true;
            excelBtn.innerHTML = '📊 Download Excel';
            container.appendChild(excelBtn);
        }

        return container;
    }

    // ========================================================================
    // TYPING INDICATOR
    // ========================================================================

    showTypingIndicator() {
        if (!this.elements.typingIndicator) return;

        setTimeout(() => {
            // Remove from current position and append to messages container
            // This ensures it appears at the bottom
            if (this.elements.typingIndicator.parentElement !== this.elements.messagesContainer) {
                this.elements.messagesContainer.appendChild(this.elements.typingIndicator);
            }
            this.elements.typingIndicator.classList.remove('hidden');
            this.scrollToBottom();
        }, this.config.typingIndicatorDelay);
    }

    hideTypingIndicator() {
        if (!this.elements.typingIndicator) return;
        this.elements.typingIndicator.classList.add('hidden');
    }

    // ========================================================================
    // SUGGESTIONS
    // ========================================================================

    loadSuggestions() {
        const suggestions = [
            "Is there any anomaly now?",
            "Show me the pressure PIT501 value now?",
            "Show me the P302 vibration and current (last 6 hours)",
            "Generate a daily report for today",
            "Compare FIT101 and FIT201 for the last 1 hour"
        ];

        const emptyState = this.elements.emptyState;
        if (!emptyState) return;

        const suggestionsContainer = emptyState.querySelector('.chat-empty-state-suggestions');
        if (!suggestionsContainer) return;

        suggestionsContainer.innerHTML = '';

        suggestions.forEach(text => {
            const chip = document.createElement('div');
            chip.className = 'chat-suggestion-chip';
            chip.textContent = text;
            chip.addEventListener('click', () => {
                this.elements.inputField.value = text;
                this.elements.inputField.focus();
            });
            suggestionsContainer.appendChild(chip);
        });
    }

    // ========================================================================
    // UTILITIES
    // ========================================================================

    formatBotText(text) {
        // Simple markdown-like formatting
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold
            .replace(/\*(.*?)\*/g, '<em>$1</em>') // Italic
            .replace(/`(.*?)`/g, '<code>$1</code>') // Inline code
            .replace(/\n/g, '<br>'); // Line breaks

        return formatted;
    }

    formatTime(date) {
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    scrollToBottom() {
        setTimeout(() => {
            this.elements.messagesArea.scrollTop = this.elements.messagesArea.scrollHeight;
        }, this.config.autoScrollDelay);
    }

    autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    updateCharCount(count) {
        const charCountEl = document.getElementById('chat-char-count');
        if (charCountEl) {
            charCountEl.textContent = `${count}/${this.config.maxMessageLength}`;

            if (count > this.config.maxMessageLength * 0.9) {
                charCountEl.style.color = 'var(--color-warning)';
            } else {
                charCountEl.style.color = 'var(--color-text-secondary)';
            }
        }
    }

    generateSessionId() {
        return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    // ========================================================================
    // CHAT MANAGEMENT
    // ========================================================================

    async clearChat() {
        if (!confirm('Clear all messages? This cannot be undone.')) {
            return;
        }

        // Clear UI
        this.elements.messagesArea.innerHTML = '';

        // Show empty state
        if (this.elements.emptyState) {
            this.elements.emptyState.classList.remove('hidden');
        }

        // Clear history
        this.messageHistory = [];

        // Destroy all charts
        Object.values(this.chartInstances).forEach(chart => chart.destroy());
        this.chartInstances = {};

        // Clear backend session
        try {
            await fetch(`${this.config.apiBaseUrl}/clear`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: this.sessionId })
            });
        } catch (error) {
            console.error('Failed to clear backend session:', error);
        }

        // Generate new session ID
        this.sessionId = this.generateSessionId();

        console.log('✅ Chat cleared');
    }

    async checkApiHealth() {
        try {
            const response = await fetch(`${this.config.apiBaseUrl}/status`);
            const data = await response.json();

            if (data.status === 'ok') {
                this.updateStatus('online', 'AI Ready');
            } else {
                this.updateStatus('offline', 'AI Unavailable');
            }
        } catch (error) {
            console.warn('API health check failed:', error);
            this.updateStatus('offline', 'Connecting...');
        }
    }

    updateStatus(status, text) {
        if (this.elements.statusDot) {
            this.elements.statusDot.className = status === 'online'
                ? 'chat-status-dot'
                : 'chat-status-dot offline';
        }

        if (this.elements.statusText) {
            this.elements.statusText.textContent = text;
        }
    }

    showError(message) {
        // Create error notification (could use toast library)
        console.error('Chat error:', message);

        // Simple inline error (you can enhance this)
        const errorDiv = document.createElement('div');
        errorDiv.className = 'chat-error-message';
        errorDiv.innerHTML = `⚠️ ${message}`;

        this.elements.messagesArea.appendChild(errorDiv);

        setTimeout(() => {
            errorDiv.remove();
        }, 5000);
    }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChat);
} else {
    initChat();
}

function initChat() {
    // Only initialize if chat container exists (i.e., we're on chat tab)
    if (document.getElementById('chat-container')) {
        window.swatChat = new SwatChatInterface();
        window.swatChat.init();
    }
}

// ============================================================================
// EXPORT FOR MODULE USAGE (if needed)
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SwatChatInterface;
}