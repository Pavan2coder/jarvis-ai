class WebSocketService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.reconnectInterval = 2000;
    this.url = 'ws://localhost:5050/ws';
    this.shouldReconnect = true;
    this.reconnectTimer = null;
    this.onStatusChangeCallback = null;
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.shouldReconnect = true;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('Connected to Jarvis OS WebSocket core.');
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback('LIVE');
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.listeners.forEach((listener) => listener(payload));
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    this.ws.onclose = () => {
      console.warn('Jarvis OS WebSocket connection closed.');
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback('DOWN');
      }
      
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket connection error:', err);
      this.ws.close();
    };
  }

  scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      console.log('Attempting to reconnect to Jarvis OS WebSocket core...');
      this.connect();
    }, this.reconnectInterval);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
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

  send(event, data = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    } else {
      console.warn('Cannot send message, WebSocket is not open.');
    }
  }
}

export const jarvisSocket = new WebSocketService();
