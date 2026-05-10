/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/*.py",
    "./apps/**/*.html",
    "./static/**/*.js"
  ],
  theme: {
    extend: {
      fontFamily: {
        'sans': ['"Times New Roman"', 'Times', 'serif'],
      },
      colors: {
        'maroon': {
          DEFAULT: '#5B1525',
          dark: '#3D0C15',
          deep: '#2D0810',
          accent: '#7A2E3E',
          light: '#EDD8DC'
        },
        gold: { DEFAULT: '#D4A843', light: '#E8C96A' },
        cream: { DEFAULT: '#FDF8F0', dark: '#F5EDE0' },
        dark: { DEFAULT: '#1A1A2E' },
      }
    },
  },
  plugins: [],
}