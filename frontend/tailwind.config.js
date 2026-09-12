/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#172033',
        canvas: '#f6f8fb',
        brand: '#2563eb',
      },
      boxShadow: {
        soft: '0 12px 40px rgba(23, 32, 51, 0.07)',
      },
    },
  },
  plugins: [],
}
