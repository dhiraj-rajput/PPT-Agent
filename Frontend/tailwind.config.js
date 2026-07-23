/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Primary neutral scale - near-black/onyx.
        onyx: {
          50: '#f3f0f5',
          100: '#e8e1ea',
          200: '#d1c3d5',
          300: '#b9a5c0',
          400: '#a287ab',
          500: '#8b6996',
          600: '#6f5478',
          700: '#533f5a',
          800: '#382a3c',
          900: '#1c151e',
          950: '#130f15',
        },
        // Legacy alias kept so existing `navy-*` classes across the app render in the
        // new onyx/black palette without needing to touch every file.
        navy: {
          950: '#130f15',
          900: '#1c151e',
          800: '#382a3c',
          700: '#533f5a',
        },
        // Legacy alias - primary brand/action color now maps to onyx (near-black) per
        // the "primarily black or onyx" brand direction.
        brand: {
          50: '#f3f0f5',
          100: '#e8e1ea',
          500: '#1c151e',
          600: '#130f15',
          700: '#0a070b',
        },
        amaranth: {
          50: '#fce8ee',
          100: '#fad1dc',
          200: '#f4a4b9',
          300: '#ef7696',
          400: '#ea4873',
          500: '#e41b50',
          600: '#b71540',
          700: '#891030',
          800: '#5b0b20',
          900: '#2e0510',
          950: '#20040b',
        },
        tomato: {
          50: '#fdeae7',
          100: '#fbd5d0',
          200: '#f8aaa0',
          300: '#f48071',
          400: '#f15641',
          500: '#ed2b12',
          600: '#be230e',
          700: '#8e1a0b',
          800: '#5f1107',
          900: '#2f0904',
          950: '#210602',
        },
        'tuscan-sun': {
          50: '#fef8e6',
          100: '#fdf1ce',
          200: '#fce29c',
          300: '#fad46b',
          400: '#f9c639',
          500: '#f7b708',
          600: '#c69306',
          700: '#946e05',
          800: '#634903',
          900: '#312502',
          950: '#231a01',
        },
        'pacific-blue': {
          50: '#ebf6f9',
          100: '#d8eef3',
          200: '#b0dde8',
          300: '#89cbdc',
          400: '#62bad0',
          500: '#3ba9c4',
          600: '#2f879d',
          700: '#236576',
          800: '#17444f',
          900: '#0c2227',
          950: '#08181b',
        },
        accent: {
          orange: '#ed2b12',
          teal: '#2f879d',
          rose: '#e41b50',
          amber: '#f7b708',
          sky: '#3ba9c4',
        }
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(19, 15, 21, 0.06), 0 1px 3px rgba(19, 15, 21, 0.08)',
        soft: '0 8px 24px rgba(19, 15, 21, 0.12)',
      },
      borderRadius: {
        xl2: '1.25rem',
      }
    },
  },
  plugins: [],
}
