export const AVATARS = {
  fox:      { emoji: '🦊', grad: 'linear-gradient(135deg,#f97316,#f43f5e)' },
  cat:      { emoji: '🐱', grad: 'linear-gradient(135deg,#a855f7,#6366f1)' },
  dog:      { emoji: '🐶', grad: 'linear-gradient(135deg,#f59e0b,#f97316)' },
  owl:      { emoji: '🦉', grad: 'linear-gradient(135deg,#8b5cf6,#06b6d4)' },
  bear:     { emoji: '🐻', grad: 'linear-gradient(135deg,#f43f5e,#8b5cf6)' },
  panda:    { emoji: '🐼', grad: 'linear-gradient(135deg,#22c55e,#14b8a6)' },
  penguin:  { emoji: '🐧', grad: 'linear-gradient(135deg,#0ea5e9,#6366f1)' },
  koala:    { emoji: '🐨', grad: 'linear-gradient(135deg,#14b8a6,#3b82f6)' },
  lion:     { emoji: '🦁', grad: 'linear-gradient(135deg,#f59e0b,#ef4444)' },
  tiger:    { emoji: '🐯', grad: 'linear-gradient(135deg,#f97316,#eab308)' },
  rabbit:   { emoji: '🐰', grad: 'linear-gradient(135deg,#ec4899,#a855f7)' },
  hamster:  { emoji: '🐹', grad: 'linear-gradient(135deg,#fbbf24,#f97316)' },
  mouse:    { emoji: '🐭', grad: 'linear-gradient(135deg,#94a3b8,#64748b)' },
  frog:     { emoji: '🐸', grad: 'linear-gradient(135deg,#22c55e,#84cc16)' },
  monkey:   { emoji: '🐵', grad: 'linear-gradient(135deg,#a16207,#f59e0b)' },
  chick:    { emoji: '🐤', grad: 'linear-gradient(135deg,#facc15,#f59e0b)' },
  unicorn:  { emoji: '🦄', grad: 'linear-gradient(135deg,#ec4899,#8b5cf6)' },
  dragon:   { emoji: '🐲', grad: 'linear-gradient(135deg,#10b981,#06b6d4)' },
  wolf:     { emoji: '🐺', grad: 'linear-gradient(135deg,#64748b,#6366f1)' },
  hedgehog: { emoji: '🦔', grad: 'linear-gradient(135deg,#b45309,#78716c)' },
  pig:      { emoji: '🐷', grad: 'linear-gradient(135deg,#f9a8d4,#ec4899)' },
  cow:      { emoji: '🐮', grad: 'linear-gradient(135deg,#f472b6,#a855f7)' },
  elephant: { emoji: '🐘', grad: 'linear-gradient(135deg,#94a3b8,#3b82f6)' },
  octopus:  { emoji: '🐙', grad: 'linear-gradient(135deg,#f43f5e,#ec4899)' },
  whale:    { emoji: '🐳', grad: 'linear-gradient(135deg,#0ea5e9,#3b82f6)' },
  turtle:   { emoji: '🐢', grad: 'linear-gradient(135deg,#16a34a,#0d9488)' },
  butterfly:{ emoji: '🦋', grad: 'linear-gradient(135deg,#06b6d4,#8b5cf6)' },
  parrot:   { emoji: '🦜', grad: 'linear-gradient(135deg,#22c55e,#f59e0b)' },
  deer:     { emoji: '🦌', grad: 'linear-gradient(135deg,#d97706,#78716c)' },
  raccoon:  { emoji: '🦝', grad: 'linear-gradient(135deg,#78716c,#334155)' },
  crab:     { emoji: '🦀', grad: 'linear-gradient(135deg,#ef4444,#f97316)' },
  dolphin:  { emoji: '🐬', grad: 'linear-gradient(135deg,#38bdf8,#6366f1)' }
}

export const AVATAR_KEYS = Object.keys(AVATARS)

export function avatar(key) {
  return AVATARS[key] || AVATARS.fox
}
