/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
        "./src/**/*.{js,jsx,ts,tsx}",
        "./public/index.html"
    ],
    theme: {
        extend: {
            colors: {
                bg: "#0D1117",
                panel: "#151B24",
                bd: "#242E3D",
                gold: "#E3B341",
                green: "#3FB68B",
                red: "#E0635E",
                "text-primary": "#E9ECF2",
                "text-secondary": "#8A94A6",
                background: 'hsl(var(--background))',
                foreground: 'hsl(var(--foreground))',
                card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
                popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
                primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
                secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
                muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
                accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
                destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
                border: 'hsl(var(--border))',
                input: 'hsl(var(--input))',
                ring: 'hsl(var(--ring))',
            },
            fontFamily: {
                sans: ['Outfit', 'system-ui', 'sans-serif'],
                mono: ['"JetBrains Mono"', 'monospace'],
            },
            borderRadius: {
                'card': '14px',
                lg: 'var(--radius)',
                md: 'calc(var(--radius) - 2px)',
                sm: 'calc(var(--radius) - 4px)'
            },
            boxShadow: {
                'glow-green': '0 0 30px rgba(63,182,139,0.35)',
                'glow-red': '0 0 30px rgba(224,99,94,0.35)',
                'glow-gold': '0 0 24px rgba(227,179,65,0.30)',
            },
            keyframes: {
                'pulse-dot': {
                    '0%, 100%': { opacity: 1 },
                    '50%': { opacity: 0.4 },
                },
                'fade-in': {
                    'from': { opacity: 0, transform: 'translateY(6px)' },
                    'to': { opacity: 1, transform: 'translateY(0)' },
                },
            },
            animation: {
                'pulse-dot': 'pulse-dot 1.6s ease-in-out infinite',
                'fade-in': 'fade-in 0.35s ease-out both',
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
};
