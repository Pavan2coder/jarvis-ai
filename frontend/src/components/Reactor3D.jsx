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
const PULSE_COUNT = 45;
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

// Built once at load: random layout must not regenerate on re-render.
const BRAIN = buildBrain();

const NeuralBrain = ({ color, status }) => {
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
      const s = (hover ? 1.06 : 1) * (1 + Math.sin(t * (status === 'idle' ? 1.5 : 6)) * beat);
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
        <lineBasicMaterial color={color} transparent opacity={hover ? 0.5 : 0.28} />
      </lineSegments>

      {/* Neurons */}
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[nodePositions, 3]} />
        </bufferGeometry>
        <pointsMaterial ref={nodeMatRef} color={color} size={0.06} sizeAttenuation transparent opacity={0.9} toneMapped={false} />
      </points>

      {/* Signals firing along synapses */}
      <points ref={pulsePointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[pulsePositions, 3]} />
        </bufferGeometry>
        <pointsMaterial color="#ffffff" size={0.09} sizeAttenuation transparent opacity={0.95} toneMapped={false} />
      </points>

      {/* Soft inner glow */}
      <mesh>
        <sphereGeometry args={[0.35, 24, 24]} />
        <meshBasicMaterial color={color} transparent opacity={hover ? 0.35 : 0.18} toneMapped={false} />
      </mesh>

      {/* Invisible hit-area: glow on hover. */}
      <mesh
        onPointerOver={() => { setHover(true); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = ''; }}
      >
        <sphereGeometry args={[1.25, 16, 16]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
};

const ReactorScene = ({ theme, status }) => {
  const outerRingRef = useRef();
  const middleRingRef = useRef();
  const innerRingRef = useRef();
  const coreRef = useRef();
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

    // Standard Rotations
    if (outerRingRef.current) {
      outerRingRef.current.rotation.y = elapsed * 0.45;
      outerRingRef.current.rotation.z = elapsed * 0.15;
    }
    if (middleRingRef.current) {
      middleRingRef.current.rotation.x = -elapsed * 0.6;
      middleRingRef.current.rotation.y = elapsed * 0.2;
    }
    if (innerRingRef.current) {
      innerRingRef.current.rotation.z = -elapsed * 0.9;
      innerRingRef.current.rotation.x = elapsed * 0.35;
    }

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

    // Core pulsing scale based on status energy
    if (coreRef.current) {
      let pulseSpeed = 2.5;
      let pulseAmount = 0.08;
      
      if (status === 'listening') {
        pulseSpeed = 8.0;
        pulseAmount = 0.25;
      } else if (status === 'speaking') {
        pulseSpeed = 6.0;
        pulseAmount = 0.18;
      } else if (status === 'thinking') {
        pulseSpeed = 4.0;
        pulseAmount = 0.05;
      }
      
      const scaleVal = 1.0 + Math.sin(elapsed * pulseSpeed) * pulseAmount;
      coreRef.current.scale.set(scaleVal, scaleVal, scaleVal);
    }
  });

  return (
    <group>
      {/* Outer Rotating Torus */}
      <mesh ref={outerRingRef}>
        <torusGeometry args={[2.0, 0.03, 16, 100]} />
        <meshStandardMaterial 
          color={primaryColor} 
          emissive={primaryColor}
          emissiveIntensity={1.8}
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>

      {/* Middle Rotating Torus */}
      <mesh ref={middleRingRef}>
        <torusGeometry args={[1.6, 0.03, 16, 100]} />
        <meshStandardMaterial 
          color={primaryColor} 
          emissive={primaryColor}
          emissiveIntensity={1.4}
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>

      {/* Inner Rotating Torus */}
      <mesh ref={innerRingRef}>
        <torusGeometry args={[1.2, 0.02, 12, 80]} />
        <meshStandardMaterial 
          color={primaryColor} 
          emissive={primaryColor}
          emissiveIntensity={1.1}
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>

      {/* Core Pulsating Sphere */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.55, 32, 32]} />
        <meshBasicMaterial 
          color={primaryColor}
          toneMapped={false}
        />
      </mesh>

      {/* NEW: 3D Holographic Cylinder scanlines (spinning) */}
      <mesh ref={scanCylinderRef}>
        <cylinderGeometry args={[2.3, 2.3, 1.4, 24, 6, true]} />
        <meshBasicMaterial
          color={primaryColor}
          wireframe={true}
          transparent={true}
          opacity={0.15}
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

const Reactor3D = ({ theme, status }) => {
  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}>
      <Canvas camera={{ position: [0, 0, 4.4], fov: 65 }}>
        <ambientLight intensity={0.6} />
        <pointLight position={[10, 10, 10]} intensity={1.8} />
        <ReactorScene theme={theme} status={status} />
        <OrbitControls enableZoom={true} enablePan={false} maxDistance={6.5} minDistance={2.2} />
      </Canvas>
    </div>
  );
};

export default Reactor3D;
