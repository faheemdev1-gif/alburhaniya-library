/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        // The reading face is a real Naskh book type; the chrome stays on a
        // lighter face so it never competes with the text block.
        reading: ['Amiri', 'Noto Naskh Arabic', 'serif'],
        arabic: ['Noto Naskh Arabic', 'Amiri', 'serif'],
        display: ['Reem Kufi', 'Noto Naskh Arabic', 'sans-serif'],
        ui: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Kept for any older markup; new work reads the CSS variables in
        // index.css so the night theme can swap them wholesale.
        ink: { DEFAULT: '#211a11', light: '#3d2e14' },
        parch: { DEFAULT: '#f7f3ea', dark: '#efe7d5', deeper: '#e6dcc6' },
        gold: { DEFAULT: '#b8922a', light: '#d9bf7a', dark: '#8a6a1a' },
        rubric: { DEFAULT: '#9d3520', light: '#c25c42' },
        rust: { DEFAULT: '#9d3520', light: '#c25c42' },
        sage: { DEFAULT: '#4c6b46', light: '#8fae87' },
      },
      borderRadius: { sm: '3px' },
    },
  },
  plugins: [],
}
