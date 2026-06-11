import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';
import { Terminal } from 'lucide-react';

const ConsoleWidget = () => {
  const { uiState, terminalText, setTerminalText, triggerTerminalSubmit } = useHud();

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      const text = terminalText.trim();
      if (!text) return;
      setTerminalText('');
      triggerTerminalSubmit(text);
    }
  };

  return (
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
        <span style={{ color: 'var(--blue)', fontWeight: 'bold', marginRight: '8px', fontFamily: 'Share Tech Mono' }}>
          <Terminal size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
          &gt;
        </span>
        <input
          type="text"
          placeholder="Type direct command..."
          value={terminalText}
          onChange={e => setTerminalText(e.target.value)}
          onKeyDown={handleKeyDown}
          autoComplete="off"
        />
      </div>
    </GlowCard>
  );
};

export default ConsoleWidget;
