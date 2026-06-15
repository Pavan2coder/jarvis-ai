// Mock WebSocket global for testing in Node
global.WebSocket = class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0; // CONNECTING
    setTimeout(() => {
      if (this.onerror) this.onerror(new Error('Connection failed'));
      if (this.onclose) this.onclose({ code: 1006, reason: 'Abnormal Close' });
    }, 10);
  }
  close() {
    this.readyState = 3; // CLOSED
  }
};

import { jarvisSocket } from './websocket.js';

console.log('--- Testing Frontend WebSocket Reconnection & Backoff ---');

let statuses = [];
jarvisSocket.onStatusChange((status) => {
  statuses.push(status);
  console.log(`Status changed: ${status}`);
});

// Override config to speed up tests
jarvisSocket.baseReconnectInterval = 100; // 100ms base
jarvisSocket.maxReconnectAttempts = 3;

jarvisSocket.connect();

// Wait for reconnect attempts to trigger and assert
setTimeout(() => {
  console.log(`\nReconnection attempts made: ${jarvisSocket.reconnectAttempts}`);
  console.log('Statuses transitions:', statuses);
  
  const expectedStates = ['CONNECTING', 'DOWN', 'FAILED'];
  const hasExpectedStates = expectedStates.every(s => statuses.includes(s));
  
  if (jarvisSocket.reconnectAttempts === 3 && hasExpectedStates) {
    console.log('\nSUCCESS: Exponential backoff limits and FAILED state triggered correctly!');
    process.exit(0);
  } else {
    console.error('\nFAILURE: Backoff limits or states not triggered correctly.');
    process.exit(1);
  }
}, 3000);
