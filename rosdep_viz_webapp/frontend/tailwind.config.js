/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        display: ['Space Grotesk', 'system-ui', 'sans-serif'],
      },
      colors: {
        surface: {
          DEFAULT: '#0f1419',
          elevated: '#1a2332',
          muted: '#16202a',
        },
        accent: {
          DEFAULT: '#22d3ee',
          muted: '#0891b2',
          dim: '#0e7490',
        },
        edge: '#334155',
      },
    },
  },
  plugins: [],
}
