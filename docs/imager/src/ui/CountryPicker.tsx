import React, { useMemo, useState } from 'react';
import { CountryConfig, getCountriesByName, guessCountryCode } from '../config';

interface CountryPickerProps {
  onSelect: (country: CountryConfig & { code: string }) => void;
  onBack: () => void;
}

const CountryPicker: React.FC<CountryPickerProps> = ({ onSelect, onBack }) => {
  const [search, setSearch] = useState('');
  const [selectedCode, setSelectedCode] = useState(guessCountryCode());

  const filteredCountries = useMemo(() => {
    const countries = getCountriesByName();
    if (!search.trim()) return countries;

    const query = search.toLowerCase();
    return countries.filter(
      ([code, country]) =>
        code.toLowerCase().includes(query) ||
        country.name.toLowerCase().includes(query) ||
        country.domain.toLowerCase().includes(query)
    );
  }, [search]);

  return (
    <div
      style={{
        maxWidth: '600px',
        padding: '2rem',
        backgroundColor: 'var(--bg-primary)',
        borderRadius: '1rem',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <h2 style={{ marginBottom: '0.5rem' }}>Select WiFi Country</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
        Choose where you'll use this Raspberry Pi to set the correct WiFi regulatory domain
      </p>

      <input
        type="text"
        placeholder="Search by country name, code, or domain..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: '1.5rem' }}
      />

      <div
        style={{
          height: '400px',
          overflowY: 'auto',
          border: '1px solid var(--border)',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
        }}
      >
        {filteredCountries.map(([code, country]) => (
          <div
            key={code}
            onClick={() => setSelectedCode(code)}
            style={{
              padding: '1rem',
              borderBottom: '1px solid var(--border)',
              cursor: 'pointer',
              backgroundColor: selectedCode === code ? 'var(--bg-tertiary)' : 'transparent',
              transition: 'background-color 0.2s ease',
            }}
            onMouseEnter={(e) => {
              if (selectedCode !== code) {
                (e.currentTarget as HTMLDivElement).style.backgroundColor =
                  'var(--bg-secondary)';
              }
            }}
            onMouseLeave={(e) => {
              if (selectedCode !== code) {
                (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent';
              }
            }}
          >
            <div style={{ fontWeight: '600' }}>{country.name}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Domain: {country.domain}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button onClick={onBack} style={{ flex: 1, backgroundColor: 'var(--bg-secondary)' }}>
          ← Back
        </button>
        <button
          onClick={() => {
            const selected = getCountriesByName().find(([code]) => code === selectedCode);
            if (selected) {
              onSelect({ ...selected[1], code: selected[0] });
            }
          }}
          style={{ flex: 1, backgroundColor: 'var(--primary)', color: 'white' }}
        >
          Next →
        </button>
      </div>
    </div>
  );
};

export default CountryPicker;
