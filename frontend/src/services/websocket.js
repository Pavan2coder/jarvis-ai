class WebSocketService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    
    // Configuration
    this.url = 'ws://localhost:5050/ws';
    this.baseReconnectInterval = 1000; // 1 second
    this.maxReconnectInterval = 30000; // 30 seconds
    this.maxReconnectAttempts = 10;
    
    // State variables
    this.reconnectAttempts = 0;
    this.shouldReconnect = true;
    this.reconnectTimer = null;
    this.onStatusChangeCallback = null;
    
    // Heartbeat watchdog (client activity monitored, server pings received)
    this.pongTimeout = 15000; // 15 seconds (expects ping/pong activity from client-side loop)
    this.watchdogTimer = null;
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.shouldReconnect = true;
    this.updateStatus('CONNECTING');
    
    console.log(`Connecting to Jarvis OS WebSocket core at ${this.url}...`);
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('Connected to Jarvis OS WebSocket core.');
      this.reconnectAttempts = 0;
      this.updateStatus('LIVE');
      this.resetWatchdog();
    };

    this.ws.onmessage = (event) => {
      // Feed/reset the watchdog on any message from the server
      this.resetWatchdog();
      
      try {
        const payload = JSON.parse(event.data);
        if (payload && payload.event === 'pong') {
          return;
        }
        this.listeners.forEach((listener) => listener(payload));
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    this.ws.onclose = (event) => {
      console.warn(`Jarvis OS WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason}`);
      this.stopWatchdog();
      
      if (this.shouldReconnect) {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.updateStatus('DOWN');
          this.scheduleReconnect();
        } else {
          console.error(`Maximum WebSocket reconnection attempts (${this.maxReconnectAttempts}) exceeded.`);
          this.updateStatus('FAILED');
        }
      } else {
        this.updateStatus('DOWN');
      }
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket connection error:', err);
      this.ws.close();
    };
  }

  resetWatchdog() {
    if (this.watchdogTimer) clearTimeout(this.watchdogTimer);
    
    // If we don't receive any message/pong for pongTimeout, consider connection dead
    this.watchdogTimer = setTimeout(() => {
      console.warn('Watchdog timeout: no server heartbeat detected. Terminating connection...');
      if (this.ws) {
        this.ws.close();
      }
    }, this.pongTimeout);
  }

  stopWatchdog() {
    if (this.watchdogTimer) {
      clearTimeout(this.watchdogTimer);
      this.watchdogTimer = null;
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    
    this.reconnectAttempts++;
    
    // Exponential backoff
    const delay = Math.min(
      this.baseReconnectInterval * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectInterval
    );
    
    // Add random jitter (0 to 1000ms)
    const jitter = Math.random() * 1000;
    const totalDelay = delay + jitter;
    
    console.log(
      `Reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} ` +
      `scheduled in ${Math.round(totalDelay)}ms (backoff: ${Math.round(delay)}ms, jitter: ${Math.round(jitter)}ms)`
    );
    
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, totalDelay);
  }

  disconnect() {
    this.shouldReconnect = false;
    this.reconnectAttempts = 0;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.stopWatchdog();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  onStatusChange(callback) {
    this.onStatusChangeCallback = callback;
  }

  updateStatus(status) {
    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback(status);
    }
  }

  send(event, data = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    } else {
      console.warn('Cannot send message, WebSocket is not open.');
    }
  }

  manualRetry() {
    console.log('User triggered manual reconnection retry.');
    this.reconnectAttempts = 0;
    this.connect();
  }
}

export const jarvisSocket = new WebSocketService();
