// Holographic Scanning Line & Ring Shader (Reference GLSL)
uniform float uTime;
uniform vec3 uColor;
varying vec2 vUv;

void main() {
    // Normal circle coordinate
    vec2 uv = vUv - 0.5;
    float dist = length(uv);
    
    // Core ring logic
    float ring = smoothstep(0.4, 0.41, dist) - smoothstep(0.42, 0.43, dist);
    
    // Moving scan lines
    float scanline = sin(uv.y * 50.0 + uTime * 4.0) * 0.5 + 0.5;
    
    // Radial grid lines
    float angle = atan(uv.y, uv.x);
    float spokes = step(0.98, sin(angle * 12.0));
    
    vec3 finalColor = uColor * (ring + scanline * 0.15 + spokes * 0.05);
    float alpha = ring + scanline * 0.1 + spokes * 0.02;
    
    gl_FragColor = vec4(finalColor, alpha);
}
