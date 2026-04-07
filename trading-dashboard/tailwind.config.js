/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './dashboard/**/*.py',
    './home/**/*.py',
    './search/**/*.py',
    './theme/**/*.py',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1E293B',
        secondary: '#64748B',
        accent: '#3B82F6',
        background: '#020617',
      },
    },
  },
  plugins: [],
}
