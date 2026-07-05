/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        arabic: ['Noto Naskh Arabic', 'Amiri', 'serif'],
        ui: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        ink:    { DEFAULT: '#1a1209', light: '#3d2e14' },
        parch:  { DEFAULT: '#f5f0e8', dark: '#e8dfc8', deeper: '#d4c9a8' },
        gold:   { DEFAULT: '#b8922a', light: '#d4a93c', dark: '#8a6a1a' },
        rust:   { DEFAULT: '#8b3a2a', light: '#b04d39' },
        sage:   { DEFAULT: '#4a6741', light: '#6a9460' },
      },
      borderRadius: { 'sm': '3px' },
    },
  },
  plugins: [],
}
