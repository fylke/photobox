export type PiModel = 'pi3' | 'pi4' | 'pi5';

export interface PiModelConfig {
  name: string;
  imageName: string;
  imageSizeBytes: number;
  imageSizeGB: number;
  minSDCardGB: number;
  recommendedSDCardGB: number;
  specs: string;
}

export interface CountryConfig {
  name: string;
  domain: string;
}

export const PI_MODELS: Record<PiModel, PiModelConfig> = {
  pi3: {
    name: 'Raspberry Pi 3',
    imageName: 'photobox-pi3.img.xz',
    imageSizeBytes: 2516582400,
    imageSizeGB: 2.4,
    minSDCardGB: 4,
    recommendedSDCardGB: 8,
    specs: '1 GB RAM, WiFi, Ethernet',
  },
  pi4: {
    name: 'Raspberry Pi 4',
    imageName: 'photobox-pi4.img.xz',
    imageSizeBytes: 4516582400,
    imageSizeGB: 4.2,
    minSDCardGB: 8,
    recommendedSDCardGB: 16,
    specs: '2-8 GB RAM, WiFi, Ethernet',
  },
  pi5: {
    name: 'Raspberry Pi 5',
    imageName: 'photobox-pi5.img.xz',
    imageSizeBytes: 5516582400,
    imageSizeGB: 5.1,
    minSDCardGB: 16,
    recommendedSDCardGB: 32,
    specs: '4-8 GB RAM, WiFi, Ethernet',
  },
};

export const COUNTRIES: Record<string, CountryConfig> = {
  GB: { name: 'United Kingdom', domain: 'GB' },
  US: { name: 'United States', domain: 'US' },
  CA: { name: 'Canada', domain: 'CA' },
  AU: { name: 'Australia', domain: 'AU' },
  DE: { name: 'Germany', domain: 'DE' },
  FR: { name: 'France', domain: 'FR' },
  IT: { name: 'Italy', domain: 'IT' },
  ES: { name: 'Spain', domain: 'ES' },
  NL: { name: 'Netherlands', domain: 'NL' },
  BE: { name: 'Belgium', domain: 'BE' },
  CH: { name: 'Switzerland', domain: 'CH' },
  AT: { name: 'Austria', domain: 'AT' },
  SE: { name: 'Sweden', domain: 'SE' },
  NO: { name: 'Norway', domain: 'NO' },
  DK: { name: 'Denmark', domain: 'DK' },
  FI: { name: 'Finland', domain: 'FI' },
  PL: { name: 'Poland', domain: 'PL' },
  CZ: { name: 'Czech Republic', domain: 'CZ' },
  SK: { name: 'Slovakia', domain: 'SK' },
  HU: { name: 'Hungary', domain: 'HU' },
  RO: { name: 'Romania', domain: 'RO' },
  GR: { name: 'Greece', domain: 'GR' },
  PT: { name: 'Portugal', domain: 'PT' },
  JP: { name: 'Japan', domain: 'JP' },
  CN: { name: 'China', domain: 'CN' },
  IN: { name: 'India', domain: 'IN' },
  BR: { name: 'Brazil', domain: 'BR' },
  MX: { name: 'Mexico', domain: 'MX' },
  ZA: { name: 'South Africa', domain: 'ZA' },
  NZ: { name: 'New Zealand', domain: 'NZ' },
  SG: { name: 'Singapore', domain: 'SG' },
  HK: { name: 'Hong Kong', domain: 'HK' },
  TW: { name: 'Taiwan', domain: 'TW' },
  TH: { name: 'Thailand', domain: 'TH' },
  MY: { name: 'Malaysia', domain: 'MY' },
  KR: { name: 'South Korea', domain: 'KR' },
};

export function getCountriesByName(): Array<[string, CountryConfig]> {
  return Object.entries(COUNTRIES).sort((a, b) => a[1].name.localeCompare(b[1].name));
}

export function getCountryByCode(code: string): CountryConfig | undefined {
  return COUNTRIES[code.toUpperCase()];
}

export function guessCountryCode(): string {
  const browserLocale = navigator.language.split('-')[1];
  if (browserLocale && COUNTRIES[browserLocale]) {
    return browserLocale;
  }
  return 'GB';
}
