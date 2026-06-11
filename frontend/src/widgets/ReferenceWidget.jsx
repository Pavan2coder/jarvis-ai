import React from 'react';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const ReferenceWidget = () => {
  return (
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
  );
};

export default ReferenceWidget;
