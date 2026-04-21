import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#10212b",
        mist: "#f4efe7",
        sand: "#dcc7a1",
        pine: "#184d47",
        coral: "#d76c4e",
        sun: "#f1b24a",
        slate: "#577180",
      },
      boxShadow: {
        card: "0 20px 60px rgba(16, 33, 43, 0.12)",
      },
      borderRadius: {
        xl2: "1.5rem",
      },
      fontFamily: {
        display: ["Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Georgia", "serif"],
        body: ["Avenir Next", "Segoe UI", "Helvetica Neue", "sans-serif"],
      },
      backgroundImage: {
        "hero-radial":
          "radial-gradient(circle at top left, rgba(241,178,74,0.25), transparent 30%), radial-gradient(circle at top right, rgba(215,108,78,0.2), transparent 28%), linear-gradient(180deg, #fffaf1 0%, #f4efe7 52%, #eef4f4 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
