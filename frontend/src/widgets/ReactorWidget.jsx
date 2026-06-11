import React from 'react';
import { useHud } from '../hooks/useHud';
import Reactor3D from '../components/Reactor3D';
import DecryptedText from '../components/DecryptedText';

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

const ReactorWidget = () => {
  const { uiState, theme, badgeText, showBadge } = useHud();

  return (
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
  );
};

export default ReactorWidget;
