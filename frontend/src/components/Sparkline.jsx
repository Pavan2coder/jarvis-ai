import React, { useState, useEffect } from 'react';

const Sparkline = ({ value, color = 'var(--blue)', maxPoints = 20, height = 30 }) => {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    if (value === null || value === undefined) return;
    setHistory(prev => {
      const next = [...prev, value];
      if (next.length > maxPoints) {
        next.shift();
      }
      return next;
    });
  }, [value, maxPoints]);

  if (history.length < 2) {
    return <div style={{ height: `${height}px` }} />;
  }

  const width = 100; // viewbox units
  const minVal = 0;
  const maxVal = 100;
  
  const points = history.map((val, i) => {
    const x = (i / (history.length - 1)) * width;
    // Invert Y because SVG coordinates start from top left
    const y = height - ((val - minVal) / (maxVal - minVal)) * height;
    return { x, y };
  });

  const pathD = `M ${points.map(p => `${p.x} ${p.y}`).join(' L ')}`;
  const areaD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

  return (
    <div style={{ width: '100%', height: `${height}px`, marginTop: '8px', opacity: 0.85 }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: '100%', height: '100%', overflow: 'visible' }}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={`gradient-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.32" />
            <stop offset="100%" stopColor={color} stopOpacity="0.00" />
          </linearGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Fill Area */}
        <path d={areaD} fill={`url(#gradient-${color})`} />

        {/* Core Line */}
        <path
          d={pathD}
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          filter="url(#glow)"
        />

        {/* Scanning point at end */}
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r="2"
          fill="#ffffff"
          stroke={color}
          strokeWidth="1"
          filter="url(#glow)"
        />
      </svg>
    </div>
  );
};

export default Sparkline;
