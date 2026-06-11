import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const ModulesWidget = () => {
  const { stats } = useHud();

  return (
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
  );
};

export default ModulesWidget;
