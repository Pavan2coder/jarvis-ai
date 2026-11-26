import React, { useRef, useMemo, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

// ── Neural-network "brain" core ────────────────────────────────────────────
// Nodes fill two hemispheres (biased to the surface, like a cortex), each node
// links to its nearest neighbours, and signal pulses hop node→node along links.
const NODE_COUNT = 170;
const LINKS_PER_NODE = 3;
const MAX_LINK_DIST = 0.55;
const PULSE_COUNT = 60;
const BRAIN_SCALE = 1.7;
const PULSE_SPEED = { idle: 0.6, active: 2.2, listening: 1.6, thinking: 3.2, speaking: 1.8 };

const buildBrain = () => {
  const nodes = [];
  while (nodes.length < NODE_COUNT) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2;
    const r = 0.6 + 0.4 * Math.random();            // shell-biased → cortex look
    const sq = Math.sqrt(1 - u * u);
    let x = sq * Math.cos(th) * r, y = u * r, z = sq * Math.sin(th) * r;
    x *= 1.15; y *= 0.8; z *= 0.95;                  // brain proportions (wide, flatter)
    if (Math.abs(x) < 0.07) continue;                // fissure between hemispheres
    if (y < -0.45 && Math.abs(z) > 0.6) continue;    // trim the underside a little
    nodes.push(new THREE.Vector3(x + Math.sign(x) * 0.05, y, z));
  }
  const edges = [];
  const adj = nodes.map(() => []);
  const seen = new Set();
  nodes.forEach((a, i) => {
    nodes
      .map((b, j) => [j, a.distanceTo(b)])
      .filter(([j, d]) => j !== i && d < MAX_LINK_DIST)
      .sort((p, q) => p[1] - q[1])
      .slice(0, LINKS_PER_NODE)
      .forEach(([j]) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (seen.has(key)) return;
        seen.add(key);
        edges.push([i, j]);
        adj[i].push(j); adj[j].push(i);
      });
  });
  // Each pulse travels from node `from` to node `to`; on arrival it hops to a random neighbour.
  const pulses = Array.from({ length: PULSE_COUNT }, () => {
    const [from, to] = edges[Math.floor(Math.random() * edges.length)];
    return { from, to, t: Math.random() };
  });
  return { nodes, edges, adj, pulses };
};

// Round soft dot sprite so points render as glowing neurons, not squares.
const DOT = (() => {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.8)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

// Built once at load: random layout must not regenerate on re-render.
const BRAIN = buildBrain();

const NeuralBrain = ({ color, status, onActivate }) => {
  const groupRef = useRef();
  const pulsePointsRef = useRef();
  const nodeMatRef = useRef();
  const [hover, setHover] = useState(false);

  const { nodes, edges, adj, pulses } = BRAIN;

  const nodePositions = useMemo(() => new Float32Array(nodes.flatMap(v => [v.x, v.y, v.z])), [nodes]);
  const linePositions = useMemo(
    () => new Float32Array(edges.flatMap(([a, b]) => [nodes[a].x, nodes[a].y, nodes[a].z, nodes[b].x, nodes[b].y, nodes[b].z])),
    [nodes, edges]
  );

  const pulsePositions = useMemo(() => new Float32Array(PULSE_COUNT * 3), []);

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime();
    const speed = (PULSE_SPEED[status] ?? PULSE_SPEED.idle) * (hover ? 1.6 : 1);

    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.25;
      groupRef.current.rotation.x = Math.sin(t * 0.3) * 0.12;
      const beat = status === 'listening' ? 0.06 : status === 'speaking' ? 0.04 : 0.015;
      const s = BRAIN_SCALE * (hover ? 1.06 : 1) * (1 + Math.sin(t * (status === 'idle' ? 1.5 : 6)) * beat);
      groupRef.current.scale.setScalar(s);
    }

    pulses.forEach((p, k) => {
      p.t += delta * speed * 1.4;
      if (p.t >= 1) {
        const next = adj[p.to];
        p.from = p.to;
        p.to = next.length ? next[Math.floor(Math.random() * next.length)] : p.from;
        p.t = 0;
      }
      const a = nodes[p.from], b = nodes[p.to];
      pulsePositions[k * 3] = a.x + (b.x - a.x) * p.t;
      pulsePositions[k * 3 + 1] = a.y + (b.y - a.y) * p.t;
      pulsePositions[k * 3 + 2] = a.z + (b.z - a.z) * p.t;
    });
    if (pulsePointsRef.current) pulsePointsRef.current.geometry.attributes.position.needsUpdate = true;

    if (nodeMatRef.current) nodeMatRef.current.opacity = 0.75 + Math.sin(t * 3) * 0.2;
  });

  return (
    <group ref={groupRef}>
      {/* Synapses */}
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={hover ? 0.7 : 0.45} />
      </lineSegments>

      {/* Neurons */}
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[nodePositions, 3]} />
        </bufferGeometry>
        <pointsMaterial ref={nodeMatRef} color={color} size={0.14} map={DOT} depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation transparent opacity={0.9} toneMapped={false} />
      </points>

      {/* Signals firing along synapses */}
      <points ref={pulsePointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[pulsePositions, 3]} />
        </bufferGeometry>
        <pointsMaterial color="#ffffff" size={0.22} map={DOT} depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation transparent opacity={0.95} toneMapped={false} />
      </points>

      {/* Soft inner glow */}
      <mesh>
        <sphereGeometry args={[0.35, 24, 24]} />
        <meshBasicMaterial color={color} transparent opacity={hover ? 0.35 : 0.18} toneMapped={false} />
      </mesh>

      {/* Invisible hit-area: click the brain to wake Jarvis. delta = px moved, so orbit-drags don't count. */}
      <mesh
        onClick={e => { e.stopPropagation(); if (e.delta < 6) onActivate?.(); }}
        onPointerOver={() => { setHover(true); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = ''; }}
      >
        <sphereGeometry args={[1.25, 16, 16]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
};

const ReactorScene = ({ theme, status, onActivate }) => {
  const scanCylinderRef = useRef();
  const hudRingRef1 = useRef();
  const hudRingRef2 = useRef();

  // Get color based on state/theme
  const getThemeColor = () => {
    if (status && status !== 'idle') {
      const stateColors = {
        active: '#39ff88',      // Green
        listening: '#ffcf4d',   // Gold
        thinking: '#ff9d2f',    // Orange
        speaking: '#00f0ff',    // Cyan
      };
      return stateColors[status] || '#3ad1ff';
    }
    // Idle theme colors
    const themeColors = {
      cyan: '#3ad1ff',
      stark: '#ff2d55',
      vibranium: '#bd00ff',
      stealth: '#ffffff',
    };
    return themeColors[theme] || '#3ad1ff';
  };

  const primaryColor = getThemeColor();

  useFrame(({ clock }) => {
    const elapsed = clock.getElapsedTime();

    // Rotations of HUD rings (flatter sci-fi dials)
    if (hudRingRef1.current) {
      hudRingRef1.current.rotation.z = elapsed * 0.3;
    }
    if (hudRingRef2.current) {
      hudRingRef2.current.rotation.z = -elapsed * 0.55;
    }

    // Vertical holographic scanning beam pulsing
    if (scanCylinderRef.current) {
      scanCylinderRef.current.rotation.y = -elapsed * 0.8;
      // Pulse scale vertically
      const scanPulse = 1.0 + Math.sin(elapsed * 4.0) * 0.15;
      scanCylinderRef.current.scale.set(1, scanPulse, 1);
    }

  });

  return (
    <group>
      <NeuralBrain color={primaryColor} status={status} onActivate={onActivate} />

      {/* NEW: 3D Holographic Cylinder scanlines (spinning) */}
      <mesh ref={scanCylinderRef}>
        <cylinderGeometry args={[2.3, 2.3, 1.4, 24, 6, true]} />
        <meshBasicMaterial
          color={primaryColor}
          wireframe={true}
          transparent={true}
          opacity={0.06}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* NEW: Flatter concentric HUD Compass Ring 1 */}
      <group ref={hudRingRef1} rotation={[Math.PI / 2, 0, 0]}>
        <mesh>
          <ringGeometry args={[2.4, 2.44, 40]} />
          <meshBasicMaterial 
            color={primaryColor} 
            transparent 
            opacity={0.4} 
            side={THREE.DoubleSide}
            wireframe
          />
        </mesh>
        {/* Alignment Ticks (orbiting nodes) */}
        {Array.from({ length: 12 }).map((_, idx) => {
          const angle = (idx / 12) * Math.PI * 2;
          return (
            <mesh key={idx} position={[Math.cos(angle) * 2.42, Math.sin(angle) * 2.42, 0]}>
              <boxGeometry args={[0.08, 0.08, 0.02]} />
              <meshBasicMaterial color={primaryColor} />
            </mesh>
          );
        })}
      </group>

      {/* NEW: Flatter Concentric HUD Target Ring 2 (smaller, counter-spinning) */}
      <group ref={hudRingRef2} rotation={[Math.PI / 2, 0, 0]}>
        <mesh>
          <ringGeometry args={[1.9, 1.92, 30]} />
          <meshBasicMaterial 
            color={primaryColor} 
            transparent 
            opacity={0.3} 
            side={THREE.DoubleSide}
          />
        </mesh>
        {/* Notch details */}
        {Array.from({ length: 6 }).map((_, idx) => {
          const angle = (idx / 6) * Math.PI * 2 + 0.3;
          return (
            <mesh key={idx} position={[Math.cos(angle) * 1.91, Math.sin(angle) * 1.91, 0]}>
              <sphereGeometry args={[0.04, 8, 8]} />
              <meshBasicMaterial color={primaryColor} />
            </mesh>
          );
        })}
      </group>

      {/* Glowing Outer Corona Particle Rings */}
      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[
              new Float32Array(
                Array.from({ length: 180 }, () => {
                  const angle = Math.random() * Math.PI * 2;
                  const radius = 2.2 + Math.random() * 0.25;
                  return [Math.cos(angle) * radius, Math.sin(angle) * radius, (Math.random() - 0.5) * 0.1];
                }).flat()
              ),
              3
            ]}
          />
        </bufferGeometry>
        <pointsMaterial color={primaryColor} size={0.035} sizeAttenuation={true} transparent opacity={0.8} />
      </points>

      {/* Floating Sparkles inside */}
      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[
              new Float32Array(
                Array.from({ length: 60 }, () => {
                  const angle = Math.random() * Math.PI * 2;
                  const radius = Math.random() * 1.1;
                  return [Math.cos(angle) * radius, Math.sin(angle) * radius, (Math.random() - 0.5) * 0.8];
                }).flat()
              ),
              3
            ]}
          />
        </bufferGeometry>
        <pointsMaterial color="#ffffff" size={0.02} sizeAttenuation={true} transparent opacity={0.7} />
      </points>
    </group>
  );
};

const Reactor3D = ({ theme, status, onActivate }) => {
  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}>
      <Canvas camera={{ position: [0, 0, 4.4], fov: 65 }}>
        <ambientLight intensity={0.6} />
        <pointLight position={[10, 10, 10]} intensity={1.8} />
        <ReactorScene theme={theme} status={status} onActivate={onActivate} />
        <OrbitControls enableZoom={false} enablePan={false} />
      </Canvas>
    </div>
  );
};

export default Reactor3D;
