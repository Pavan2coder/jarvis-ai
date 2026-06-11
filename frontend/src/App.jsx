import React from 'react';
import { HudProvider } from './store/HudContext';
import { useHud } from './hooks/useHud';
import BackgroundField from './components/BackgroundField';
import VitalsWidget from './widgets/VitalsWidget';
import ThemeSelectorWidget from './widgets/ThemeSelectorWidget';
import ModulesWidget from './widgets/ModulesWidget';
import LogWidget from './widgets/LogWidget';
import ConsoleWidget from './widgets/ConsoleWidget';
import ReferenceWidget from './widgets/ReferenceWidget';
import NetworkWidget from './widgets/NetworkWidget';
import ReactorWidget from './widgets/ReactorWidget';

const HudLayout = () => {
  const { link } = useHud();

  return (
    <div className="hud-container" style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <BackgroundField />
      <div className="grid"></div>
      <div className="vignette"></div>

      {/* Decorative Sci-Fi Corner Borders */}
      <div className="cn tl"></div>
      <div className="cn tr"></div>
      <div className="cn bl"></div>
      <div className="cn br"></div>

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
          <VitalsWidget />
          <ThemeSelectorWidget />
          <ModulesWidget />
          <LogWidget />
        </aside>

        {/* CENTER PANEL */}
        <ReactorWidget />

        {/* RIGHT PANEL */}
        <aside className="panel">
          <ConsoleWidget />
          <ReferenceWidget />
          <NetworkWidget />
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

const App = () => {
  return (
    <HudProvider>
      <HudLayout />
    </HudProvider>
  );
};

export default App;
