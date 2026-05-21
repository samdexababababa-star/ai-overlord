/* Pixel-art office rendering engine.
 *
 * Composes rooms + agents on a logical canvas (LOGICAL_W x LOGICAL_H) and
 * lets the React component scale it up with crisp pixels. The engine is
 * stateless w.r.t. React; we feed it a per-agent state from event handling
 * and it returns the drawn frame.
 */

import {
  type AgentState,
  type Palette,
  paletteFromColor,
  paintSprite,
  spriteFor,
  SPRITE_W,
  SPRITE_H,
} from './pixelSprites';

/** Logical (low-resolution) canvas, in pixels. We render here and the
 *  hosting CSS scales the canvas element up to the available viewport. */
export const LOGICAL_W = 480;
export const LOGICAL_H = 320;

/** Logical room layout: top row + bottom row + atrium centre. */
export type RoomLayout = {
  id: string;
  label: string;
  x: number; y: number; w: number; h: number;
  floor: string; wall: string; accent: string;
  agentId: string; agentName: string;
};

export const ROOMS: RoomLayout[] = [
  {
    id: 'war_room',  label: 'War Room',  x: 6,   y: 18,  w: 110, h: 90,
    floor: '#0b1f33', wall: '#11304d', accent: '#7cd1ff',
    agentId: 'planner', agentName: 'Aiden',
  },
  {
    id: 'library',   label: 'Library',   x: 124, y: 18,  w: 110, h: 90,
    floor: '#0e2218', wall: '#163524', accent: '#9ee493',
    agentId: 'researcher', agentName: 'Mira',
  },
  {
    id: 'lab',       label: 'Lab',       x: 242, y: 18,  w: 110, h: 90,
    floor: '#2a1b06', wall: '#43290a', accent: '#ffb86b',
    agentId: 'coder', agentName: 'Kade',
  },
  {
    id: 'observatory', label: 'Observatory', x: 360, y: 18, w: 110, h: 90,
    floor: '#1b1339', wall: '#2a1d5a', accent: '#c9a8ff',
    agentId: 'vision', agentName: 'Iris',
  },
  {
    id: 'court',     label: 'Court',     x: 6,   y: 116, w: 110, h: 90,
    floor: '#330b1d', wall: '#52132f', accent: '#ff6b8a',
    agentId: 'critic', agentName: 'Vex',
  },
  {
    id: 'workshop',  label: 'Workshop',  x: 124, y: 116, w: 110, h: 90,
    floor: '#332b08', wall: '#4d3f0c', accent: '#ffd866',
    agentId: 'executor', agentName: 'Orin',
  },
  {
    id: 'atrium',    label: 'Atrium',    x: 242, y: 116, w: 110, h: 90,
    floor: '#202028', wall: '#2e2e3a', accent: '#f5f5f5',
    agentId: 'conductor', agentName: 'Nyra',
  },
  {
    id: 'balcony',   label: 'Balcony',   x: 360, y: 116, w: 110, h: 90,
    floor: '#0a2a26', wall: '#103f38', accent: '#5be7c4',
    agentId: 'oracle', agentName: 'Vox',
  },
];

export type AgentAnim = {
  state: AgentState;
  /** When the state was last set (ms since epoch). */
  setAt: number;
  /** Optional message bubble. */
  bubble?: string;
  /** Optional model name to show under sprite. */
  model?: string;
};

export type FrameInput = {
  roles: Record<string, { color: string; title: string }>; // by agentId
  anim: Record<string, AgentAnim>; // by agentId
  now: number; // ms
};

/** 5-stop scanline shading for tile floors. */
function paintTile(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  floor: string, wall: string,
) {
  // Wall (top 6 px) + floor
  ctx.fillStyle = wall;
  ctx.fillRect(x, y, w, 6);
  ctx.fillStyle = floor;
  ctx.fillRect(x, y + 6, w, h - 6);
  // Floor grid lines
  ctx.fillStyle = 'rgba(0,0,0,0.18)';
  for (let gx = x + 4; gx < x + w; gx += 6) {
    ctx.fillRect(gx, y + 6, 1, h - 6);
  }
  for (let gy = y + 12; gy < y + h; gy += 6) {
    ctx.fillRect(x, gy, w, 1);
  }
}

/** Border / glow around an active room. */
function paintBorder(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  color: string,
  glow: boolean,
) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, 1);
  ctx.fillRect(x, y + h - 1, w, 1);
  ctx.fillRect(x, y, 1, h);
  ctx.fillRect(x + w - 1, y, 1, h);
  if (glow) {
    ctx.fillStyle = color + '44';
    ctx.fillRect(x - 1, y - 1, w + 2, 1);
    ctx.fillRect(x - 1, y + h, w + 2, 1);
    ctx.fillRect(x - 1, y - 1, 1, h + 2);
    ctx.fillRect(x + w, y - 1, 1, h + 2);
  }
}

/** Tiny 3x5 pixel font for room labels + names. */
const FONT_3X5: Record<string, string[]> = {
  A: ['.X.', 'X.X', 'XXX', 'X.X', 'X.X'],
  B: ['XX.', 'X.X', 'XX.', 'X.X', 'XX.'],
  C: ['XXX', 'X..', 'X..', 'X..', 'XXX'],
  D: ['XX.', 'X.X', 'X.X', 'X.X', 'XX.'],
  E: ['XXX', 'X..', 'XX.', 'X..', 'XXX'],
  F: ['XXX', 'X..', 'XX.', 'X..', 'X..'],
  G: ['XXX', 'X..', 'X.X', 'X.X', 'XXX'],
  H: ['X.X', 'X.X', 'XXX', 'X.X', 'X.X'],
  I: ['XXX', '.X.', '.X.', '.X.', 'XXX'],
  J: ['XXX', '..X', '..X', 'X.X', 'XXX'],
  K: ['X.X', 'X.X', 'XX.', 'X.X', 'X.X'],
  L: ['X..', 'X..', 'X..', 'X..', 'XXX'],
  M: ['X.X', 'XXX', 'XXX', 'X.X', 'X.X'],
  N: ['X.X', 'XXX', 'XXX', 'XXX', 'X.X'],
  O: ['XXX', 'X.X', 'X.X', 'X.X', 'XXX'],
  P: ['XXX', 'X.X', 'XXX', 'X..', 'X..'],
  Q: ['XXX', 'X.X', 'X.X', 'XXX', '..X'],
  R: ['XXX', 'X.X', 'XX.', 'X.X', 'X.X'],
  S: ['XXX', 'X..', 'XXX', '..X', 'XXX'],
  T: ['XXX', '.X.', '.X.', '.X.', '.X.'],
  U: ['X.X', 'X.X', 'X.X', 'X.X', 'XXX'],
  V: ['X.X', 'X.X', 'X.X', 'X.X', '.X.'],
  W: ['X.X', 'X.X', 'XXX', 'XXX', 'X.X'],
  X: ['X.X', 'X.X', '.X.', 'X.X', 'X.X'],
  Y: ['X.X', 'X.X', '.X.', '.X.', '.X.'],
  Z: ['XXX', '..X', '.X.', 'X..', 'XXX'],
  ' ': ['...', '...', '...', '...', '...'],
  '-': ['...', '...', 'XXX', '...', '...'],
  '?': ['XXX', '..X', '.X.', '...', '.X.'],
  '!': ['.X.', '.X.', '.X.', '...', '.X.'],
  '.': ['...', '...', '...', '...', '.X.'],
  '0': ['XXX', 'X.X', 'X.X', 'X.X', 'XXX'],
  '1': ['.X.', 'XX.', '.X.', '.X.', 'XXX'],
  '2': ['XXX', '..X', 'XXX', 'X..', 'XXX'],
  '3': ['XXX', '..X', 'XXX', '..X', 'XXX'],
  '4': ['X.X', 'X.X', 'XXX', '..X', '..X'],
  '5': ['XXX', 'X..', 'XXX', '..X', 'XXX'],
  '6': ['XXX', 'X..', 'XXX', 'X.X', 'XXX'],
  '7': ['XXX', '..X', '..X', '..X', '..X'],
  '8': ['XXX', 'X.X', 'XXX', 'X.X', 'XXX'],
  '9': ['XXX', 'X.X', 'XXX', '..X', 'XXX'],
};

export function paintText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number, y: number,
  color: string,
) {
  const ch = text.toUpperCase();
  ctx.fillStyle = color;
  for (let i = 0; i < ch.length; i++) {
    const glyph = FONT_3X5[ch[i]] ?? FONT_3X5[' '];
    for (let gy = 0; gy < 5; gy++) {
      for (let gx = 0; gx < 3; gx++) {
        if (glyph[gy][gx] === 'X') ctx.fillRect(x + i * 4 + gx, y + gy, 1, 1);
      }
    }
  }
}

/** Tiny thought / speech bubble. The shape is 1-px rectangle with a 1-px tail
 *  pointing down toward (anchorX, anchorY). */
function paintBubble(
  ctx: CanvasRenderingContext2D,
  text: string,
  bx: number, by: number,
  w: number, h: number,
  fill: string,
  fg: string,
) {
  ctx.fillStyle = fill;
  ctx.fillRect(bx, by, w, h);
  ctx.fillStyle = '#0c0e16';
  ctx.fillRect(bx, by, w, 1);
  ctx.fillRect(bx, by + h - 1, w, 1);
  ctx.fillRect(bx, by, 1, h);
  ctx.fillRect(bx + w - 1, by, 1, h);
  ctx.fillRect(bx + 2, by + h, 1, 1);
  ctx.fillRect(bx + 3, by + h, 1, 1);
  paintText(ctx, text, bx + 2, by + 2, fg);
}

/** Particles for "thinking" / "working" states. */
function paintParticles(
  ctx: CanvasRenderingContext2D,
  state: AgentState,
  cx: number, cy: number,
  frame: number,
  accent: string,
) {
  if (state === 'thinking') {
    // Floating "?" above head — appears on frames 0,1, fades on 2,3
    const ts = frame < 2 ? '?' : ' ';
    paintText(ctx, ts, cx - 2, cy - 8, accent);
  } else if (state === 'working') {
    // 4-point sparkle that rotates
    const offsets = [
      [0, -4], [4, 0], [0, 4], [-4, 0],
    ];
    const [dx, dy] = offsets[frame % 4];
    ctx.fillStyle = accent;
    ctx.fillRect(cx + dx, cy - 2 + dy, 1, 1);
  } else if (state === 'talking') {
    // Two small bars on right of head
    ctx.fillStyle = accent;
    ctx.fillRect(cx + 8 + (frame % 2), cy - 2, 1, 1);
    ctx.fillRect(cx + 8 + (frame % 2), cy, 1, 1);
  }
}

/** Render one full frame of the office. */
export function renderFrame(
  ctx: CanvasRenderingContext2D,
  input: FrameInput,
): void {
  // Background gradient (cheap: two solid rectangles)
  ctx.fillStyle = '#06070d';
  ctx.fillRect(0, 0, LOGICAL_W, LOGICAL_H);
  ctx.fillStyle = '#0a0b16';
  ctx.fillRect(0, 0, LOGICAL_W, LOGICAL_H / 2);

  // Stars for upper half
  for (let i = 0; i < 30; i++) {
    const sx = (i * 17) % LOGICAL_W;
    const sy = (i * 13) % (LOGICAL_H / 3);
    ctx.fillStyle = i % 3 === 0 ? '#7cd1ff' : '#444';
    ctx.fillRect(sx, sy, 1, 1);
  }

  const frame = Math.floor(input.now / 250) % 4;

  for (const room of ROOMS) {
    const anim = input.anim[room.agentId];
    const role = input.roles[room.agentId];
    const isActive = anim && anim.state !== 'idle' && (input.now - anim.setAt < 8000);

    paintTile(ctx, room.x, room.y, room.w, room.h, room.floor, room.wall);
    paintBorder(ctx, room.x, room.y, room.w, room.h, room.accent, !!isActive);
    paintText(ctx, room.label, room.x + 4, room.y + 1, '#ffffff');

    // Sprite centred in room (slight offset down so feet are at floor)
    const spriteX = Math.floor(room.x + (room.w - SPRITE_W) / 2);
    const spriteY = Math.floor(room.y + (room.h - SPRITE_H) - 6);
    const palette: Palette = paletteFromColor(role?.color ?? room.accent);
    const state = anim?.state ?? 'idle';
    const grid = spriteFor(room.agentId, state, frame);
    paintSprite(ctx, grid, spriteX, spriteY, palette);

    // Name plate
    paintText(ctx, room.agentName, room.x + 4, room.y + room.h - 7, '#dbe1ea');

    // Particles by state
    paintParticles(ctx, state, spriteX + 8, spriteY + 2, frame, room.accent);

    // Speech bubble (truncated to ~16 chars)
    if (anim?.bubble) {
      const txt = anim.bubble.slice(0, 16);
      const bw = Math.max(20, txt.length * 4 + 4);
      paintBubble(
        ctx,
        txt,
        Math.max(2, spriteX - 4),
        Math.max(2, spriteY - 12),
        Math.min(bw, room.w - 6),
        9,
        '#1a1b28',
        '#ffffff',
      );
    }
  }

  // Footer with active room count
  const activeCount = Object.values(input.anim).filter(
    (a) => a.state !== 'idle' && (input.now - a.setAt < 8000),
  ).length;
  paintText(
    ctx,
    `ACTIVE ${activeCount} OF ${ROOMS.length}`,
    LOGICAL_W - 80,
    LOGICAL_H - 7,
    '#7cd1ff',
  );
}
