import React, { useState, useEffect, useRef } from 'react';
import BackgroundField from './components/BackgroundField';
import Reactor3D from './components/Reactor3D';
import GlowCard from './components/GlowCard';
import DecryptedText from './components/DecryptedText';
import Sparkline from './components/Sparkline';
import { Cpu, Server, Radio, Power, Eye, Terminal } from 'lucide-react';

const STATE_LABELS = {
  idle: 'STANDING BY',
  active: 'ACTIVATED',
  listening: 'LISTENING…',
  thinking: 'PROCESSING…',
  speaking: 'RESPONDING'
};

const REACTOR_TEXTS = {
  idle: 'JARVIS',
  active: 'AWAKE',
  listening: 'HEAR',
  thinking: 'THINK',
  speaking: 'SPEAK'
};

const App = () => {
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

  // ════════ Helper to add log lines ════════
  const addLog = (msg, color = 'var(--blue)') => {
    const t = new Date().toLocaleTimeString('en-GB');
    const newLine = { t, msg, color, id: Math.random() };
    setLogLines(prev => {
      const updated = [newLine, ...prev];
      return updated.slice(0, 16); // limit logs
    });
  };

  // ════════ Theme Switcher ════════
  const selectTheme = (themeName) => {
    document.body.className = '';
    if (themeName !== 'cyan') {
      document.body.classList.add('theme-' + themeName);
    }
    setTheme(themeName);
    addLog(`Theme initialized: ${themeName.toUpperCase()}`, 'var(--cyan)');
  };

  // ════════ Boot logs ════════
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

  // ════════ Polling backend ════════
  useEffect(() => {
    let offline = false;
    
    const pollState = async () => {
      const startTime = performance.now();
      try {
        const res = await fetch('http://localhost:5050/state');
        if (!res.ok) throw new Error();
        const data = await res.json();
        
        setUiState(data);
        setPing(Math.round(performance.now() - startTime));
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

      } catch (e) {
        setLink('DOWN');
        setUiState(prev => ({ ...prev, status: 'idle', response: 'Run  python jarvis.py  to connect.' }));
        if (!offline) {
          addLog('Core offline — start jarvis.py', 'var(--red)');
          offline = true;
        }
      }
    };

    const pollStats = async () => {
      try {
        const res = await fetch('http://localhost:5050/stats');
        if (!res.ok) throw new Error();
        const data = await res.json();
        setStats(data);
      } catch (e) {}
    };

    const stateTimer = setInterval(pollState, 350);
    const statsTimer = setInterval(pollStats, 1500);

    pollState();
    pollStats();

    return () => {
      clearInterval(stateTimer);
      clearInterval(statsTimer);
    };
  }, []);

  // ════════ Console input ════════
  const handleTerminalSubmit = async (e) => {
    if (e.key === 'Enter') {
      const text = terminalText.trim();
      if (!text) return;
      setTerminalText('');
      
      addLog(`Terminal CMD: ${text}`, 'var(--gold)');
      setUiState(prev => ({ ...prev, command: text, response: 'Processing command...' }));
      
      try {
        const res = await fetch(`http://localhost:5050/command?text=${encodeURIComponent(text)}`);
        const data = await res.json();
        addLog(`Server: ${data.message}`, 'var(--cyan)');
      } catch (err) {
        addLog('Server unreachable', 'var(--red)');
      }
    }
  };

  const CIRC = 188.5;
  const getDashOffset = (val) => {
    if (val == null) return CIRC;
    return CIRC * (1 - val / 100);
  };

  const getCpuStrokeColor = (pct) => {
    if (pct > 85) return 'var(--red)';
    if (pct > 60) return 'var(--orange)';
    return 'var(--blue)';
  };

  return (
    <div className="hud-container" style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <BackgroundField />
      <div className="grid"></div>
      <div className="vignette"></div>

      <div className="hud">
        {/* TOP BAR */}
        <header className="top">
          <div className="brand">
            <span className="shiny-text">J.A.R.V.I.<b>S</b></span>
          </div>
          <div className="topmeta">
            <span>
              <span className="k">TIME</span>{' '}
              <span className="v" id="clock">
                {new Date().toLocaleTimeString('en-GB')}
              </span>
            </span>
            <span>
              <span className="k">DATE</span>{' '}
              <span className="v" id="date">
                {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' }).toUpperCase()}
              </span>
            </span>
            <span>
              <span className="k">CORE</span> <span className="v" style={{ color: 'var(--green)' }}>ONLINE</span>
            </span>
            <span>
              <span className="k">LINK</span>{' '}
              <span className="v" style={{ color: link === 'LIVE' ? 'var(--green)' : 'var(--red)' }}>
                {link}
              </span>
            </span>
          </div>
        </header>

        {/* LEFT PANEL */}
        <aside className="panel">
          {/* VITALS */}
          <GlowCard>
            <div className="ttl">
              <DecryptedText text="// Vitals" animateOn="hover" />
            </div>
            <div className="gauges">
              <div className="gauge">
                <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
                  <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
                  <circle
                    className="fill"
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    strokeWidth="5"
                    strokeDasharray={CIRC}
                    strokeDashoffset={getDashOffset(stats.cpu)}
                    style={{ stroke: getCpuStrokeColor(stats.cpu) }}
                  />
                  <text className="num" x="36" y="41" textAnchor="middle">
                    {stats.cpu != null ? Math.round(stats.cpu) : '--'}
                  </text>
                </svg>
                <div className="lbl">CPU</div>
                <div className="sub">&nbsp;</div>
                <Sparkline value={stats.cpu} color={getCpuStrokeColor(stats.cpu)} height={20} />
              </div>
              
              <div className="gauge">
                <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
                  <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
                  <circle
                    className="fill"
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    strokeWidth="5"
                    strokeDasharray={CIRC}
                    strokeDashoffset={getDashOffset(stats.ram)}
                    style={{ stroke: 'var(--gold)' }}
                  />
                  <text className="num" x="36" y="41" textAnchor="middle">
                    {stats.ram != null ? Math.round(stats.ram) : '--'}
                  </text>
                </svg>
                <div className="lbl">MEM</div>
                <div className="sub">{stats.ram_used != null ? `${stats.ram_used}/${stats.ram_total}GB` : ' '}</div>
                <Sparkline value={stats.ram} color="var(--gold)" height={20} />
              </div>

              <div className="gauge">
                <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
                  <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
                  <circle
                    className="fill"
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    strokeWidth="5"
                    strokeDasharray={CIRC}
                    strokeDashoffset={getDashOffset(stats.gpu)}
                    style={{ stroke: 'var(--cyan)' }}
                  />
                  <text className="num" x="36" y="41" textAnchor="middle">
                    {stats.gpu != null ? Math.round(stats.gpu) : '--'}
                  </text>
                </svg>
                <div className="lbl">GPU</div>
                <div className="sub">{stats.gpu_mem_used != null ? `${stats.gpu_mem_used}/${stats.gpu_mem_total}MB` : (stats.gpu == null ? 'n/a' : ' ')}</div>
                <Sparkline value={stats.gpu} color="var(--cyan)" height={20} />
              </div>
            </div>
          </GlowCard>

          {/* THEME CONTROLLER */}
          <GlowCard>
            <div className="ttl">
              <DecryptedText text="// HUD Interface Theme" animateOn="hover" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <button onClick={() => selectTheme('cyan')} className={`theme-btn ${theme === 'cyan' ? 'active' : ''}`} id="btn-cyan">CYAN PROT</button>
              <button onClick={() => selectTheme('stark')} className={`theme-btn ${theme === 'stark' ? 'active' : ''}`} id="btn-stark">STARK IND</button>
              <button onClick={() => selectTheme('vibranium')} className={`theme-btn ${theme === 'vibranium' ? 'active' : ''}`} id="btn-vibranium">VIBRANIUM</button>
              <button onClick={() => selectTheme('stealth')} className={`theme-btn ${theme === 'stealth' ? 'active' : ''}`} id="btn-stealth">STEALTH</button>
            </div>
          </GlowCard>

          {/* MODULES */}
          <GlowCard>
            <div className="ttl">
              <DecryptedText text="// Modules" animateOn="hover" />
            </div>
            <div className="mod"><span><span className="dot"></span>SPEECH RECOGNITION</span><span className="on">ON</span></div>
            <div className="mod"><span><span className="dot"></span>TEXT-TO-SPEECH</span><span className="on">ON</span></div>
            <div className="mod"><span><span className="dot"></span>CLAP DETECTION</span><span className="on">ON</span></div>
            <div className="mod"><span><span className="dot"></span>SYSTEM CONTROL</span><span className="on">ON</span></div>
            <div className="mod"><span><span className="dot"></span>GEMINI AI BRAIN</span><span className="on">ON</span></div>
            <div className="mod"><span><span className="dot"></span>BATTERY</span><span className="on">{stats.battery != null ? `${stats.battery}%` : '--'}</span></div>
          </GlowCard>

          {/* ACTIVITY LOG */}
          <GlowCard grow>
            <div className="ttl">
              <DecryptedText text="// Activity Log" animateOn="hover" />
            </div>
            <div id="log">
              {logLines.map(line => (
                <div key={line.id} style={{ color: line.color }}>
                  [{line.t}] {line.msg}
                </div>
              ))}
            </div>
          </GlowCard>
        </aside>

        {/* CENTER PANEL */}
        <main className="center">
          <div className="reactor">
            <Reactor3D theme={theme} status={uiState.status} />
            <div className="rtext" style={{ textShadow: `0 0 18px var(--blue)` }}>
              {REACTOR_TEXTS[uiState.status || 'idle']}
            </div>
          </div>
          <div className={`badge ${showBadge ? 'show' : ''}`}>{badgeText}</div>
          <div className="status">
            <div className="lab">// SYSTEM STATUS</div>
            <div className={`big ${uiState.status || 'idle'}`}>
              <DecryptedText 
                text={STATE_LABELS[uiState.status || 'idle'] || uiState.status.toUpperCase()} 
                animateOn="change" 
                speed={35}
                maxIterations={10}
              />
            </div>
          </div>
          <div className="wave">
            {Array.from({ length: 40 }).map((_, i) => {
              const active = uiState.status === 'listening' || uiState.status === 'speaking';
              const scale = uiState.status === 'listening' ? 1.0 : 0.45;
              const h = active 
                ? (Math.sin(Date.now() / 110 + i * 0.55) * 0.5 + 0.5) * (28 * scale + 8) + 4
                : 4;
              return <i key={i} style={{ height: `${h}px` }} />;
            })}
          </div>
        </main>

        {/* RIGHT PANEL */}
        <aside className="panel">
          {/* CORE CONSOLE */}
          <GlowCard>
            <div className="ttl">
              <DecryptedText text="// Core Console" animateOn="hover" />
            </div>
            <div className="bubble you">
              <span className="tag">YOU SAID</span>
              <span>{uiState.command || '—'}</span>
            </div>
            <div className="bubble jar">
              <span className="tag">JARVIS</span>
              <span style={{ color: '#d6fff0' }}>{uiState.response || 'Awaiting input…'}</span>
            </div>
            <div className="console-input-wrap">
              <span style={{ color: 'var(--blue)', fontWeight: 'bold', marginRight: '8px', fontFamily: 'Share Tech Mono' }}><Terminal size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />&gt;</span>
              <input
                type="text"
                placeholder="Type direct command..."
                value={terminalText}
                onChange={e => setTerminalText(e.target.value)}
                onKeyDown={handleTerminalSubmit}
                autoComplete="off"
              />
            </div>
          </GlowCard>

          {/* COMMAND REFERENCE */}
          <GlowCard grow>
            <div className="ttl">
              <DecryptedText text="// Command Reference" animateOn="hover" />
            </div>
            <div style={{ fontSize: '.78rem', lineHeight: '2.05', opacity: '.85' }}>
              <div>👏👏 / “Jarvis” &nbsp;→&nbsp; <b>Wake</b></div>
              <div>“open youtube cats” &nbsp;→&nbsp; YouTube</div>
              <div>“close youtube” &nbsp;→&nbsp; Close tab</div>
              <div>“open notepad” / “close notepad”</div>
              <div>“cpu / memory / gpu usage”</div>
              <div>“search …”, “play play-name”</div>
              <div>“battery”, “lock pc”, “screenshot”</div>
              <div>“goodbye” &nbsp;→&nbsp; Shut down</div>
            </div>
          </GlowCard>

          {/* NETWORK */}
          <GlowCard>
            <div className="ttl">
              <DecryptedText text="// Network" animateOn="hover" />
            </div>
            <div style={{ fontSize: '.78rem', lineHeight: '1.95' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>UPLINK</span>
                <span className="on" style={{ color: 'var(--green)' }}>SECURE</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>MODE</span>
                <span style={{ color: 'var(--blue)' }}>LOCAL · 5050</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>LATENCY</span>
                <span style={{ color: '#fff' }}>{ping} ms</span>
              </div>
            </div>
          </GlowCard>
        </aside>

        {/* BOTTOM TICKER */}
        <footer className="bottom">
          <div className="tick">
            J.A.R.V.I.S v3.5 — POWERED BY REACT & THREE.JS • WEBGL 3D CORE SYSTEM OPERATIONAL • STARK PROTOCOLS ACTIVE • ALL SYSTEMS NOMINAL •
          </div>
        </footer>
      </div>
    </div>
  );
};

export default App;
