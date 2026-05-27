/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Coffee-shop warm palette for the storefront.
        coffee: {
          50:  "#faf6f0",
          100: "#f3ebde",
          200: "#e6d3b7",
          300: "#d5b389",
          400: "#bd8d5a",
          500: "#a06f3d",
          600: "#825530",
          700: "#684228",
          800: "#503321",
          900: "#3a2517",
        },
        // Cool slate palette for the ops dashboard.
        ops: {
          50:  "#f4f6fa",
          100: "#e7ecf3",
          200: "#cbd5e1",
          300: "#94a3b8",
          400: "#64748b",
          500: "#475569",
          600: "#334155",
          700: "#1e293b",
          800: "#0f172a",
          900: "#020617",
        },
        accent: {
          green: "#10b981",
          amber: "#f59e0b",
          red:   "#ef4444",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "Menlo", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "slide-in":   "slideIn 0.3s ease-out",
        "fade-in":    "fadeIn 0.4s ease-out",
      },
      keyframes: {
        slideIn: {
          "0%":   { transform: "translateX(20px)", opacity: "0" },
          "100%": { transform: "translateX(0)",    opacity: "1" },
        },
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
