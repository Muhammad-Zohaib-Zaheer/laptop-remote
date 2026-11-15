import { defineConfig } from "vite";

// `npm run build` writes the app to dist/, which the laptop's server sends to the phone.
export default defineConfig({ esbuild: { jsx: "automatic" } }); // JSX without the React plugin
