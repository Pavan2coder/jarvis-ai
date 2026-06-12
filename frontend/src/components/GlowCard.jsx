import React, { useState, useRef } from 'react';

const GlowCard = ({ children, className = '', title = '', grow = false, style = {} }) => {
  const cardRef = useRef(null);
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);
  const [rotate, setRotate] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    
    // Position of cursor within card
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setCoords({ x, y });

    // Rotate calculate (3D tilt)
    const midX = rect.width / 2;
    const midY = rect.height / 2;
    const rotateX = -(y - midY) / (rect.height / 8); // subtle tilt
    const rotateY = (x - midX) / (rect.width / 8);
    setRotate({ x: rotateX, y: rotateY });
  };

  const handleMouseEnter = () => {
    setHovered(true);
  };

  const handleMouseLeave = () => {
    setHovered(false);
    setRotate({ x: 0, y: 0 });
  };

  const combinedStyle = {
    transform: hovered 
      ? `perspective(800px) rotateX(${rotate.x}deg) rotateY(${rotate.y}deg) scale3d(1.02, 1.02, 1.02)` 
      : 'perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)',
    transition: hovered ? 'transform 0.05s ease-out' : 'transform 0.5s ease-out',
    position: 'relative',
    ...style
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`card ${grow ? 'grow' : ''} ${className}`}
      style={combinedStyle}
    >
      {/* Radial Hover Glow Overlay */}
      {hovered && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            background: `radial-gradient(circle 160px at ${coords.x}px ${coords.y}px, rgba(var(--glow-rgb), 0.12), transparent 70%)`,
            zIndex: 1,
            mixBlendMode: 'screen',
          }}
        />
      )}
      
      {/* Glowing border outline overlay (following mouse) */}
      {hovered && (
        <div
          style={{
            position: 'absolute',
            inset: -1,
            pointerEvents: 'none',
            border: '1px solid transparent',
            backgroundImage: `radial-gradient(circle 100px at ${coords.x}px ${coords.y}px, var(--blue), transparent 60%)`,
            WebkitMask: 'linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0)',
            WebkitMaskComposite: 'xor',
            maskComposite: 'exclude',
            zIndex: 2,
            opacity: 0.85,
            clipPath: 'polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px))',
          }}
        />
      )}

      {/* Card Header Title */}
      {title && (
        <div className="ttl">
          {title}
        </div>
      )}

      <div className={grow ? 'grow' : ''} style={{ position: 'relative', zIndex: 3 }}>
        {children}
      </div>
      
      <div className="card-corner-line" />
    </div>
  );
};

export default GlowCard;
