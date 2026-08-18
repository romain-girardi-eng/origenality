/* Origenality — explorer dust.
   Particle vertex/fragment, velocity/position GPGPU and gaussian node
   sampling copied from the pragma-cloud engine (romain.pragma-cloud.com).
   Graph-node path only: no wordmark morph, no edge filaments.
   Romain Girardi, 2026. */

import * as THREE from './vendor/three.module.min.js';
import { GPUComputationRenderer } from './vendor/GPUComputationRenderer.js';

const velocityFragmentShader = "\n  uniform sampler2D uTargetA;\n  uniform sampler2D uTargetB;\n  uniform float uTargetMix;\n  uniform float uAssembled;\n  uniform float uTime;\n  uniform float uDelta;\n  uniform float uNoiseFreq;\n  uniform float uNoiseAmp;\n  uniform float uSpring;\n  uniform float uDamping;\n  uniform float uMaxSpeed;\n  uniform float uTransit;\n  uniform vec2 uPointer;\n  uniform vec2 uPointerPrev;\n  uniform float uPointerActive;\n  uniform float uPointerRadius;\n  uniform float uPointerAmp;\n  uniform float uPointerSwirl;\n\n  \n  vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}\n  vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}\n  vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}\n  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}\n  float snoise(vec3 v){\n    const vec2 C=vec2(1.0/6.0,1.0/3.0);\n    const vec4 D=vec4(0.0,0.5,1.0,2.0);\n    vec3 i=floor(v+dot(v,C.yyy));\n    vec3 x0=v-i+dot(i,C.xxx);\n    vec3 g=step(x0.yzx,x0.xyz);\n    vec3 l=1.0-g;\n    vec3 i1=min(g.xyz,l.zxy);\n    vec3 i2=max(g.xyz,l.zxy);\n    vec3 x1=x0-i1+C.xxx;\n    vec3 x2=x0-i2+C.yyy;\n    vec3 x3=x0-D.yyy;\n    i=mod289(i);\n    vec4 p=permute(permute(permute(\n      i.z+vec4(0.0,i1.z,i2.z,1.0))\n      +i.y+vec4(0.0,i1.y,i2.y,1.0))\n      +i.x+vec4(0.0,i1.x,i2.x,1.0));\n    float n_=0.142857142857;\n    vec3 ns=n_*D.wyz-D.xzx;\n    vec4 j=p-49.0*floor(p*ns.z*ns.z);\n    vec4 x_=floor(j*ns.z);\n    vec4 y_=floor(j-7.0*x_);\n    vec4 x=x_*ns.x+ns.yyyy;\n    vec4 y=y_*ns.x+ns.yyyy;\n    vec4 h=1.0-abs(x)-abs(y);\n    vec4 b0=vec4(x.xy,y.xy);\n    vec4 b1=vec4(x.zw,y.zw);\n    vec4 s0=floor(b0)*2.0+1.0;\n    vec4 s1=floor(b1)*2.0+1.0;\n    vec4 sh=-step(h,vec4(0.0));\n    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;\n    vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;\n    vec3 p0=vec3(a0.xy,h.x);\n    vec3 p1=vec3(a0.zw,h.y);\n    vec3 p2=vec3(a1.xy,h.z);\n    vec3 p3=vec3(a1.zw,h.w);\n    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));\n    p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;\n    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);\n    m=m*m;\n    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));\n  }\n  vec3 snoiseVec3(vec3 x){\n    return vec3(\n      snoise(vec3(x.x,x.y,x.z)),\n      snoise(vec3(x.y-19.1,x.z+33.4,x.x+47.2)),\n      snoise(vec3(x.z+74.2,x.x-124.5,x.y+99.4)));\n  }\n  vec3 curlNoise(vec3 p){\n    const float e=0.1;\n    vec3 dx=vec3(e,0.0,0.0);\n    vec3 dy=vec3(0.0,e,0.0);\n    vec3 dz=vec3(0.0,0.0,e);\n    vec3 p_x0=snoiseVec3(p-dx);\n    vec3 p_x1=snoiseVec3(p+dx);\n    vec3 p_y0=snoiseVec3(p-dy);\n    vec3 p_y1=snoiseVec3(p+dy);\n    vec3 p_z0=snoiseVec3(p-dz);\n    vec3 p_z1=snoiseVec3(p+dz);\n    float cx=(p_y1.z-p_y0.z)-(p_z1.y-p_z0.y);\n    float cy=(p_z1.x-p_z0.x)-(p_x1.z-p_x0.z);\n    float cz=(p_x1.y-p_x0.y)-(p_y1.x-p_y0.x);\n    return normalize(vec3(cx,cy,cz)/(2.0*e)+1e-6);\n  }\n\n\n  void main(){\n    vec2 uv = gl_FragCoord.xy / resolution.xy;\n    vec4 posT = texture2D(uTexturePosition, uv);\n    vec4 velT = texture2D(uTextureVelocity, uv);\n    vec3 pos = posT.xyz;\n    vec3 vel = velT.xyz;\n    float dt = uDelta;\n\n    // per-particle staggered A->B progress so the field re-forms as a wave,\n    // not an all-at-once snap\n    float ph = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);\n    float lm = smoothstep(ph * 0.55, ph * 0.55 + 0.45, uTargetMix);\n    vec3 homeA = texture2D(uTargetA, uv).xyz;\n    vec3 homeB = texture2D(uTargetB, uv).xyz;\n    vec3 home = mix(homeA, homeB, lm);\n\n    vec3 flow = curlNoise(pos * uNoiseFreq + uTime * 0.12) * uNoiseAmp;\n    vec3 spring = (home - pos) * uSpring * 60.0;\n\n    float transitEnv = sin(lm * 3.14159265);\n    vec3 transit = curlNoise(pos * 0.26 + home * 0.30 + uTime * 0.18) * uTransit * 1.25 * transitEnv;\n    transit += curlNoise(pos * 0.12 - uTime * 0.10) * uTransit * 0.45 * transitEnv;\n\n    // both decays below are per-second rates raised to (dt*60): at exactly\n    // 60Hz this is identical to the old per-frame multiply, but at any other\n    // refresh rate the total damping over one real second stays the same\n    // (a bare \"vel *= k\" per callback would over- or under-damp at 120Hz vs 60Hz)\n    float frameScale = dt * 60.0;\n    float damp = mix(uDamping, 0.62, uAssembled * uAssembled);\n    float decayEff = pow(max(damp, 0.0001), frameScale);\n\n    // pointer ripple: soft radial parting + a touch of tangential swirl,\n    // world-space radius uPointerRadius. The falloff is measured against\n    // the SEGMENT swept by the cursor this frame (uPointerPrev -> uPointer),\n    // not the point alone: a fast stroke carves one continuous wake instead\n    // of leaving untouched gaps between per-frame cursor samples. Direction\n    // vectors are normalize()'d so the falloff alone (not distance) sets\n    // amplitude; a drag component along the sweep grows with stroke speed\n    // so quick strokes visibly pull the ink with them (zero when idle).\n    vec2 segPa = pos.xy - uPointerPrev;\n    vec2 segBa = uPointer - uPointerPrev;\n    float segLen2 = max(dot(segBa, segBa), 1e-6);\n    float segH = clamp(dot(segPa, segBa) / segLen2, 0.0, 1.0);\n    vec2 toPointer = segPa - segBa * segH;\n    float pointerDist = length(toPointer);\n    float pointerFalloff = 1.0 - smoothstep(0.0, uPointerRadius, pointerDist);\n    pointerFalloff *= pointerFalloff;\n    vec2 pointerRadialDir = toPointer / max(pointerDist, 1e-4);\n    vec2 pointerTangentDir = vec2(-pointerRadialDir.y, pointerRadialDir.x);\n    vec2 sweepDir = segBa * inversesqrt(segLen2);\n    float sweepAmt = min(length(segBa) / uPointerRadius, 1.0);\n    // motion-gated: a RESTING cursor barely stirs the ink (no carved-out\n    // ring under an idle pointer); the parting/swirl/drag strength follows\n    // the stroke speed instead\n    float motionK = mix(0.12, 1.0, min(length(segBa) / (uPointerRadius * 0.35), 1.0));\n    vec2 pointerPush = (pointerRadialDir * uPointerAmp\n      + pointerTangentDir * uPointerSwirl\n      + sweepDir * uPointerAmp * 0.8 * sweepAmt) * motionK;\n    vec3 pointerForce = vec3(pointerPush, 0.0) * pointerFalloff * uPointerActive;\n\n    // hard freeze at full assembly: velocity can never slowly build back up\n    // \u2014 EXCEPT locally around an active pointer, where the freeze is eased\n    // off (never fully lifted) so the just-injected pointerForce can still\n    // move the surface instead of being crushed the same frame it lands.\n    // Folded into decayTotal (below) BEFORE the pointer gain is computed,\n    // because the gain needs the FULL per-frame decay actually applied to\n    // vel this step \u2014 damping AND freeze together \u2014 not decayEff alone.\n    float freezeK = 0.55 * smoothstep(0.92, 1.0, uAssembled);\n    freezeK *= 1.0 - 0.85 * pointerFalloff * uPointerActive;\n    float freezeDecay = pow(max(1.0 - freezeK, 0.0001), frameScale);\n    float decayTotal = decayEff * freezeDecay;\n\n    vec3 force = mix(flow, spring, uAssembled) + transit;\n    vel += force * dt;\n\n    // Exact dt-invariant pointer steady state. With this integration order\n    // (impulse added, THEN vel *= decayTotal), the recurrence\n    // v_(n+1) = (v_n + pointerForce*gain) * decayTotal converges to\n    // v_ss = pointerForce*gain*decayTotal/(1-decayTotal) \u2014 so a bare\n    // gain=dt (or any gain that only approximates decayTotal's own dt\n    // dependence) still leaves a residual dt-dependence baked into that\n    // extra decayTotal/(1-decayTotal) factor. Setting\n    // gain = (1-decayTotal)/decayTotal makes gain*decayTotal/(1-decayTotal)\n    // cancel to EXACTLY 1 for any decayTotal in (0,1), so v_ss ==\n    // pointerForce identically \u2014 independent of dt AND of the freeze factor\n    // \u2014 rather than only approximately matching a dt=1/60 reference.\n    float pointerGain = (1.0 - decayTotal) / max(decayTotal, 1e-5);\n    vel += pointerForce * pointerGain;\n\n    vel *= decayTotal;\n\n    float sp = length(vel);\n    if (sp > uMaxSpeed) vel = normalize(vel) * uMaxSpeed;\n\n    gl_FragColor = vec4(vel, velT.w);\n  }\n";
const positionFragmentShader = "\n  uniform float uDelta;\n  void main(){\n    vec2 uv = gl_FragCoord.xy / resolution.xy;\n    vec4 posT = texture2D(uTexturePosition, uv);\n    vec4 velT = texture2D(uTextureVelocity, uv);\n    vec3 pos = posT.xyz;\n    vec3 vel = velT.xyz;\n    pos += vel * uDelta * 60.0;\n    float age = posT.w + uDelta * 0.3;\n    if (age >= 1.0) age = fract(age);\n    gl_FragColor = vec4(pos, age);\n  }\n";
const particleVertexShader = "\n  uniform sampler2D uTexturePosition;\n  uniform sampler2D uTextureVelocity;\n  uniform sampler2D uColorKeyTex;\n  uniform float uSpacingA;\n  uniform float uSpacingB;\n  uniform float uEdgeSpacingA;\n  uniform float uEdgeSpacingB;\n  uniform float uSizeFactor;\n  uniform float uEdgeSizeFactor;\n  uniform float uDPR;\n  uniform float uZoom;\n  uniform float uCX;\n  uniform float uCY;\n  uniform float uViewportW;\n  uniform float uViewportH;\n  uniform float uTargetMix;\n  uniform float uPhaseA;\n  uniform float uPhaseB;\n  uniform float uFocusGroup;\n  uniform float uHasFocus;\n  uniform float uTime;\n  uniform float uHubGroup;\n  uniform float uAssembled;\n  attribute vec2 aParticlesUv;\n\n  varying float vSpeed;\n  varying float vPaletteIdx;\n  varying float vGroupId;\n  varying float vIsEdge;\n  varying float vPhaseAmount;\n  varying float vEdgeT;\n  varying float vEdgePhase;\n  varying float vBreath;\n  varying float vFlash;\n  varying float vAlphaVar;\n\n  void main(){\n    vec4 posT = texture2D(uTexturePosition, aParticlesUv);\n    vec4 velT = texture2D(uTextureVelocity, aParticlesUv);\n    vec3 pos = posT.xyz;\n    float life = posT.w;\n\n    vSpeed = length(velT.xyz);\n\n    // colorKey decode: colorKey = paletteIndex + storedGroup*8, storedGroup = groupId+1\n    // (groupId 0..N-1 is the node index for focus matching; groupId -1 = edge\n    // particle, encoded as storedGroup 0, which can never match a real uFocusGroup).\n    // the g/b channels of the same texture carry the edge's bezier parameter\n    // (vEdgeT, 0 for node particles) and a per-edge random phase (vEdgePhase,\n    // shared by every particle sampled off that edge) \u2014 both feed the\n    // traveling signal pulse in the fragment shader. The a channel carries a\n    // node particle's arrival phase (see targets.ts's arrivalPhase / the\n    // flash block below); unused (but harmless) for edge particles.\n    vec4 aux = texture2D(uColorKeyTex, aParticlesUv);\n    float colorKey = aux.r;\n    float storedGroup = floor(colorKey / 8.0);\n    vPaletteIdx = colorKey - storedGroup * 8.0;\n    vGroupId = storedGroup - 1.0;\n    vIsEdge = step(vGroupId, -0.5);\n    vEdgeT = aux.g;\n    vEdgePhase = aux.b;\n    float arrivalPhase = aux.a;\n\n    float ph = fract(sin(dot(aParticlesUv, vec2(12.9898, 78.233))) * 43758.5453);\n    float lm = smoothstep(ph * 0.55, ph * 0.55 + 0.45, uTargetMix);\n    // fractional only while uPhaseA != uPhaseB, i.e. only during a genuine\n    // transition \u2014 an idle particle (uPhaseA == uPhaseB) stays pinned at that\n    // exact phase for every lm, so this doubles as the \"is transitioning\" test\n    vPhaseAmount = mix(uPhaseA, uPhaseB, lm);\n\n    // node-cluster life: a slow per-node breathing oscillation (the hub\n    // breathes more, a focused node breathes a touch faster) \u2014 computed\n    // once here and reused in the fragment shader for brightness/size so the\n    // two stages never drift apart.\n    float nodePhase = fract(sin(vGroupId * 12.9898 + 4.7) * 43758.5453);\n    float isHub = step(abs(vGroupId - uHubGroup), 0.5);\n    float isFocusedNode = 0.0;\n    if (uHasFocus > 0.5) isFocusedNode = step(abs(vGroupId - uFocusGroup), 0.5);\n    float breathSpeed = 0.5 + 0.35 * isHub + 0.45 * isFocusedNode;\n    vBreath = sin(uTime * breathSpeed + nodePhase * 6.2831853);\n\n    // synaptic flash, COUPLED to a real pulse arrival: arrivalPhase (see\n    // targets.ts) is the phase of the ONE incoming edge chosen for this\n    // node, and the formula below \u2014 pulse speed, lap index, firing roll \u2014\n    // is deliberately identical to the edge pulse's own formula in the\n    // fragment shader (same magic constants, same phase value), so this\n    // node \"fires\" in exact lockstep with that edge's pulse completing a\n    // firing lap, i.e. actually arriving, not on an independent clock. A\n    // node that is never a destination (arrivalPhase < 0) never flashes.\n    float hasArrival = step(0.0, arrivalPhase);\n    float arrivalSpeed = 0.16 + 0.30 * fract(arrivalPhase * 7.13);\n    float arrivalClock = uTime * arrivalSpeed + arrivalPhase;\n    float arrivalPos = fract(arrivalClock);\n    // distance to the wrap point (0 == 1 in this looping parametrization) is\n    // the moment the edge's pulse completes its lap, i.e. arrives at t=1\n    float arrivalDist = min(arrivalPos, 1.0 - arrivalPos);\n    float arrivalLapIdx = floor(arrivalClock);\n    float arrivalFireRoll = fract(sin(arrivalLapIdx * 53.219 + arrivalPhase * 91.7) * 24634.6345);\n    float arrivalFiring = step(0.76, arrivalFireRoll);\n    float arrivalWindow = 1.0 - smoothstep(0.0, 0.10, arrivalDist);\n    vFlash = hasArrival * arrivalFiring * arrivalWindow;\n\n    // Sub-pixel shimmer: at HARD FREEZE (uAssembled -> 1) the simulated\n    // position is fully locked, so without this the assembled ink/graph\n    // would read as visually dead. This is a purely screen-space wobble\n    // (position AND size), never fed back into the physics sim, so it can't\n    // fight the freeze \u2014 amplitude fades in with uAssembled and is a\n    // fraction of a px, period 2-6s per particle (own hash, decorrelated\n    // from the size/morph hash) so the surface shimmers without ever\n    // looking like it's reassembling or drifting.\n    float shimmerPhaseX = fract(sin(dot(aParticlesUv, vec2(93.989, 67.345))) * 24634.6345);\n    float shimmerPhaseY = fract(sin(dot(aParticlesUv, vec2(51.123, 14.775))) * 12345.6789);\n    float shimmerFreq = 1.0 / (2.0 + 4.0 * shimmerPhaseX);\n    float shimmerX = sin(uTime * 6.2831853 * shimmerFreq + shimmerPhaseX * 6.2831853);\n    float shimmerY = sin(uTime * 6.2831853 * shimmerFreq * 1.3 + shimmerPhaseY * 6.2831853);\n    float shimmerAmt = uAssembled * uAssembled;\n    float shimmerPx = 0.5;\n\n    float ndcX = (pos.x - uCX) * uZoom * (2.0 / uViewportW) + shimmerX * shimmerPx * shimmerAmt * (2.0 / uViewportW);\n    float ndcY = -(pos.y - uCY) * uZoom * (2.0 / uViewportH) + shimmerY * shimmerPx * shimmerAmt * (2.0 / uViewportH);\n    gl_Position = vec4(ndcX, ndcY, 0.0, 1.0);\n\n    // focus only applies once the particle has actually arrived in graph\n    // space \u2014 never during wordmark phase or the first half of a transition\n    float sizeBoost = 1.0;\n    if (uHasFocus > 0.5 && vPhaseAmount > 0.5) {\n      float match = step(abs(vGroupId - uFocusGroup), 0.5);\n      sizeBoost = mix(1.0, 1.15, match);\n    }\n\n    float pop = 0.65 + 0.35 * sin(life * 3.14159265);\n    // static per-particle size variation (same hash as the morph stagger, so\n    // it stays stable frame to frame) keeps clusters from reading as a\n    // uniform dot grid.\n    float sizeVar = 0.82 + 0.36 * ph;\n    float alphaVarSeed = fract(sin(dot(aParticlesUv, vec2(19.81, 7.34))) * 24634.6345);\n    vAlphaVar = 0.75 + 0.5 * alphaVarSeed;\n    float breathSize = 1.0 + (0.05 * vBreath + 0.16 * vFlash) * (1.0 - vIsEdge) * vPhaseAmount;\n    float shimmerSize = 1.0 + 0.07 * shimmerY * shimmerAmt;\n\n    // Point diameter is derived from the ACTUAL median spacing between\n    // target positions (see targets.ts's estimateSpacing), not a fixed px\n    // constant: a fixed size can't track how tightly 262k particles pack\n    // into a wordmark vs. a graph cluster, which is what fused the ink into\n    // a blurry slab. uSpacingA/B track whichever target is active (wordmark\n    // ink or graph node-cluster spacing); uEdgeSpacingA/B are the same but\n    // for edge-filament particles, which pack far tighter and need both a\n    // smaller measured spacing AND a smaller factor to read as fine threads\n    // rather than smears.\n    float spacingBase = mix(uSpacingA, uSpacingB, lm);\n    float spacingEdge = mix(uEdgeSpacingA, uEdgeSpacingB, lm);\n    float spacingWorld = mix(spacingBase, spacingEdge, vIsEdge);\n    float sizeFactor = mix(uSizeFactor, uEdgeSizeFactor, vIsEdge);\n    float sz = spacingWorld * uZoom * uDPR * sizeFactor * pop * sizeVar * sizeBoost * breathSize * shimmerSize;\n    gl_PointSize = clamp(sz, 1.1, 34.0);\n  }\n";
const particleFragmentShader = "\n  precision highp float;\n  varying float vSpeed;\n  varying float vPaletteIdx;\n  varying float vGroupId;\n  varying float vIsEdge;\n  varying float vPhaseAmount;\n  varying float vEdgeT;\n  varying float vEdgePhase;\n  varying float vBreath;\n  varying float vFlash;\n  varying float vAlphaVar;\n  uniform vec3 uInk;\n  uniform vec3 uLapis;\n  uniform vec3 uGold;\n  uniform vec3 uRed;\n  uniform vec3 uOchre;\n  uniform vec3 uGraphite;\n  uniform vec3 uGreen;\n  uniform float uFocusGroup;\n  uniform float uHasFocus;\n  uniform float uTime;\n\n  void main(){\n    vec2 q = gl_PointCoord - 0.5;\n    float r = length(q);\n    if (r > 0.5) discard;\n    float a = 1.0 - smoothstep(0.30, 0.5, r);\n    float fres = pow(r * 2.0, 1.6);\n\n    vec3 branchCol = uLapis;\n    if (vPaletteIdx > 4.5) branchCol = uGreen;\n    else if (vPaletteIdx > 3.5) branchCol = uGraphite;\n    else if (vPaletteIdx > 2.5) branchCol = uOchre;\n    else if (vPaletteIdx > 1.5) branchCol = uRed;\n    else if (vPaletteIdx > 0.5) branchCol = uGold;\n\n    vec3 paleGold = mix(uGold, vec3(1.0), 0.55);\n    vec3 graphCol = mix(branchCol, paleGold, vIsEdge);\n    graphCol += branchCol * fres * 0.22 * (1.0 - vIsEdge);\n\n    // neural signal: a warm white-gold pulse travels along the edge's bezier\n    // parameter (vEdgeT), looping at a per-edge speed/phase (vEdgePhase) so\n    // edges never fire in lockstep. Occasional \"firing\" laps push the pulse\n    // brighter still \u2014 the closest a shader-only, per-point renderer gets to\n    // a signal visibly propagating from one node into another. Gated by\n    // vPhaseAmount so pulses only read once the graph has actually assembled.\n    float pulseSpeed = 0.16 + 0.30 * fract(vEdgePhase * 7.13);\n    float pulsePos = fract(uTime * pulseSpeed + vEdgePhase);\n    float pd = abs(vEdgeT - pulsePos);\n    pd = min(pd, 1.0 - pd);\n    // both windows written as 1.0 - smoothstep(lo, hi, x) with lo < hi:\n    // smoothstep(hi, lo, x) with hi > lo is reversed-edge undefined behavior\n    // per the GLSL ES 1.00 spec (driver-dependent, can render black/garbage)\n    float pulseCore = 1.0 - smoothstep(0.0, 0.055, pd);\n    float pulseGlow = (1.0 - smoothstep(0.02, 0.16, pd)) * 0.45;\n    float pulseLapIdx = floor(uTime * pulseSpeed + vEdgePhase);\n    float pulseFireRoll = fract(sin(pulseLapIdx * 53.219 + vEdgePhase * 91.7) * 24634.6345);\n    float pulseFiring = step(0.76, pulseFireRoll);\n    float pulseRaw = max(pulseCore, pulseGlow) * mix(1.0, 1.9, pulseFiring);\n    float pulseMix = clamp(pulseRaw, 0.0, 1.0) * vIsEdge * vPhaseAmount;\n    float pulseOverdrive = max(pulseRaw - 1.0, 0.0) * vIsEdge * vPhaseAmount;\n\n    vec3 pulseColor = mix(uGold, vec3(1.0, 0.97, 0.85), pulseCore);\n    graphCol = mix(graphCol, pulseColor, pulseMix);\n\n    vec3 col = mix(uInk, graphCol, vPhaseAmount);\n\n    // ignition flash: mid-transition, blend toward gold (peaks at 0.5, zero\n    // at either settled phase \u2014 see vPhaseAmount's transitioning-test note above)\n    float ignition = 4.0 * vPhaseAmount * (1.0 - vPhaseAmount);\n    col = mix(col, uGold, ignition * 0.5);\n\n    float dim = 1.0;\n    float bright = 1.0;\n    if (uHasFocus > 0.5 && vPhaseAmount > 0.5) {\n      float match = step(abs(vGroupId - uFocusGroup), 0.5);\n      dim = mix(0.25, 1.0, match);\n      bright = mix(1.0, 1.25, match);\n    }\n\n    // node-cluster breathing/flash (see vertex shader) plus edge-pulse\n    // overdrive both read purely as brightness, never new geometry \u2014 signals\n    // stay highlights on the parchment, never lasers.\n    float breathBright = 1.0 + (0.10 * vBreath + 0.55 * vFlash) * (1.0 - vIsEdge) * vPhaseAmount;\n    bright *= breathBright;\n    bright += pulseOverdrive * 0.6;\n\n    // Per-particle alpha stays well under 1 (~0.35-0.6) with normal blending\n    // (never additive) so ink tone builds from grain density rather than\n    // flat coverage, and vAlphaVar (a static per-particle hash) keeps that\n    // density organic instead of a uniform wash.\n    float baseAlpha = mix(0.82, 0.6, vIsEdge);\n    float alpha = a * mix(0.96, baseAlpha, vPhaseAmount) * (0.4 + 0.6 * dim) * vAlphaVar;\n    alpha = min(alpha + pulseMix * 0.35 * a, 1.0);\n    gl_FragColor = vec4(col * bright * (0.5 + 0.5 * dim), alpha);\n  }\n";

const SPACING_SAMPLE_TARGET = 3000;
const PALETTE_STRIDE = 8;
const LANG_PAL = { eng: 0, ita: 1, ger: 2, spa: 3, oth: 4, fre: 5 };

function hex01(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

// Explorer language colours, fed into the pragma-cloud palette slots.
const PALETTE = {
  lapis: hex01('#1F5674'),
  gold: hex01('#8A6A12'),
  red: hex01('#A8371F'),
  ochre: hex01('#B15A17'),
  graphite: hex01('#78766F'),
  green: hex01('#4F7350')
};

function hashSeed(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussianPair(rand) {
  let u = 0, v = 0;
  while (u === 0) u = rand();
  while (v === 0) v = rand();
  const mag = Math.sqrt(-2 * Math.log(u));
  return [mag * Math.cos(2 * Math.PI * v), mag * Math.sin(2 * Math.PI * v)];
}

function colOf(grid, x) {
  return Math.min(grid.cols - 1, Math.max(0, Math.floor((x - grid.minX) / grid.cell)));
}
function rowOf(grid, y) {
  return Math.min(grid.rows - 1, Math.max(0, Math.floor((y - grid.minY) / grid.cell)));
}

function buildSpatialGrid(positions, count, stride) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < count; i++) {
    const x = positions[i * stride] || 0;
    const y = positions[i * stride + 1] || 0;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const w = Math.max(maxX - minX, 1e-3);
  const h = Math.max(maxY - minY, 1e-3);
  const cell = Math.max(Math.sqrt((w * h) / count), 1e-3);
  const grid = {
    minX, minY, cell,
    cols: Math.max(1, Math.ceil(w / cell)),
    rows: Math.max(1, Math.ceil(h / cell)),
    buckets: new Map()
  };
  for (let i = 0; i < count; i++) {
    const key = rowOf(grid, positions[i * stride + 1] || 0) * grid.cols + colOf(grid, positions[i * stride] || 0);
    let bucket = grid.buckets.get(key);
    if (!bucket) { bucket = []; grid.buckets.set(key, bucket); }
    bucket.push(i);
  }
  return grid;
}

function scanBucketNearest(bucket, positions, stride, x, y, skip, best) {
  if (!bucket) return best;
  let closest = best;
  for (let b = 0; b < bucket.length; b++) {
    const j = bucket[b];
    if (j === skip) continue;
    const ddx = (positions[j * stride] || 0) - x;
    const ddy = (positions[j * stride + 1] || 0) - y;
    const d2 = ddx * ddx + ddy * ddy;
    if (d2 < closest) closest = d2;
  }
  return closest;
}

function nearestNeighborDistSq(grid, positions, stride, i) {
  const x = positions[i * stride] || 0;
  const y = positions[i * stride + 1] || 0;
  const cx = colOf(grid, x);
  const cy = rowOf(grid, y);
  let best = Infinity;
  for (let dy = -1; dy <= 1; dy++) {
    const ncy = cy + dy;
    if (ncy < 0 || ncy >= grid.rows) continue;
    for (let dx = -1; dx <= 1; dx++) {
      const ncx = cx + dx;
      if (ncx < 0 || ncx >= grid.cols) continue;
      best = scanBucketNearest(grid.buckets.get(ncy * grid.cols + ncx), positions, stride, x, y, i, best);
    }
  }
  return best;
}

function estimateSpacing(positions, count, stride) {
  if (count <= 1) return 1;
  const grid = buildSpatialGrid(positions, count, stride);
  const strideStep = Math.max(1, Math.floor(count / SPACING_SAMPLE_TARGET));
  const samples = [];
  for (let i = 0; i < count; i += strideStep) {
    const d2 = nearestNeighborDistSq(grid, positions, stride, i);
    if (d2 < Infinity) samples.push(Math.sqrt(d2));
  }
  if (samples.length === 0) return grid.cell;
  samples.sort(function (a, b) { return a - b; });
  return samples[Math.floor(samples.length / 2)] || grid.cell;
}

function distribute(weights, total) {
  if (total <= 0 || weights.length === 0) return weights.map(function () { return 0; });
  const sum = weights.reduce(function (s, w) { return s + w; }, 0);
  if (sum <= 0) return weights.map(function () { return 0; });
  const raw = weights.map(function (w) { return (w / sum) * total; });
  const base = raw.map(function (v) { return Math.floor(v); });
  let remainder = total - base.reduce(function (s, v) { return s + v; }, 0);
  const order = raw.map(function (v, i) { return { i: i, frac: v - base[i] }; })
    .sort(function (a, b) { return b.frac - a.frac; });
  const out = base.slice();
  for (let k = 0; k < order.length && remainder > 0; k++) {
    out[order[k].i] += 1;
    remainder--;
  }
  return out;
}

function graphTargets(nodes, count) {
  const positions = new Float32Array(count * 3);
  const colorKey = new Float32Array(count);
  const edgeT = new Float32Array(count);
  const edgePhase = new Float32Array(count);
  const arrivalPhase = new Float32Array(count);
  const nodeOf = new Uint32Array(count);
  const ox = new Float32Array(count);
  const oy = new Float32Array(count);
  if (count <= 0 || nodes.length === 0) {
    return { positions, colorKey, edgeT, edgePhase, arrivalPhase, nodeOf, ox, oy, nodeSpacing: 1 };
  }

  const nodeCounts = distribute(nodes.map(function (n) {
    const w = Math.min(4, Math.max(1, n.weight || 1));
    return w * w;
  }), count);

  const rand = mulberry32(hashSeed('graph:' + count + ':' + nodes.length));
  let cursor = 0;
  nodes.forEach(function (node, ni) {
    const n = nodeCounts[ni] || 0;
    const sigma = node.r / 2.2;
    const pal = LANG_PAL[node.lang] != null ? LANG_PAL[node.lang] : LANG_PAL.oth;
    const key = pal + (ni + 1) * PALETTE_STRIDE;
    let written = 0;
    while (written < n) {
      const pair = gaussianPair(rand);
      const gx = pair[0], gy = pair[1];
      positions[cursor * 3] = node.x + gx * sigma;
      positions[cursor * 3 + 1] = node.y + gy * sigma;
      colorKey[cursor] = key;
      arrivalPhase[cursor] = -1;
      nodeOf[cursor] = ni;
      ox[cursor] = gx * sigma;
      oy[cursor] = gy * sigma;
      cursor++;
      written++;
      if (written >= n) break;
      positions[cursor * 3] = node.x - gx * sigma;
      positions[cursor * 3 + 1] = node.y - gy * sigma;
      colorKey[cursor] = key;
      arrivalPhase[cursor] = -1;
      nodeOf[cursor] = ni;
      ox[cursor] = -gx * sigma;
      oy[cursor] = -gy * sigma;
      cursor++;
      written++;
    }
  });
  while (cursor < count) {
    const src = cursor > 0 ? cursor - 1 : 0;
    positions[cursor * 3] = positions[src * 3] || 0;
    positions[cursor * 3 + 1] = positions[src * 3 + 1] || 0;
    colorKey[cursor] = colorKey[src] || 0;
    arrivalPhase[cursor] = arrivalPhase[src] || 0;
    nodeOf[cursor] = nodeOf[src] || 0;
    ox[cursor] = ox[src] || 0;
    oy[cursor] = oy[src] || 0;
    cursor++;
  }
  const nodeSpacing = estimateSpacing(positions, count, 3);
  return { positions, colorKey, edgeT, edgePhase, arrivalPhase, nodeOf, ox, oy, nodeSpacing };
}

function makeDataTexture(gpuSize) {
  const data = new Float32Array(gpuSize * gpuSize * 4);
  const tex = new THREE.DataTexture(data, gpuSize, gpuSize, THREE.RGBAFormat, THREE.FloatType);
  tex.needsUpdate = true;
  return tex;
}

function fillPositionTexture(tex, positions, count) {
  const d = tex.image.data;
  for (let i = 0; i < count; i++) {
    d[i * 4] = positions[i * 3] || 0;
    d[i * 4 + 1] = positions[i * 3 + 1] || 0;
    d[i * 4 + 2] = positions[i * 3 + 2] || 0;
    d[i * 4 + 3] = 0;
  }
  tex.needsUpdate = true;
}

function fillColorKeyTexture(tex, colorKey, edgeT, edgePhase, arrivalPhase, count) {
  const d = tex.image.data;
  for (let i = 0; i < count; i++) {
    d[i * 4] = colorKey[i] || 0;
    d[i * 4 + 1] = edgeT[i] || 0;
    d[i * 4 + 2] = edgePhase[i] || 0;
    d[i * 4 + 3] = arrivalPhase[i] || 0;
  }
  tex.needsUpdate = true;
}

function seedTextures(dtPos, dtVel, count) {
  const p = dtPos.image.data;
  const v = dtVel.image.data;
  for (let i = 0; i < count; i++) {
    p[i * 4] = 0; p[i * 4 + 1] = 0; p[i * 4 + 2] = 0; p[i * 4 + 3] = Math.random();
    v[i * 4] = 0; v[i * 4 + 1] = 0; v[i * 4 + 2] = 0; v[i * 4 + 3] = 0;
  }
  dtPos.needsUpdate = true;
  dtVel.needsUpdate = true;
}

export function createDustField(canvas, opts) {
  opts = opts || {};
  const isMobile = !!opts.mobile;
  const reduce = !!opts.reduceMotion;
  const GPU_SIZE = isMobile ? 256 : 512;
  const N = GPU_SIZE * GPU_SIZE;

  const renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: false,
    alpha: true,
    powerPreference: 'high-performance'
  });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.NoToneMapping;

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 10);
  camera.position.z = 1;

  const gpu = new GPUComputationRenderer(GPU_SIZE, GPU_SIZE, renderer);
  gpu.setDataType(isMobile ? THREE.HalfFloatType : THREE.FloatType);

  const dtPos = gpu.createTexture();
  const dtVel = gpu.createTexture();
  seedTextures(dtPos, dtVel, N);

  const velVar = gpu.addVariable('uTextureVelocity', velocityFragmentShader, dtVel);
  const posVar = gpu.addVariable('uTexturePosition', positionFragmentShader, dtPos);
  gpu.setVariableDependencies(velVar, [velVar, posVar]);
  gpu.setVariableDependencies(posVar, [velVar, posVar]);

  const graphTex = makeDataTexture(GPU_SIZE);
  const colorKeyTex = makeDataTexture(GPU_SIZE);

  const dpr0 = Math.min(window.devicePixelRatio || 1, 2);
  const u = {
    uTargetA: { value: graphTex },
    uTargetB: { value: graphTex },
    uTargetMix: { value: 1 },
    uAssembled: { value: 1 },
    uTime: { value: 0 },
    uSimDelta: { value: 0.016 },
    uNoiseFreq: { value: 0.006 },
    uNoiseAmp: { value: 55 },
    uSpring: { value: 0.12 },
    uDamping: { value: 0.92 },
    uMaxSpeed: { value: 900 },
    uTransit: { value: 30 },
    uPointer: { value: new THREE.Vector2(0, 0) },
    uPointerPrev: { value: new THREE.Vector2(0, 0) },
    uPointerActive: { value: 0 },
    uPointerRadius: { value: 55 },
    uPointerAmp: { value: 150 },
    uPointerSwirl: { value: 80 },
    uPosDelta: { value: 0.016 },
    uTexturePosition: { value: null },
    uTextureVelocity: { value: null },
    uColorKeyTex: { value: colorKeyTex },
    uSpacingA: { value: 1 },
    uSpacingB: { value: 1 },
    uEdgeSpacingA: { value: 1 },
    uEdgeSpacingB: { value: 1 },
    uSizeFactor: { value: 2.0 },
    uEdgeSizeFactor: { value: 1.35 },
    uDPR: { value: dpr0 },
    uZoom: { value: 1 },
    uCX: { value: 0 },
    uCY: { value: 0 },
    uViewportW: { value: 1 },
    uViewportH: { value: 1 },
    uRenderTargetMix: { value: 1 },
    uPhaseA: { value: 1 },
    uPhaseB: { value: 1 },
    uInk: { value: new THREE.Color(PALETTE.lapis[0], PALETTE.lapis[1], PALETTE.lapis[2]) },
    uLapis: { value: new THREE.Color(PALETTE.lapis[0], PALETTE.lapis[1], PALETTE.lapis[2]) },
    uGold: { value: new THREE.Color(PALETTE.gold[0], PALETTE.gold[1], PALETTE.gold[2]) },
    uRed: { value: new THREE.Color(PALETTE.red[0], PALETTE.red[1], PALETTE.red[2]) },
    uOchre: { value: new THREE.Color(PALETTE.ochre[0], PALETTE.ochre[1], PALETTE.ochre[2]) },
    uGraphite: { value: new THREE.Color(PALETTE.graphite[0], PALETTE.graphite[1], PALETTE.graphite[2]) },
    uGreen: { value: new THREE.Color(PALETTE.green[0], PALETTE.green[1], PALETTE.green[2]) },
    uFocusGroup: { value: -999 },
    uHasFocus: { value: 0 },
    uHubGroup: { value: -999 }
  };

  Object.assign(velVar.material.uniforms, {
    uTargetA: u.uTargetA,
    uTargetB: u.uTargetB,
    uTargetMix: u.uTargetMix,
    uAssembled: u.uAssembled,
    uTime: u.uTime,
    uDelta: u.uSimDelta,
    uNoiseFreq: u.uNoiseFreq,
    uNoiseAmp: u.uNoiseAmp,
    uSpring: u.uSpring,
    uDamping: u.uDamping,
    uMaxSpeed: u.uMaxSpeed,
    uTransit: u.uTransit,
    uPointer: u.uPointer,
    uPointerPrev: u.uPointerPrev,
    uPointerActive: u.uPointerActive,
    uPointerRadius: u.uPointerRadius,
    uPointerAmp: u.uPointerAmp,
    uPointerSwirl: u.uPointerSwirl
  });
  Object.assign(posVar.material.uniforms, { uDelta: u.uPosDelta });

  const initError = gpu.init();
  if (initError !== null) {
    gpu.dispose();
    graphTex.dispose();
    colorKeyTex.dispose();
    renderer.dispose();
    throw new Error('dust-field: GPUComputationRenderer init failed: ' + initError);
  }

  const geo = new THREE.BufferGeometry();
  const uvs = new Float32Array(N * 2);
  for (let i = 0; i < N; i++) {
    const x = i % GPU_SIZE;
    const y = Math.floor(i / GPU_SIZE);
    uvs[i * 2] = (x + 0.5) / GPU_SIZE;
    uvs[i * 2 + 1] = (y + 0.5) / GPU_SIZE;
  }
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  geo.setAttribute('aParticlesUv', new THREE.BufferAttribute(uvs, 2));
  geo.setDrawRange(0, 0);

  const renderMat = new THREE.ShaderMaterial({
    depthWrite: false,
    depthTest: false,
    transparent: true,
    blending: THREE.NormalBlending,
    uniforms: {
      uTexturePosition: u.uTexturePosition,
      uTextureVelocity: u.uTextureVelocity,
      uColorKeyTex: u.uColorKeyTex,
      uSpacingA: u.uSpacingA,
      uSpacingB: u.uSpacingB,
      uEdgeSpacingA: u.uEdgeSpacingA,
      uEdgeSpacingB: u.uEdgeSpacingB,
      uSizeFactor: u.uSizeFactor,
      uEdgeSizeFactor: u.uEdgeSizeFactor,
      uDPR: u.uDPR,
      uZoom: u.uZoom,
      uCX: u.uCX,
      uCY: u.uCY,
      uViewportW: u.uViewportW,
      uViewportH: u.uViewportH,
      uTargetMix: u.uRenderTargetMix,
      uPhaseA: u.uPhaseA,
      uPhaseB: u.uPhaseB,
      uInk: u.uInk,
      uLapis: u.uLapis,
      uGold: u.uGold,
      uRed: u.uRed,
      uOchre: u.uOchre,
      uGraphite: u.uGraphite,
      uGreen: u.uGreen,
      uFocusGroup: u.uFocusGroup,
      uHasFocus: u.uHasFocus,
      uTime: u.uTime,
      uHubGroup: u.uHubGroup,
      uAssembled: u.uAssembled
    },
    vertexShader: particleVertexShader,
    fragmentShader: particleFragmentShader
  });
  const points = new THREE.Points(geo, renderMat);
  points.frustumCulled = false;
  scene.add(points);

  let disposed = false;
  let lastNodes = [];
  let lastIds = '';
  let sampled = null;
  const nodeIndexById = new Map();

  function resize(w, h) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
    u.uViewportW.value = w;
    u.uViewportH.value = h;
    u.uDPR.value = dpr;
  }

  function stampHomes(positions) {
    fillPositionTexture(graphTex, positions, N);
    gpu.renderTexture(graphTex, gpu.getCurrentRenderTarget(posVar));
    gpu.renderTexture(graphTex, gpu.getAlternateRenderTarget(posVar));
  }

  function setNodes(nodes) {
    lastNodes = nodes;
    lastIds = nodes.map(function (n) { return n.id; }).join('\0');
    nodeIndexById.clear();
    nodes.forEach(function (n, i) { nodeIndexById.set(n.id, i); });
    sampled = graphTargets(nodes, N);
    fillColorKeyTexture(colorKeyTex, sampled.colorKey, sampled.edgeT, sampled.edgePhase, sampled.arrivalPhase, N);
    stampHomes(sampled.positions);
    u.uSpacingA.value = sampled.nodeSpacing;
    u.uSpacingB.value = sampled.nodeSpacing;
    u.uEdgeSpacingA.value = sampled.nodeSpacing;
    u.uEdgeSpacingB.value = sampled.nodeSpacing;
    u.uTargetA.value = graphTex;
    u.uTargetB.value = graphTex;
    geo.setDrawRange(0, nodes.length ? N : 0);
  }

  function moveNodes(nodes) {
    if (!sampled || nodes.length !== lastNodes.length) {
      setNodes(nodes);
      return;
    }
    const ids = nodes.map(function (n) { return n.id; }).join('\0');
    if (ids !== lastIds) {
      setNodes(nodes);
      return;
    }
    lastNodes = nodes;
    const positions = sampled.positions;
    for (let i = 0; i < N; i++) {
      const ni = sampled.nodeOf[i];
      const node = nodes[ni];
      if (!node) continue;
      positions[i * 3] = node.x + sampled.ox[i];
      positions[i * 3 + 1] = node.y + sampled.oy[i];
    }
    fillPositionTexture(graphTex, positions, N);
    u.uTargetA.value = graphTex;
    u.uTargetB.value = graphTex;
  }

  function syncCamera(cam, w, h) {
    const s = cam.s || 1;
    u.uZoom.value = s;
    u.uCX.value = (w / 2 - cam.x) / s;
    u.uCY.value = (h / 2 - cam.y) / s;
    u.uViewportW.value = w;
    u.uViewportH.value = h;
  }

  function setPointer() { /* explorer does not part the dust under the cursor */ }

  function focus(id) {
    const idx = id == null ? undefined : nodeIndexById.get(String(id));
    if (idx === undefined) {
      u.uHasFocus.value = 0;
      return;
    }
    u.uHasFocus.value = 1;
    u.uFocusGroup.value = idx;
  }

  let rafId = 0;
  let lastT = performance.now();
  let elapsed = 0;

  function tick(now) {
    if (disposed) return;
    rafId = requestAnimationFrame(tick);
    const delta = Math.min((now - lastT) / 1000, 0.05);
    lastT = now;
    if (!reduce) elapsed += delta;
    u.uTime.value = elapsed;
    u.uSimDelta.value = delta;
    u.uPosDelta.value = delta;
    u.uPointerActive.value = 0;
    if (reduce) {
      u.uAssembled.value = 1;
    } else {
      const settleK = 1 - Math.pow(1 - 0.08, delta * 60);
      u.uAssembled.value += (1 - u.uAssembled.value) * settleK;
    }
    gpu.compute();
    u.uTexturePosition.value = gpu.getCurrentRenderTarget(posVar).texture;
    u.uTextureVelocity.value = gpu.getCurrentRenderTarget(velVar).texture;
    u.uRenderTargetMix.value = 1;
    renderer.render(scene, camera);
  }
  rafId = requestAnimationFrame(tick);

  function dispose() {
    disposed = true;
    cancelAnimationFrame(rafId);
    gpu.dispose();
    geo.dispose();
    renderMat.dispose();
    graphTex.dispose();
    colorKeyTex.dispose();
    renderer.dispose();
  }

  return {
    ok: true,
    resize: resize,
    setNodes: setNodes,
    moveNodes: moveNodes,
    syncCamera: syncCamera,
    setPointer: setPointer,
    focus: focus,
    dispose: dispose
  };
}
