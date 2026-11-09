export interface PriceInput {
  weightKg: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
  express: boolean;
  remoteZone: boolean;
}

const BASE_PRICE = 250;
const PRICE_PER_KG = 40;
const HEAVY_THRESHOLD_KG = 20;
const HEAVY_SURCHARGE = 1.3;
const EXPRESS_MULTIPLIER = 1.5;
const REMOTE_ZONE_FEE = 180;
const FUEL_SURCHARGE = 1.06;
const VOLUMETRIC_DIVISOR = 5000;

export function quote(input: PriceInput): number {
  const volumetricKg = (input.lengthCm * input.widthCm * input.heightCm) / VOLUMETRIC_DIVISOR;
  const billableKg = Math.max(input.weightKg, volumetricKg);
  let price = BASE_PRICE + billableKg * PRICE_PER_KG;
  if (billableKg > HEAVY_THRESHOLD_KG) {
    price *= HEAVY_SURCHARGE;
  }
  if (input.express) {
    price *= EXPRESS_MULTIPLIER;
  }
  if (input.remoteZone) {
    price += REMOTE_ZONE_FEE;
  }
  price *= FUEL_SURCHARGE;
  return Math.round(price * 100) / 100;
}
