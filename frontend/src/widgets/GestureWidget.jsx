import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';

const GestureWidget = () => {
  const { gestureState } = useHud();
  const { active, gesture, action, camera } = gestureState || {
    active: false,
    gesture: 'None',
    action: 'None',
    camera: 'Inactive'
  };

  // Maps gesture symbols for rich visual look
  const getGestureIcon = (g) => {
    switch (g) {
      case 'Fist': return '✊';
      case 'Thumbs Up': return '👍';
      case 'Peace Sign': return '✌️';
      case 'Open Palm': return '🖐️';
      case 'Middle Pinch': return '🤏';
      case 'Index Point': return '☝️';
      default: return '🖐️';
    }
  };

  const getCameraColor = (status) => {
    if (status === 'Active') return 'var(--green)';
    if (status === 'Error') return 'var(--red)';
    return 'rgba(255,255,255,0.4)';
  };

  return (
    <GlowCard>
      <div className="ttl">
        <DecryptedText text="// Gesture Control" animateOn="hover" />
      </div>
      
      <div className="mod" style={{ marginBottom: '8px' }}>
        <span>CAMERA FEED</span>
        <span style={{ color: getCameraColor(camera), fontWeight: 'bold' }}>
          {camera.toUpperCase()}
        </span>
      </div>

      <div className="mod" style={{ marginBottom: '8px' }}>
        <span>ENGINE STATUS</span>
        <span style={{ color: active ? 'var(--green)' : 'var(--red)', fontWeight: 'bold' }}>
          {active ? 'ACTIVE' : 'OFFLINE'}
        </span>
      </div>

      {active && (
        <>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            padding: '12px 0',
            borderTop: '1px dashed var(--line)',
            borderBottom: '1px dashed var(--line)',
            margin: '8px 0',
            background: 'rgba(var(--glow-rgb), 0.02)'
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ 
                fontSize: '2rem', 
                transform: gesture !== 'None' ? 'scale(1.15)' : 'scale(1.0)',
                transition: 'transform 0.2s ease-in-out'
              }}>
                {getGestureIcon(gesture)}
              </div>
              <div style={{ fontSize: '0.8rem', letterSpacing: '1px', opacity: 0.9, marginTop: '4px', fontFamily: 'Orbitron', fontWeight: 600 }}>
                {gesture.toUpperCase()}
              </div>
            </div>
          </div>

          <div className="mod">
            <span>ACTION</span>
            <span style={{ color: action !== 'None' ? 'var(--cyan)' : 'var(--txt)', fontWeight: '500' }}>
              {action}
            </span>
          </div>
        </>
      )}
    </GlowCard>
  );
};

export default GestureWidget;
