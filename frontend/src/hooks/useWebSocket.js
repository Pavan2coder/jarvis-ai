import { useEffect, useState, useCallback } from 'react';
import { jarvisSocket } from '../services/websocket';

export const useWebSocket = (onMessageReceived) => {
  const [connectionStatus, setConnectionStatus] = useState('DOWN');

  useEffect(() => {
    // Synchronize connection status shifts
    jarvisSocket.onStatusChange((status) => {
      setConnectionStatus(status);
    });

    // Register active packet callback listener
    const unsubscribe = jarvisSocket.subscribe((message) => {
      if (onMessageReceived) {
        onMessageReceived(message);
      }
    });

    // Establish link with uvicorn server
    jarvisSocket.connect();

    return () => {
      unsubscribe();
    };
  }, [onMessageReceived]);

  const sendMessage = useCallback((event, data = {}) => {
    jarvisSocket.send(event, data);
  }, []);

  return {
    connectionStatus,
    sendMessage,
  };
};
