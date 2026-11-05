// Иконки категорий товара. Список специально узкий — под ассортимент небольшого
// магазина, а не «все иконки на всякий случай»: каждая попадает в бандл.
import {
  Package, Shirt, Footprints, Watch, Glasses, Gem, ShoppingBag, Baby,
  Utensils, Coffee, CupSoda, Candy, Cake, Wine, Apple,
  Home, Sofa, Lamp, Bath, Refrigerator, Flower, Trees,
  Smartphone, Headphones, Laptop, Tv, Cable, BatteryCharging,
  Book, Pencil, Backpack, Palette, Scissors, Puzzle, Dices, Gamepad2,
  Dumbbell, Bike, Tent, Umbrella, Gift, Sparkles, Music, Guitar,
  Pill, Stethoscope, Dog, PawPrint, Car, Wrench, Hammer, Paintbrush,
  Cigarette, Sun, Snowflake, Star, Crown, Heart, Ticket, Camera,
  HelpCircle
} from 'lucide-svelte'

export const iconRegistry = {
  package: Package, shirt: Shirt, footprints: Footprints, watch: Watch,
  glasses: Glasses, gem: Gem, 'shopping-bag': ShoppingBag, baby: Baby,
  utensils: Utensils, coffee: Coffee, soda: CupSoda, candy: Candy,
  cake: Cake, wine: Wine, apple: Apple,
  home: Home, sofa: Sofa, lamp: Lamp, bath: Bath, fridge: Refrigerator,
  flower: Flower, trees: Trees,
  smartphone: Smartphone, headphones: Headphones, laptop: Laptop, tv: Tv,
  cable: Cable, battery: BatteryCharging,
  book: Book, pencil: Pencil, backpack: Backpack, palette: Palette,
  scissors: Scissors, puzzle: Puzzle, dices: Dices, gamepad: Gamepad2,
  dumbbell: Dumbbell, bike: Bike, tent: Tent, umbrella: Umbrella,
  gift: Gift, sparkles: Sparkles, music: Music, guitar: Guitar,
  pill: Pill, stethoscope: Stethoscope, dog: Dog, paw: PawPrint,
  car: Car, wrench: Wrench, hammer: Hammer, paintbrush: Paintbrush,
  cigarette: Cigarette, sun: Sun, snowflake: Snowflake, star: Star,
  crown: Crown, heart: Heart, ticket: Ticket, camera: Camera,
  'help-circle': HelpCircle
}

export function getIcon(name) {
  return iconRegistry[name] || Package
}

export const CATEGORY_ICONS = Object.keys(iconRegistry).filter((n) => n !== 'help-circle')

export const PALETTE = [
  // синие / голубые
  '#0ea5e9', '#0284c7', '#3b82f6', '#2563eb', '#6366f1', '#4f46e5',
  '#06b6d4', '#0891b2',
  // фиолетовые / розовые
  '#8b5cf6', '#7c3aed', '#a855f7', '#d946ef', '#ec4899', '#db2777',
  // красные / оранжевые
  '#f43f5e', '#e11d48', '#ef4444', '#f97316', '#ea580c', '#f59e0b',
  '#d97706', '#eab308',
  // зелёные / бирюзовые
  '#84cc16', '#65a30d', '#22c55e', '#16a34a', '#10b981', '#059669',
  '#14b8a6', '#0d9488',
  // нейтральные
  '#78716c', '#64748b', '#475569', '#334155'
]
