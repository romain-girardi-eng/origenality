/* Origenality landing — Particle Image, adapted from React Bits Pro (licensed
   copy) to vanilla Three.js. The simulation is the original one: a flow field
   over a GPU ping-pong, the same uniforms, the same defaults.

   What is added, and why:
     - `focus`     aim the cover crop at the face instead of the centre;
     - `grade`     one colour grade (black point, contrast, split tone, ACES)
                   shared by the picture and the dust, so both are made of the
                   same light;
     - `trace`     a small force up the luminance gradient, and a tint read at
                   the particle's own position: the dust follows the features
                   of the portrait instead of drifting past them;
     - `toGraph()` the departure. Every particle is given a place in a
                   constellation of clusters and filaments and eases into it,
                   losing the picture's colour on the way. The Explorer picks
                   the thought up from there.

   Romain Girardi, 2026. */
import * as THREE from './vendor/three.module.min.js';

const GLSL_HASH = `
#define HASH_SCALE vec3(0.1031, 0.11369, 0.13787)
vec3 hash33(vec3 p) {
  p = fract(p * HASH_SCALE);
  p += dot(p, p.yxz + 19.19);
  return -1.0 + 2.0 * fract(vec3((p.x + p.y) * p.z, (p.x + p.z) * p.y, (p.y + p.z) * p.x));
}
`;

const GLSL_NOISE = `
float flowNoise(vec3 p) {
  const float K1 = 0.333333333;
  const float K2 = 0.166666667;
  vec3 cell = floor(p + (p.x + p.y + p.z) * K1);
  vec3 d0 = p - (cell - (cell.x + cell.y + cell.z) * K2);
  vec3 edge = step(vec3(0.0), d0 - d0.yzx);
  vec3 o1 = edge * (1.0 - edge.zxy);
  vec3 o2 = 1.0 - edge.zxy * (1.0 - edge);
  vec3 d1 = d0 - (o1 - K2);
  vec3 d2 = d0 - (o2 - 2.0 * K2);
  vec3 d3 = d0 - (1.0 - 3.0 * K2);
  vec4 falloff = max(0.6 - vec4(dot(d0, d0), dot(d1, d1), dot(d2, d2), dot(d3, d3)), 0.0);
  vec4 weights = falloff * falloff * falloff * falloff * vec4(
    dot(d0, hash33(cell)),
    dot(d1, hash33(cell + o1)),
    dot(d2, hash33(cell + o2)),
    dot(d3, hash33(cell + 1.0))
  );
  return dot(vec4(31.316), weights);
}
`;

/* how the picture is laid into the frame: cover or contain, an aim point
   instead of the centre, and a zoom. Framing only — nothing here touches how
   the dust behaves. */
const GLSL_COVER = `
uniform vec2 uFocus;
uniform float uFit;    // 0 cover, 1 contain
uniform float uZoom;
vec2 coverUv(vec2 uv, float frameAspect, float imageAspect) {
  float r = imageAspect / frameAspect;
  vec2 letterbox = vec2(1.0 / r, 1.0);   // bars left and right
  vec2 pillarbox = vec2(1.0, r);         // bars top and bottom
  vec2 span = mix(
    r > 1.0 ? letterbox : pillarbox,     // cover: the long side is cropped
    r > 1.0 ? pillarbox : letterbox,     // contain: the short side is let out
    uFit
  ) / max(uZoom, 0.01);
  vec2 lo = min(span * 0.5, 1.0 - span * 0.5);
  vec2 hi = max(span * 0.5, 1.0 - span * 0.5);
  return (uv - 0.5) * span + clamp(uFocus, lo, hi);
}
`;

/* one grade, shared by the picture and the dust */
const GLSL_GRADE = `
uniform float uBlackPoint;
uniform float uContrast;
uniform float uExposure;
uniform float uSaturation;
uniform vec3 uShadowTint;
uniform vec3 uHighlightTint;

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

vec3 aces(vec3 x) {
  const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

vec3 grade(vec3 c) {
#ifdef GRADED
  c = max(c - uBlackPoint, 0.0) / max(1.0 - uBlackPoint, 0.001);
  c = (c - 0.5) * uContrast + 0.5;
  c = max(c, 0.0);
  float l = luma(c);
  c = mix(vec3(l), c, uSaturation);
  c *= mix(uShadowTint, uHighlightTint, smoothstep(0.05, 0.70, l));
  return aces(c * uExposure);
#else
  return c;
#endif
}
`;

const QUAD_VERT = `precision highp float;
in vec3 position;
in vec2 uv;
out vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 1.0);
}`;

/* Where a grain is born decides everything: it carries the colour of that
   pixel for its whole life. Born on a smooth plane it lands on its own value
   and is invisible; born on an edge it shows. So the birth site is drawn
   towards the carving — five candidates, the one standing on the steepest
   slope wins. uEdgeAffinity 0 restores the original's even scatter. */
const GLSL_EDGE = `
uniform sampler2D uImage;
uniform float uImageAspect;
uniform float uEdgeAffinity;

float lumaAt(vec2 uv, float frameAspect) {
  vec3 c = texture(uImage, coverUv(clamp(uv, 0.0, 1.0), frameAspect, uImageAspect)).rgb;
  return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

float edgeAt(vec2 pos, vec2 res) {
  float frameAspect = res.x / res.y;
  vec2 uv = pos / res;
  vec2 d = 2.5 / res;
  float gx = lumaAt(uv + vec2(d.x, 0.0), frameAspect) - lumaAt(uv - vec2(d.x, 0.0), frameAspect);
  float gy = lumaAt(uv + vec2(0.0, d.y), frameAspect) - lumaAt(uv - vec2(0.0, d.y), frameAspect);
  return length(vec2(gx, gy));
}

vec2 birthSite(vec2 seed, float salt, vec2 res) {
  vec2 best = fract(hash33(vec3(seed, salt)).xy * 0.5 + 0.5) * res;
  if (uEdgeAffinity <= 0.0) return best;
  float score = -1.0;
  for (int i = 0; i < 20; i++) {
    vec3 r = hash33(vec3(seed * (11.3 + float(i) * 2.7), salt + float(i) * 5.1));
    vec2 cand = fract(r.xy * 0.5 + 0.5) * res;
    float w = pow(clamp(edgeAt(cand, res) * 7.0, 0.0, 1.0), uEdgeAffinity)
            * (0.55 + 0.45 * fract(r.z * 0.5 + 0.5));
    if (w > score) { score = w; best = cand; }
  }
  return best;
}
`;

const SEED_FRAG = `precision highp float;
uniform vec2 uResolution;
uniform float uLifespan;
in vec2 vUv;
layout(location = 0) out vec4 outMotion;
layout(location = 1) out vec4 outLife;
${GLSL_HASH}
${GLSL_COVER}
${GLSL_EDGE}
void main() {
  vec3 jitter = hash33(vec3(vUv * 91.7, 7.3));
  vec2 origin = birthSite(vUv * 512.0, 1.0, uResolution);
  float span = uLifespan * (0.25 + 0.75 * fract(jitter.z * 0.5 + 0.5));
  outMotion = vec4(origin, jitter.xy * 0.25);
  outLife = vec4(fract(jitter.x * 0.5 + 0.5) * span, span, origin / uResolution);
}`;

const SIM_FRAG = `precision highp float;
uniform sampler2D tMotion;
uniform sampler2D tLife;
uniform sampler2D tTarget;
uniform vec2 uResolution;
uniform vec2 uPointer;
uniform vec2 uPointerVelocity;
uniform float uTime;
uniform float uNoiseScale;
uniform float uNoiseStrength;
uniform float uDamping;
uniform float uLifespan;
uniform float uPointerStrength;
uniform float uPointerFalloff;
uniform float uTrace;
uniform float uCling;
uniform float uAlong;
uniform float uEdgeFloor;
uniform float uMorph;
in vec2 vUv;
layout(location = 0) out vec4 outMotion;
layout(location = 1) out vec4 outLife;
${GLSL_HASH}
${GLSL_NOISE}
${GLSL_COVER}
${GLSL_EDGE}

float lightAt(vec2 p) {
  return lumaAt(p / uResolution, uResolution.x / uResolution.y);
}

void main() {
  vec4 motion = texture(tMotion, vUv);
  vec4 life = texture(tLife, vUv);
  vec2 pos = motion.xy;
  vec2 vel = motion.zw;
  float age = life.x + 1.0;
  float span = life.y;
  vec2 birth = life.zw;

  float uSide = fract(sin(dot(vUv, vec2(41.7, 289.1))) * 43758.5453) < 0.5 ? -1.0 : 1.0;

  float angle = flowNoise(vec3(pos * uNoiseScale, uTime * 20.0 + age * 0.05)) * 6.2831853;
  vec2 flow = vec2(cos(angle), sin(angle)) * uNoiseStrength;

  vec2 e = vec2(2.5, 0.0);
  vec2 slope = vec2(
    lightAt(pos + e.xy) - lightAt(pos - e.xy),
    lightAt(pos + e.yx) - lightAt(pos - e.yx)
  );
  /* clamped: a hard edge between stone and black is a cliff in this field, and
     an unbounded pull off it would fling grains across the frame */
  vec2 trace = clamp(slope * uTrace, vec2(-0.35), vec2(0.35)) * (1.0 - uMorph);

  vec2 offset = pos - uPointer;
  float proximity = uPointerFalloff / (dot(offset, offset) + uPointerFalloff);
  vec2 wake = uPointerVelocity * proximity * uPointerStrength * (1.0 - uMorph);

  vel = vel * uDamping + flow * (1.0 - uMorph * 0.85) + trace + wake;
  pos += vel;

  /* A grain belongs to ONE contour of the picture: the level of luminance it
     was born on. After it has moved, it is put back on that contour and slid
     a little way along it.

     This is a CONSTRAINT on the position, never a force on the velocity — a
     bounded acceleration under 0.98 damping still compounds fifty-fold, which
     is how a nudge turns into a grain crossing the frame every frame.

       cling  a Newton step back onto the level set: the grain sits exactly on
              the crease, the ridge of a curl, the line of the brow;
       along  a slide down the iso-line, perpendicular to the gradient, so the
              grain travels ALONG the feature instead of across it.

     Below uEdgeFloor there is no contour worth holding — flat stone, or the
     black ground — and the grain is left to drift as it always did. Both are
     zero by default, which is the original's behaviour. */
  float gm2 = dot(slope, slope);
  if ((uCling > 0.0 || uAlong > 0.0) && gm2 > uEdgeFloor * uEdgeFloor) {
    float level = lumaAt(birth, uResolution.x / uResolution.y);
    vec2 snap = -slope * ((lightAt(pos) - level) / gm2) * uCling;
    vec2 slide = vec2(-slope.y, slope.x) * inversesqrt(gm2) * uAlong * uSide;
    pos += clamp(snap + slide, vec2(-3.0), vec2(3.0)) * (1.0 - uMorph);
  }

  /* the departure: each particle eases into its place on its own beat, so the
     constellation assembles rather than snaps */
  if (uMorph > 0.0) {
    vec4 target = texture(tTarget, vUv);
    float beat = smoothstep(target.w * 0.5, target.w * 0.5 + 0.5, uMorph);
    beat = beat * beat * (3.0 - 2.0 * beat);
    pos = mix(pos, target.xy, beat * 0.16);
    vel *= mix(1.0, 0.82, beat);
  }

  bool loose = age >= span
    || pos.x < 0.0 || pos.x > uResolution.x
    || pos.y < 0.0 || pos.y > uResolution.y;

  if (loose && uMorph < 0.02) {
    vec2 fresh = birthSite(birth * 97.3 + vUv, uTime + age, uResolution);
    vec3 r = hash33(vec3(fresh * 0.01, uTime + age));
    float nextSpan = uLifespan * (0.25 + 0.75 * fract(r.z * 0.5 + 0.5));
    outMotion = vec4(fresh, 0.0, 0.0);
    outLife = vec4(0.0, nextSpan, fresh / uResolution);
  } else {
    outMotion = vec4(pos, vel);
    outLife = vec4(age, span, birth);
  }
}`;

const POINT_VERT = `precision highp float;
in vec3 position;
uniform sampler2D tMotion;
uniform sampler2D tLife;
uniform sampler2D tTarget;
uniform sampler2D uImage;
uniform vec2 uResolution;
uniform vec2 uKey;
uniform vec2 uVignetteShape;
uniform float uImageAspect;
uniform float uPointSize;
uniform float uOpacity;
uniform float uVignette;
uniform float uTintGain;
uniform float uTraceTint;
uniform float uMorph;
uniform vec3 uGraphTint;
out vec3 vTint;
out float vAlpha;
${GLSL_HASH}
${GLSL_COVER}
${GLSL_GRADE}
void main() {
  vec4 motion = texture(tMotion, position.xy);
  vec4 life = texture(tLife, position.xy);
  float ratio = life.x / max(life.y, 1.0);
  float fade = smoothstep(0.0, 0.05, ratio) * (1.0 - smoothstep(0.85, 1.0, ratio));
  fade = mix(fade, 1.0, uMorph);

  vec2 birthUv = life.zw;
  vec2 hereUv = clamp(motion.xy / uResolution, 0.0, 1.0);
  vec2 readUv = mix(birthUv, hereUv, uTraceTint);
  float frameAspect = uResolution.x / uResolution.y;

  vec3 lit = grade(texture(uImage, coverUv(readUv, frameAspect, uImageAspect)).rgb);
  lit = min(lit * uTintGain, vec3(1.0));

  vec2 key = (birthUv - uKey) * uVignetteShape;
  float vign = 1.0 - uVignette * smoothstep(0.10, 0.62, length(key));
  vign = mix(vign, 1.0, uMorph);

  /* on the way to the graph the dust forgets the picture and keeps the ink */
  vec3 jitter = hash33(vec3(position.xy * 421.0, 5.7));
  float shade = 0.72 + 0.42 * fract(jitter.x * 0.5 + 0.5);
  vTint = mix(lit, uGraphTint * shade, smoothstep(0.10, 0.72, uMorph));

  float kind = texture(tTarget, position.xy).z;   // 0 node, 1 filament
  vAlpha = fade * uOpacity * vign * mix(1.0, mix(1.7, 0.62, kind), uMorph);

  vec2 ndc = motion.xy / uResolution * 2.0 - 1.0;
  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
  float size = smoothstep(1.0, 0.5, ratio) * uPointSize * fade;
  gl_PointSize = mix(size, uPointSize * mix(0.62, 0.34, kind), uMorph);
}`;

const POINT_FRAG = `precision highp float;
in vec3 vTint;
in float vAlpha;
out vec4 fragColor;
void main() {
  float mask = 1.0 - smoothstep(0.3, 0.5, length(gl_PointCoord - 0.5));
  fragColor = vec4(vTint, vAlpha * mask);
}`;

const IMAGE_FRAG = `precision highp float;
uniform sampler2D uImage;
uniform vec2 uKey;
uniform vec2 uVignetteShape;
uniform float uFrameAspect;
uniform float uImageAspect;
uniform float uOpacity;
uniform float uVignette;
in vec2 vUv;
out vec4 fragColor;
${GLSL_COVER}
${GLSL_GRADE}
void main() {
  vec2 uv = vec2(vUv.x, 1.0 - vUv.y);
  vec3 c = grade(texture(uImage, coverUv(uv, uFrameAspect, uImageAspect)).rgb);
  vec2 key = (uv - uKey) * uVignetteShape;
  float vign = 1.0 - uVignette * smoothstep(0.10, 0.62, length(key));
  fragColor = vec4(c * vign, uOpacity);
}`;

const OFFSCREEN = -100000;

function gridFor(count) {
  return Math.min(1024, Math.max(64, Math.ceil(Math.sqrt(Math.max(count, 1)))));
}

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* A constellation with the Explorer's grammar: weighted clusters of dots, a
   hub, and filaments running between them. Deterministic, so it does not
   reshuffle on a resize. */
function graphTargets(grid, width, height, cfg) {
  var total = grid * grid;
  var data = new Float32Array(total * 4);
  var rand = mulberry32(0x0e1a3f5b);
  var count = cfg.clusters;
  var cx = width * 0.5;
  var cy = height * 0.5;
  var unit = Math.min(width, height);
  var nodes = [];
  var i, k;

  function gauss() {
    var u = 1 - rand(), v = rand();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  /* golden-angle placement: clusters spread without clumping, and the
     ellipse is wide so the constellation uses the whole frame */
  var golden = Math.PI * (3 - Math.sqrt(5));
  for (i = 0; i < count; i++) {
    var a = i * golden;
    var rr = Math.sqrt((i + 0.6) / count);
    nodes.push({
      x: cx + Math.cos(a) * rr * width * 0.40,
      y: cy + Math.sin(a) * rr * height * 0.36,
      r: unit * (0.016 + 0.026 * rand()),
      w: 0.30 + rand()
    });
  }
  var hub = nodes.length;
  nodes.push({ x: cx, y: cy, r: unit * 0.048, w: 2.2 });

  var edges = [];
  for (i = 0; i < count; i++) edges.push([hub, i]);
  for (i = 0; i < count; i += 2) edges.push([i, (i + 3) % count]);

  var nodeSlots = Math.floor(total * (1 - cfg.filamentShare));
  var weight = 0;
  for (i = 0; i < nodes.length; i++) weight += nodes[i].w;

  var cursor = 0;
  for (k = 0; k < nodes.length; k++) {
    var node = nodes[k];
    var slots = k === nodes.length - 1
      ? nodeSlots - cursor
      : Math.round(nodeSlots * node.w / weight);
    var sigma = node.r * 0.46;
    for (i = 0; i < slots && cursor < nodeSlots; i++, cursor++) {
      data[cursor * 4] = node.x + gauss() * sigma;
      data[cursor * 4 + 1] = node.y + gauss() * sigma;
      data[cursor * 4 + 2] = 0;
      data[cursor * 4 + 3] = rand();
    }
  }

  var spread = Math.max(unit * 0.0016, 1);
  for (; cursor < total; cursor++) {
    var edge = edges[Math.floor(rand() * edges.length)];
    var a0 = nodes[edge[0]], b0 = nodes[edge[1]];
    var u = rand();
    var bow = (rand() - 0.5) * 0.14;
    var mx = (a0.x + b0.x) * 0.5 - (b0.y - a0.y) * bow;
    var my = (a0.y + b0.y) * 0.5 + (b0.x - a0.x) * bow;
    var iv = 1 - u;
    data[cursor * 4] = iv * iv * a0.x + 2 * iv * u * mx + u * u * b0.x + gauss() * spread;
    data[cursor * 4 + 1] = iv * iv * a0.y + 2 * iv * u * my + u * u * b0.y + gauss() * spread;
    data[cursor * 4 + 2] = 1;
    data[cursor * 4 + 3] = rand();
  }

  return data;
}

function loadTexture(url) {
  return new Promise(function (resolve, reject) {
    var loader = new THREE.TextureLoader();
    loader.setCrossOrigin('anonymous');
    loader.load(url, function (texture) {
      var img = texture.image;
      var w = img.naturalWidth || img.width || 1;
      var h = img.naturalHeight || img.height || 1;
      texture.flipY = false;
      texture.generateMipmaps = false;
      texture.minFilter = THREE.LinearFilter;
      texture.magFilter = THREE.LinearFilter;
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
      texture.needsUpdate = true;
      resolve({ texture: texture, aspect: w / Math.max(h, 1) });
    }, undefined, reject);
  });
}

function pick(v, fallback) { return v == null ? fallback : v; }

export function mountParticleImage(root, opt) {
  opt = opt || {};
  var imageUrl = opt.imageUrl;
  if (!root || !imageUrl) return null;

  var particleCount = opt.particleCount || 250000;
  var particleSize = pick(opt.particleSize, 2);
  var particleOpacity = pick(opt.particleOpacity, 0.5);
  var speed = pick(opt.speed, 1);
  var noiseScale = pick(opt.noiseScale, 0.004);
  var noiseStrength = pick(opt.noiseStrength, 0.04);
  var damping = pick(opt.damping, 0.98);
  var lifespan = pick(opt.lifespan, 400);
  var showImage = opt.showImage !== false;
  var imageOpacity = pick(opt.imageOpacity, 1);
  var cursorInteraction = opt.cursorInteraction !== false;
  var cursorStrength = pick(opt.cursorStrength, 0.08);
  var cursorRadius = pick(opt.cursorRadius, 90);
  var dprCap = pick(opt.dpr, 2);
  var focus = opt.focus || [0.5, 0.5];
  var fit = opt.fit === 'contain' ? 1 : 0;
  var zoom = pick(opt.zoom, 1);
  var keyPoint = opt.keyPoint || [0.5, 0.5];
  var vignette = pick(opt.vignette, 0);
  var vignetteShape = opt.vignetteShape || [1, 0.82];
  var tintGain = pick(opt.tintGain, 1);
  var trace = pick(opt.trace, 0);
  var edgeAffinity = pick(opt.edgeAffinity, 0);
  var cling = pick(opt.cling, 0);
  var along = pick(opt.along, 0);
  var edgeFloor = pick(opt.edgeFloor, 0.035);
  var traceTint = pick(opt.traceTint, 0);
  var fadeInMs = pick(opt.fadeInMs, 900);
  var graphTint = opt.graphTint || [0.95, 0.94, 0.90];
  var graphCfg = Object.assign({ clusters: 11, filamentShare: 0.20 }, opt.graph || {});
  var onLive = opt.onLive;

  var grade = opt.grade || null;
  var graded = !!grade;
  var gradeDefines = graded ? { GRADED: '' } : {};
  grade = grade || {};
  var blackPoint = pick(grade.blackPoint, 0);
  var contrast = pick(grade.contrast, 1);
  var exposure = pick(grade.exposure, 1);
  var saturation = pick(grade.saturation, 1);
  var shadowTint = grade.shadowTint || [1, 1, 1];
  var highlightTint = grade.highlightTint || [1, 1, 1];

  var canvas = document.createElement('canvas');
  canvas.className = 'particle-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  root.appendChild(canvas);

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: false,
      alpha: true,
      depth: false,
      powerPreference: 'high-performance'
    });
  } catch (err) {
    root.removeChild(canvas);
    return null;
  }
  if (!renderer.capabilities.isWebGL2) {
    renderer.dispose();
    root.removeChild(canvas);
    return null;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, dprCap));
  renderer.setClearColor(0x000000, 0);
  renderer.autoClear = false;

  var scene = new THREE.Scene();
  var camera = new THREE.Camera();
  var simScene = new THREE.Scene();
  var simCamera = new THREE.Camera();
  var frame = new THREE.Vector2(1, 1);
  var clock = { time: 0, elapsed: 0 };
  var pointer = {
    targetX: OFFSCREEN, targetY: OFFSCREEN,
    lastX: OFFSCREEN, lastY: OFFSCREEN,
    velocityX: 0, velocityY: 0, engaged: false
  };
  var grid = gridFor(particleCount);
  var targetTexture = new THREE.DataTexture(
    new Float32Array(grid * grid * 4), grid, grid, THREE.RGBAFormat, THREE.FloatType
  );
  targetTexture.minFilter = THREE.NearestFilter;
  targetTexture.magFilter = THREE.NearestFilter;
  targetTexture.needsUpdate = true;
  var targetSize = { w: 0, h: 0 };

  var sim = null;
  var source = null;
  var running = true;
  var inView = true;
  var live = false;
  var raf = 0;
  var morph = 0;

  function opticsUniforms() {
    return {
      uFocus: { value: new THREE.Vector2(focus[0], focus[1]) },
      uFit: { value: fit },
      uZoom: { value: zoom },
      uKey: { value: new THREE.Vector2(keyPoint[0], keyPoint[1]) },
      uVignette: { value: vignette },
      uVignetteShape: { value: new THREE.Vector2(vignetteShape[0], vignetteShape[1]) },
      uBlackPoint: { value: blackPoint },
      uContrast: { value: contrast },
      uExposure: { value: exposure },
      uSaturation: { value: saturation },
      uShadowTint: { value: new THREE.Vector3().fromArray(shadowTint) },
      uHighlightTint: { value: new THREE.Vector3().fromArray(highlightTint) }
    };
  }

  var pointMaterial = new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: POINT_VERT,
    defines: gradeDefines,
    fragmentShader: POINT_FRAG,
    uniforms: Object.assign({
      tMotion: { value: null },
      tLife: { value: null },
      tTarget: { value: targetTexture },
      uImage: { value: null },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uImageAspect: { value: 1 },
      uPointSize: { value: 4 },
      uOpacity: { value: particleOpacity },
      uTintGain: { value: tintGain },
      uTraceTint: { value: traceTint },
      uMorph: { value: 0 },
      uGraphTint: { value: new THREE.Vector3().fromArray(graphTint) }
    }, opticsUniforms()),
    transparent: true,
    depthTest: false,
    depthWrite: false,
    blending: THREE.NormalBlending
  });

  var backdropMaterial = new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: QUAD_VERT,
    defines: gradeDefines,
    fragmentShader: IMAGE_FRAG,
    uniforms: Object.assign({
      uImage: { value: null },
      uFrameAspect: { value: 1 },
      uImageAspect: { value: 1 },
      uOpacity: { value: imageOpacity }
    }, opticsUniforms()),
    transparent: true,
    depthTest: false,
    depthWrite: false
  });

  var backdrop = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), backdropMaterial);
  backdrop.frustumCulled = false;
  backdrop.renderOrder = -1;
  backdrop.visible = showImage;
  scene.add(backdrop);

  function buildSim() {
    var gl = renderer.getContext();
    var floatCapable = gl.getExtension('EXT_color_buffer_float') !== null;
    var dataType = floatCapable ? THREE.FloatType : THREE.HalfFloatType;
    function makeBuffer() {
      return new THREE.WebGLRenderTarget(grid, grid, {
        count: 2,
        type: dataType,
        format: THREE.RGBAFormat,
        minFilter: THREE.NearestFilter,
        magFilter: THREE.NearestFilter,
        wrapS: THREE.ClampToEdgeWrapping,
        wrapT: THREE.ClampToEdgeWrapping,
        depthBuffer: false,
        stencilBuffer: false,
        generateMipmaps: false
      });
    }
    var buffers = [makeBuffer(), makeBuffer()];

    var seedMaterial = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: QUAD_VERT,
      fragmentShader: SEED_FRAG,
      uniforms: {
        uResolution: { value: new THREE.Vector2(1, 1) },
        uLifespan: { value: lifespan },
        uImage: { value: null },
        uImageAspect: { value: 1 },
        uEdgeAffinity: { value: edgeAffinity },
        uFocus: { value: new THREE.Vector2(focus[0], focus[1]) },
        uFit: { value: fit },
        uZoom: { value: zoom }
      },
      depthTest: false,
      depthWrite: false
    });

    var stepMaterial = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: QUAD_VERT,
      fragmentShader: SIM_FRAG,
      uniforms: {
        tMotion: { value: null },
        tLife: { value: null },
        tTarget: { value: targetTexture },
        uImage: { value: null },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uPointer: { value: new THREE.Vector2(OFFSCREEN, OFFSCREEN) },
        uPointerVelocity: { value: new THREE.Vector2(0, 0) },
        uTime: { value: 0 },
        uNoiseScale: { value: noiseScale },
        uNoiseStrength: { value: noiseStrength },
        uDamping: { value: damping },
        uLifespan: { value: lifespan },
        uPointerStrength: { value: cursorStrength },
        uPointerFalloff: { value: 1000 },
        uImageAspect: { value: 1 },
        uFocus: { value: new THREE.Vector2(focus[0], focus[1]) },
        uFit: { value: fit },
        uZoom: { value: zoom },
        uTrace: { value: trace },
        uEdgeAffinity: { value: edgeAffinity },
        uCling: { value: cling },
        uAlong: { value: along },
        uEdgeFloor: { value: edgeFloor },
        uMorph: { value: 0 }
      },
      depthTest: false,
      depthWrite: false
    });

    var plane = new THREE.PlaneGeometry(2, 2);
    var quad = new THREE.Mesh(plane, stepMaterial);
    quad.frustumCulled = false;
    simScene.add(quad);

    var total = grid * grid;
    var lookup = new Float32Array(total * 3);
    for (var i = 0; i < total; i++) {
      lookup[i * 3] = ((i % grid) + 0.5) / grid;
      lookup[i * 3 + 1] = (Math.floor(i / grid) + 0.5) / grid;
    }
    var geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(lookup, 3));
    var points = new THREE.Points(geometry, pointMaterial);
    points.frustumCulled = false;
    points.renderOrder = 1;
    scene.add(points);

    return {
      buffers: buffers, front: 0, seeded: false,
      seedMaterial: seedMaterial, stepMaterial: stepMaterial,
      quad: quad, plane: plane, geometry: geometry, points: points
    };
  }

  function refreshTargets(width, height) {
    if (width === targetSize.w && height === targetSize.h) return;
    targetSize.w = width;
    targetSize.h = height;
    targetTexture.image.data.set(graphTargets(grid, width, height, graphCfg));
    targetTexture.needsUpdate = true;
  }

  function resize() {
    var w = root.clientWidth, h = root.clientHeight;
    if (w < 2 || h < 2) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, dprCap));
    renderer.setSize(w, h, false);
  }

  function track(event) {
    var bounds = canvas.getBoundingClientRect();
    var ratio = renderer.getPixelRatio();
    var x = (event.clientX - bounds.left) * ratio;
    var y = (event.clientY - bounds.top) * ratio;
    if (!pointer.engaged) {
      pointer.lastX = x; pointer.lastY = y; pointer.engaged = true;
    }
    pointer.targetX = x; pointer.targetY = y;
  }

  function release() {
    pointer.engaged = false;
    pointer.targetX = OFFSCREEN; pointer.targetY = OFFSCREEN;
    pointer.lastX = OFFSCREEN; pointer.lastY = OFFSCREEN;
    pointer.velocityX = 0; pointer.velocityY = 0;
  }

  function step(delta) {
    if (!sim || !source || !inView) return;
    renderer.getDrawingBufferSize(frame);
    var width = Math.max(frame.x, 1), height = Math.max(frame.y, 1);
    var ratio = renderer.getPixelRatio();
    refreshTargets(width, height);

    clock.elapsed += delta * 1000;
    var settle = fadeInMs > 0 ? Math.min(clock.elapsed / fadeInMs, 1) : 1;

    if (cursorInteraction) {
      pointer.velocityX += ((pointer.targetX - pointer.lastX) - pointer.velocityX) * 0.15;
      pointer.velocityY += ((pointer.targetY - pointer.lastY) - pointer.velocityY) * 0.15;
    } else {
      pointer.velocityX = 0; pointer.velocityY = 0;
    }
    pointer.lastX = pointer.targetX; pointer.lastY = pointer.targetY;

    var u = sim.stepMaterial.uniforms;
    u.uResolution.value.set(width, height);
    u.uNoiseScale.value = noiseScale;
    u.uNoiseStrength.value = noiseStrength;
    u.uDamping.value = damping;
    u.uLifespan.value = lifespan;
    u.uPointerStrength.value = cursorInteraction ? cursorStrength : 0;
    u.uPointerFalloff.value = Math.pow(Math.max(cursorRadius * ratio, 1), 2);
    u.uPointer.value.set(pointer.targetX, pointer.targetY);
    u.uPointerVelocity.value.set(pointer.velocityX, pointer.velocityY);
    u.uImage.value = source.texture;
    u.uImageAspect.value = source.aspect;
    u.uTrace.value = trace * ratio * settle;
    u.uEdgeAffinity.value = edgeAffinity;
    u.uCling.value = cling * settle;
    u.uAlong.value = along * ratio * settle;
    u.uEdgeFloor.value = edgeFloor;
    u.uMorph.value = morph;
    clock.time += delta * 0.05 * speed;
    u.uTime.value = clock.time;

    if (!sim.seeded) {
      sim.seedMaterial.uniforms.uResolution.value.set(width, height);
      sim.seedMaterial.uniforms.uLifespan.value = lifespan;
      sim.seedMaterial.uniforms.uImage.value = source.texture;
      sim.seedMaterial.uniforms.uImageAspect.value = source.aspect;
      sim.seedMaterial.uniforms.uEdgeAffinity.value = edgeAffinity;
      sim.quad.material = sim.seedMaterial;
      sim.buffers.forEach(function (buffer) {
        renderer.setRenderTarget(buffer);
        renderer.render(simScene, simCamera);
      });
      renderer.setRenderTarget(null);
      sim.seeded = true;
    }

    var read = sim.buffers[sim.front];
    var write = sim.buffers[1 - sim.front];
    u.tMotion.value = read.textures[0];
    u.tLife.value = read.textures[1];
    sim.quad.material = sim.stepMaterial;
    renderer.setRenderTarget(write);
    renderer.render(simScene, simCamera);
    renderer.setRenderTarget(null);
    sim.front = 1 - sim.front;

    var current = sim.buffers[sim.front];
    var pu = pointMaterial.uniforms;
    pu.tMotion.value = current.textures[0];
    pu.tLife.value = current.textures[1];
    pu.uImage.value = source.texture;
    pu.uResolution.value.set(width, height);
    pu.uImageAspect.value = source.aspect;
    pu.uPointSize.value = particleSize * ratio;
    pu.uOpacity.value = particleOpacity * settle;
    pu.uMorph.value = morph;

    var bu = backdropMaterial.uniforms;
    bu.uImage.value = source.texture;
    bu.uFrameAspect.value = width / height;
    bu.uImageAspect.value = source.aspect;
    bu.uOpacity.value = imageOpacity * Math.max(0, 1 - morph * 1.9);

    renderer.setRenderTarget(null);
    renderer.clear();
    renderer.render(scene, camera);

    if (!live) {
      live = true;
      if (onLive) onLive();
    }
  }

  var last = performance.now();
  function loop(now) {
    if (!running) return;
    raf = requestAnimationFrame(loop);
    var delta = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(delta);
  }

  canvas.addEventListener('pointermove', track);
  canvas.addEventListener('pointerleave', release);
  var ro = new ResizeObserver(resize);
  ro.observe(root);
  var io = new IntersectionObserver(function (entries) {
    inView = entries[0] && entries[0].isIntersecting;
  }, { threshold: 0.01 });
  io.observe(root);

  loadTexture(imageUrl).then(function (src) {
    source = src;
    sim = buildSim();
    resize();
    last = performance.now();
    raf = requestAnimationFrame(loop);
  }).catch(function () {
    renderer.dispose();
    if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
  });

  function destroy() {
    running = false;
    cancelAnimationFrame(raf);
    canvas.removeEventListener('pointermove', track);
    canvas.removeEventListener('pointerleave', release);
    ro.disconnect();
    io.disconnect();
    if (sim) {
      sim.buffers.forEach(function (b) { b.dispose(); });
      sim.seedMaterial.dispose();
      sim.stepMaterial.dispose();
      sim.plane.dispose();
      sim.geometry.dispose();
    }
    pointMaterial.dispose();
    backdropMaterial.dispose();
    targetTexture.dispose();
    if (source) source.texture.dispose();
    renderer.dispose();
    if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
  }

  /* the departure — resolves once the constellation has settled */
  function toGraph(durationMs) {
    var span = durationMs || 1500;
    return new Promise(function (resolve) {
      if (!sim) { resolve(); return; }
      var start = performance.now();
      requestAnimationFrame(function tick(now) {
        var t = Math.min(Math.max(now - start, 0) / span, 1);
        morph = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        if (t < 1) requestAnimationFrame(tick);
        else resolve();
      });
    });
  }

  return { destroy: destroy, toGraph: toGraph, canvas: canvas };
}
