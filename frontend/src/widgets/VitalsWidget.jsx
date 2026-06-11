import React from 'react';
import { useHud } from '../hooks/useHud';
import GlowCard from '../components/GlowCard';
import DecryptedText from '../components/DecryptedText';
import Sparkline from '../components/Sparkline';

const CIRC = 188.5;
const getDashOffset = (val) => {
  if (val == null) return CIRC;
  return CIRC * (1 - val / 100);
};

const getCpuStrokeColor = (pct) => {
  if (pct > 85) return 'var(--red)';
  if (pct > 60) return 'var(--orange)';
  return 'var(--blue)';
};

const VitalsWidget = () => {
  const { stats } = useHud();

  return (
    <GlowCard>
      <div className="ttl">
        <DecryptedText text="// Vitals" animateOn="hover" />
      </div>
      <div className="gauges">
        <div className="gauge">
          <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
            <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
            <circle
              className="fill"
              cx="36"
              cy="36"
              r="30"
              fill="none"
              strokeWidth="5"
              strokeDasharray={CIRC}
              strokeDashoffset={getDashOffset(stats.cpu)}
              style={{ stroke: getCpuStrokeColor(stats.cpu) }}
            />
            <text className="num" x="36" y="41" textAnchor="middle">
              {stats.cpu != null ? Math.round(stats.cpu) : '--'}
            </text>
          </svg>
          <div className="lbl">CPU</div>
          <div className="sub">&nbsp;</div>
          <Sparkline value={stats.cpu} color={getCpuStrokeColor(stats.cpu)} height={20} />
        </div>
        
        <div className="gauge">
          <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
            <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
            <circle
              className="fill"
              cx="36"
              cy="36"
              r="30"
              fill="none"
              strokeWidth="5"
              strokeDasharray={CIRC}
              strokeDashoffset={getDashOffset(stats.ram)}
              style={{ stroke: 'var(--gold)' }}
            />
            <text className="num" x="36" y="41" textAnchor="middle">
              {stats.ram != null ? Math.round(stats.ram) : '--'}
            </text>
          </svg>
          <div className="lbl">MEM</div>
          <div className="sub">{stats.ram_used != null ? `${stats.ram_used}/${stats.ram_total}GB` : ' '}</div>
          <Sparkline value={stats.ram} color="var(--gold)" height={20} />
        </div>

        <div className="gauge">
          <svg className="radial-gauge" width="72" height="72" viewBox="0 0 72 72">
            <circle className="track" cx="36" cy="36" r="30" fill="none" strokeWidth="5" />
            <circle
              className="fill"
              cx="36"
              cy="36"
              r="30"
              fill="none"
              strokeWidth="5"
              strokeDasharray={CIRC}
              strokeDashoffset={getDashOffset(stats.gpu)}
              style={{ stroke: 'var(--cyan)' }}
            />
            <text className="num" x="36" y="41" textAnchor="middle">
              {stats.gpu != null ? Math.round(stats.gpu) : '--'}
            </text>
          </svg>
          <div className="lbl">GPU</div>
          <div className="sub">{stats.gpu_mem_used != null ? `${stats.gpu_mem_used}/${stats.gpu_mem_total}MB` : (stats.gpu == null ? 'n/a' : ' ')}</div>
          <Sparkline value={stats.gpu} color="var(--cyan)" height={20} />
        </div>
      </div>
    </GlowCard>
  );
};

export default VitalsWidget;
