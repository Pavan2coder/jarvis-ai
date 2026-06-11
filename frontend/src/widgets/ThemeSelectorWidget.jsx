import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const ThemeSelectorWidget = () => {
  const { theme, selectTheme } = useHud();

  return (
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
  );
};

export default ThemeSelectorWidget;
