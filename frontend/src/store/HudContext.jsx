import React, { createContext, useState, useEffect, useRef, useCallback } from 'react';
import * as api from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

export const HudContext = createContext(null);

export const HudProvider = ({ children }) => {
  const [uiState, setUiState] = useState({
    status: 'idle',
    message: 'Standing by...',
    wake_source: '',
    command: '',
    response: ''
  });
  
  const [stats, setStats] = useState({
    cpu: null,
    ram: null,
    ram_used: null,
    ram_total: null,
    battery: null,
    gpu: null,
    gpu_mem_used: null,
    gpu_mem_total: null
  });

  const [theme, setTheme] = useState('cyan');
  const [ping, setPing] = useState('--');
  const [link, setLink] = useState('OFFLINE');
  const [logLines, setLogLines] = useState([]);
  const [badgeText, setBadgeText] = useState('');
  const [showBadge, setShowBadge] = useState(false);
  const [terminalText, setTerminalText] = useState('');

  const lastStatusRef = useRef('');
  const lastCmdRef = useRef('');
  const lastResRef = useRef('');

  // Helper to add log lines
  const addLog = (msg, color = 'var(--blue)') => {
    const t = new Date().toLocaleTimeString('en-GB');
    const newLine = { t, msg, color, id: Math.random() };
    setLogLines(prev => {
      const updated = [newLine, ...prev];
      return updated.slice(0, 16); // limit logs
    });
  };

  // Theme Switcher
  const selectTheme = (themeName) => {
    document.body.className = '';
    if (themeName !== 'cyan') {
      document.body.classList.add('theme-' + themeName);
    }
    setTheme(themeName);
    addLog(`Theme initialized: ${themeName.toUpperCase()}`, 'var(--cyan)');
  };

  // Boot logs
  useEffect(() => {
    selectTheme('cyan');
    const bootMsgs = [
      'Core online — compiled in React',
      'Clap detector armed & ready',
      'Wake-word listener calibrated',
      'Awaiting directive'
    ];
    bootMsgs.forEach((msg, i) => {
      setTimeout(() => addLog(msg, i === 0 ? 'var(--green)' : 'var(--blue)'), i * 300);
    });
  }, []);

  const offlineRef = useRef(false);
  const lastPingTimeRef = useRef(0);

  // Handle incoming websocket messages
  const handleMessage = useCallback((payload) => {
    if (!payload) return;
    
    // Check if it's wrapped in our Event system payload
    if (payload.event) {
      if (payload.event === 'COMMAND_EXECUTED') {
        addLog(`CMD Executed: ${payload.data.command || ''}`, 'var(--green)');
      } else if (payload.event === 'VOICE_DETECTED') {
        addLog(`Voice detected (intensity: ${payload.data.intensity || ''})`, 'var(--cyan)');
      } else if (payload.event === 'DIAGNOSTICS_UPDATE') {
        setStats(payload.data);
        return;
      } else if (payload.event === 'pong') {
        const latency = Math.round(performance.now() - lastPingTimeRef.current);
        setPing(latency);
        return;
      }
      
      // For general wrapped events, extract state payload if applicable
      if (payload.data && payload.event === 'SYSTEM_UPDATE') {
        setUiState(payload.data);
      }
    } else {
      // Raw state object fallback
      setUiState(payload);
    }

    if (offlineRef.current) {
      addLog('Reconnected to core', 'var(--green)');
      offlineRef.current = false;
    }

    // Detect status shifts if the state updates
    const data = payload.event === 'SYSTEM_UPDATE' ? payload.data : (!payload.event ? payload : null);
    if (!data) return;

    const st = data.status || 'idle';
    if (st !== lastStatusRef.current) {
      if (st === 'active') {
        const src = data.wake_source === 'clap' ? '👏 CLAP' : (data.wake_source === 'manual' ? '⌨ MANUAL' : '🎙 VOICE');
        setBadgeText(`── ${src} ACTIVATED ──`);
        setShowBadge(true);
        setTimeout(() => setShowBadge(false), 2800);
        addLog(`Activated via ${data.wake_source || 'voice'}`, 'var(--green)');
      } else if (st === 'listening') {
        addLog('Listening for command…', 'var(--gold)');
      }
      lastStatusRef.current = st;
    }

    // Detect commands
    if (data.command && data.command !== lastCmdRef.current) {
      addLog(`CMD: ${data.command}`, 'var(--gold)');
      lastCmdRef.current = data.command;
    }

    // Detect responses
    if (data.response && data.response !== lastResRef.current) {
      addLog(`RSP: ${data.response.slice(0, 36)}...`, 'var(--green)');
      lastResRef.current = data.response;
    }
  }, []);

  // Initialize WebSocket connection hook
  const { connectionStatus, sendMessage } = useWebSocket(handleMessage);

  // Synchronize WebSocket status with HudContext state
  useEffect(() => {
    setLink(connectionStatus);
    if (connectionStatus === 'DOWN') {
      setUiState(prev => ({ ...prev, status: 'idle', response: 'Run  python jarvis.py  to connect.' }));
      setPing('--');
      if (!offlineRef.current) {
        addLog('Core offline — start jarvis.py', 'var(--red)');
        offlineRef.current = true;
      }
    }
  }, [connectionStatus]);

  // Ping heartbeat timer
  useEffect(() => {
    if (connectionStatus !== 'LIVE') return;

    const sendPing = () => {
      lastPingTimeRef.current = performance.now();
      sendMessage('ping');
    };

    const pingTimer = setInterval(sendPing, 3000);
    sendPing(); // Initial trigger

    return () => {
      clearInterval(pingTimer);
    };
  }, [connectionStatus, sendMessage]);

  const triggerTerminalSubmit = async (text) => {
    addLog(`Terminal CMD: ${text}`, 'var(--gold)');
    setUiState(prev => ({ ...prev, command: text, response: 'Processing command...' }));
    
    try {
      const data = await api.sendTerminalCommand(text);
      addLog(`Server: ${data.message}`, 'var(--cyan)');
    } catch (err) {
      addLog('Server unreachable', 'var(--red)');
    }
  };

  return (
    <HudContext.Provider value={{
      uiState,
      stats,
      theme,
      ping,
      link,
      logLines,
      badgeText,
      showBadge,
      terminalText,
      setTerminalText,
      selectTheme,
      addLog,
      triggerTerminalSubmit
    }}>
      {children}
    </HudContext.Provider>
  );
};
