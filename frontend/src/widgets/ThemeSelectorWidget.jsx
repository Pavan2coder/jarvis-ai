import React from 'react';
import { useHud } from '../hooks/useHud';

const THEMES = [['cyan', 'CYAN'], ['stark', 'STARK'], ['vibranium', 'VIBRANIUM'], ['stealth', 'STEALTH']];

// Compact inline theme switcher for the top bar.
const ThemeSelectorWidget = () => {
  const { theme, selectTheme } = useHud();

  return (
    <div className="theme-bar">
      {THEMES.map(([id, label]) => (
        <button key={id} id={`btn-${id}`} onClick={() => selectTheme(id)} className={`theme-btn ${theme === id ? 'active' : ''}`}>
          {label}
        </button>
      ))}
    </div>
  );
};

export default ThemeSelectorWidget;
