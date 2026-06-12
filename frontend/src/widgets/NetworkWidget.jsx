import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const NetworkWidget = () => {
  const { ping, link, stats } = useHud();
  const net = stats?.network || { sent_speed: 0.0, recv_speed: 0.0 };

  return (
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
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>UP (TX)</span>
          <span style={{ color: 'var(--gold)' }}>{net.sent_speed} KB/s</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>DOWN (RX)</span>
          <span style={{ color: 'var(--cyan)' }}>{net.recv_speed} KB/s</span>
        </div>
      </div>
    </GlowCard>
  );
};

export default NetworkWidget;
