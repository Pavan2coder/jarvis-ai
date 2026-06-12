import React, { createContext, useState, useEffect, useRef } from 'react';
import * as api from '../services/api';

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

  // Connect to backend WebSocket and poll stats
  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;
    let offline = false;

    const handleStateUpdate = (data) => {
      setUiState(data);
      setLink('LIVE');

      if (offline) {
        addLog('Reconnected to core', 'var(--green)');
        offline = false;
      }

      // Detect status shifts
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
    };

    const connectWs = () => {
      ws = new WebSocket('ws://localhost:5050/ws');

      ws.onopen = () => {
        setLink('LIVE');
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload && payload.event) {
            // Event wrapper schema detected: extract wrapped data object
            if (payload.data) {
              handleStateUpdate(payload.data);
            }
          } else {
            // Raw state object fallback
            handleStateUpdate(payload);
          }
        } catch (e) {
          console.error('WebSocket parse error:', e);
        }
      };

      ws.onclose = () => {
        setLink('DOWN');
        setUiState(prev => ({ ...prev, status: 'idle', response: 'Run  python jarvis.py  to connect.' }));
        if (!offline) {
          addLog('Core offline — start jarvis.py', 'var(--red)');
          offline = true;
        }
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectWs, 2000);
      };

      ws.onerror = (err) => {
        ws.close();
      };
    };

    connectWs();

    const pollStats = async () => {
      const startTime = performance.now();
      try {
        const data = await api.fetchStats();
        setStats(data);
        setPing(Math.round(performance.now() - startTime));
      } catch (e) {
        setPing('--');
      }
    };

    const statsTimer = setInterval(pollStats, 1500);
    pollStats();

    return () => {
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(statsTimer);
    };
  }, []);

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
