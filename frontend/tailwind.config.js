/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        glass: {
          50: 'rgba(255,255,255,0.06)',
          100: 'rgba(255,255,255,0.10)',
          200: 'rgba(255,255,255,0.16)',
          300: 'rgba(255,255,255,0.24)',
          400: 'rgba(255,255,255,0.32)',
          500: 'rgba(255,255,255,0.40)',
          ring: 'rgba(255,255,255,0.12)',
        },
        ink: {
          50: '#f4f6fb',
          100: '#dde2ee',
          200: '#b5bdcf',
          300: '#7c879c',
          400: '#525c6f',
          500: '#363d4d',
          600: '#23293b',
          700: '#181d2c',
          800: '#10131e',
          900: '#080a13',
        },
      },
      boxShadow: {
        glass: '0 8px 32px 0 rgba(0, 0, 0, 0.35)',
        glow: '0 0 30px rgba(124, 209, 255, 0.4)',
      },
      backdropBlur: {
        xs: '2px',
      },
      fontFamily: {
        display: ['"SF Pro Display"', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', '"SF Pro Text"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      animation: {
        'pulse-soft': 'pulseSoft 3s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
        'shimmer': 'shimmer 2.5s linear infinite',
      },
      keyframes: {
        pulseSoft: {
          '0%, 100%': { opacity: '0.85', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.03)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
};
