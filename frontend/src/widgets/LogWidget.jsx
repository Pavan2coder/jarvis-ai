import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const LogWidget = () => {
  const { logLines } = useHud();

  return (
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
  );
};

export default LogWidget;
