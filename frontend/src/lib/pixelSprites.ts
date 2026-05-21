/* Procedural pixel-art sprite definitions for the virtual office.
 *
 * Each agent is drawn as a small humanoid (16 x 24 px) with a role-specific
 * accessory. State + frame index drives the per-pixel layout so we never
 * ship a PNG file — everything is rendered on the fly into the canvas.
 */

export type AgentState = 'idle' | 'thinking' | 'talking' | 'working' | 'happy' | 'sad';

/** Logical sprite size, in pixels. */
export const SPRITE_W = 16;
export const SPRITE_H = 24;

/** Per-agent palette. The base body colour comes from `AgentRole.color`;
 *  we derive secondaries (shadow, accent, accessory) by tinting. */
export type Palette = {
  body: string;       // primary tint
  bodyShade: string;  // darker for shadows
  accent: string;     // accessory accent
  skin: string;       // face / hands
  outline: string;    // 1-px outline
  eye: string;        // eye pixel
};

export function paletteFromColor(color: string): Palette {
  // Parse "#rrggbb"
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  const shade = (v: number, k: number) =>
    Math.max(0, Math.min(255, Math.round(v * k)));
  const toHex = (rv: number, gv: number, bv: number) =>
    `#${[rv, gv, bv].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  return {
    body: color,
    bodyShade: toHex(shade(r, 0.6), shade(g, 0.6), shade(b, 0.6)),
    accent: toHex(shade(r, 1.15), shade(g, 1.15), shade(b, 1.15)),
    skin: '#f0d8b0',
    outline: '#0c0e16',
    eye: '#0c0e16',
  };
}

/** A pixel cell is referenced by a single letter; lookup table maps letter
 *  to a Palette field. '.' means transparent. */
const KEY: Record<string, keyof Palette | 'transparent'> = {
  '.': 'transparent',
  B: 'body',
  S: 'bodyShade',
  A: 'accent',
  K: 'skin',
  O: 'outline',
  E: 'eye',
};

/**
 * Base humanoid silhouette (16 x 24). 'B' is body colour, 'S' is the
 * shaded body, 'K' is skin (face), 'O' is the outline. Hair and eyes
 * placed at (5-10, 7) and a small smile at row 11.
 *
 *  cols:  0123456789012345
 */
const BASE: string[] = [
  '................', //  0
  '................', //  1
  '.....OOOOOO.....', //  2  hair top
  '....OKKKKKKO....', //  3
  '....OKKKKKKO....', //  4
  '....OKKKKKKO....', //  5  face
  '....OKEKKEKO....', //  6  eyes
  '....OKKKKKKO....', //  7
  '....OKKKKKKO....', //  8
  '.....OOOOOO.....', //  9  jawline
  '......BB........', // 10  neck
  '....OBBBBBBO....', // 11  chest top
  '....OBBSSBBO....', // 12  shirt shade
  '....OBBBBBBO....', // 13
  '....OBSSSSBO....', // 14
  '....OBBBBBBO....', // 15
  '.....OBBBBO.....', // 16  waist
  '.....OBBBBO.....', // 17
  '.....OSBBSO.....', // 18  legs split
  '.....OSBBSO.....', // 19
  '.....OSBBSO.....', // 20
  '.....OOOOOO.....', // 21  feet
  '................', // 22
  '................', // 23
];

export type PixelGrid = string[];

/** Apply a vertical bob offset to a sprite. */
function bob(grid: PixelGrid, dy: number): PixelGrid {
  if (dy === 0) return grid;
  const empty = '.'.repeat(SPRITE_W);
  if (dy > 0) {
    const cut = grid.slice(0, grid.length - dy);
    return Array(dy).fill(empty).concat(cut);
  }
  const cut = grid.slice(-dy);
  return cut.concat(Array(-dy).fill(empty));
}

/** Paint a small overlay block on top of a grid (e.g. mouth, sparkle). */
function overlay(grid: PixelGrid, x: number, y: number, pattern: string[]): PixelGrid {
  const out = grid.slice();
  for (let dy = 0; dy < pattern.length; dy++) {
    const row = out[y + dy] ?? '';
    if (!row) continue;
    const chars = row.split('');
    for (let dx = 0; dx < pattern[dy].length; dx++) {
      const ch = pattern[dy][dx];
      if (ch === '.' || ch === ' ') continue;
      if (x + dx < 0 || x + dx >= chars.length) continue;
      chars[x + dx] = ch;
    }
    out[y + dy] = chars.join('');
  }
  return out;
}

// ---- Role-specific accessory layers ----

/** Wizard hat (planner Aiden). */
function withWizardHat(g: PixelGrid): PixelGrid {
  return overlay(g, 4, 0, [
    '.....OO.........',
    '....OAAO........',
    '...OAAAAO.......',
    '..OAAAABBO......',
    '.OAAAAAABBO.....',
  ]);
}

/** Book in hand (researcher Mira). */
function withBook(g: PixelGrid): PixelGrid {
  return overlay(g, 2, 12, [
    'OAAO............',
    'OAKAO...........',
    'OAKAO...........',
    'OAAO............',
  ]);
}

/** Glasses (coder Kade). */
function withGlasses(g: PixelGrid): PixelGrid {
  return overlay(g, 3, 6, ['OAAOOOAAO']);
}

/** Monocle / eye gadget (vision Iris). */
function withMonocle(g: PixelGrid): PixelGrid {
  return overlay(g, 5, 5, [
    'OAAO',
    'OAAO',
  ]);
}

/** Bow tie + judge bow (critic Vex). */
function withBowTie(g: PixelGrid): PixelGrid {
  return overlay(g, 5, 10, ['AAAAAA']);
}

/** Hammer in hand (executor Orin). */
function withHammer(g: PixelGrid): PixelGrid {
  return overlay(g, 11, 11, [
    'OAAO',
    'OAAO',
    '.OO.',
    '.OO.',
    '.OO.',
  ]);
}

/** Crown (conductor Nyra). */
function withCrown(g: PixelGrid): PixelGrid {
  return overlay(g, 4, 0, [
    'O.O.O.O.',
    'OAAAAAAO',
    'OAAAAAAO',
  ]);
}

/** Halo (oracle Vox). */
function withHalo(g: PixelGrid): PixelGrid {
  return overlay(g, 3, 0, [
    '.OAAAAAO.',
    'OA.....AO',
    'OA.....AO',
    '.OAAAAAO.',
  ]);
}

const ACCESSORY: Record<string, (g: PixelGrid) => PixelGrid> = {
  planner: withWizardHat,
  researcher: withBook,
  coder: withGlasses,
  vision: withMonocle,
  critic: withBowTie,
  executor: withHammer,
  conductor: withCrown,
  oracle: withHalo,
};

// ---- State decorations ----

/** Eyes-closed face for thinking. */
function thinkingFace(g: PixelGrid): PixelGrid {
  // replace eye row with closed eyes
  const closed = '....OKKKKKKO....'.split('');
  closed[8] = 'E';
  closed[11] = 'E';
  // Build proper closed-eyes row
  const newRow = '....OKK--KKO....'.replace(/-/g, 'O');
  const out = g.slice();
  out[6] = newRow;
  return out;
}

/** Open mouth (talking). */
function talkingFace(g: PixelGrid): PixelGrid {
  return overlay(g, 6, 8, ['OOOO']);
}

/** Smile (happy). */
function happyFace(g: PixelGrid): PixelGrid {
  return overlay(g, 6, 8, ['O..O', '.OO.']);
}

/** Frown (sad). */
function sadFace(g: PixelGrid): PixelGrid {
  return overlay(g, 6, 8, ['.OO.', 'O..O']);
}

// ---- Public API ----

/** Build the per-state sprite grid for a given role + animation frame. */
export function spriteFor(
  roleId: string,
  state: AgentState,
  frame: number, // 0..3
): PixelGrid {
  let g = BASE.slice();
  const accessory = ACCESSORY[roleId];
  if (accessory) g = accessory(g);

  // Per-state face / pose
  switch (state) {
    case 'thinking':
      g = thinkingFace(g);
      break;
    case 'talking':
      // mouth opens on frames 0/2, closes on 1/3
      if (frame % 2 === 0) g = talkingFace(g);
      break;
    case 'working':
      // small idle bob, base pose
      break;
    case 'happy':
      g = happyFace(g);
      break;
    case 'sad':
      g = sadFace(g);
      break;
    case 'idle':
    default:
      break;
  }

  // Idle / talking / thinking all get a 1-pixel bob (frames 0,1 = up; 2,3 = down)
  const dy = (state === 'working') ? 0 : (frame < 2 ? -1 : 0);
  g = bob(g, dy);
  return g;
}

/** Paint a grid into a 2D canvas context at integer (x, y), 1 cell = 1 px.
 *  We use fillRect rather than putImageData so a single sprite render
 *  is ~few hundred draw calls but stays GC-free and very fast. */
export function paintSprite(
  ctx: CanvasRenderingContext2D,
  grid: PixelGrid,
  px: number,
  py: number,
  palette: Palette,
): void {
  for (let y = 0; y < grid.length; y++) {
    const row = grid[y];
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      const slot = KEY[ch];
      if (!slot || slot === 'transparent') continue;
      ctx.fillStyle = palette[slot as keyof Palette];
      ctx.fillRect(px + x, py + y, 1, 1);
    }
  }
}

/** Lookup: which animation state best matches a given event kind? */
export function eventToState(kind: string): AgentState | null {
  if (kind === 'agent.start' || kind === 'reasoning.start') return 'thinking';
  if (kind === 'agent.message' || kind === 'agent.delta') return 'talking';
  if (kind === 'tool.start' || kind === 'tool.call') return 'working';
  if (kind === 'agent.finish') return 'idle';
  if (kind === 'critic.approve') return 'happy';
  if (kind === 'critic.block' || kind === 'agent.error') return 'sad';
  return null;
}
