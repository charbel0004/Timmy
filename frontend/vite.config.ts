import { execFileSync } from "node:child_process";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

function releaseVersion() {
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA;
  try { return execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); }
  catch { return `build-${Date.now()}`; } // Production releases are Git archives.
}
const releaseId = releaseVersion();
export default defineConfig({
  define: { "import.meta.env.VITE_RELEASE_ID": JSON.stringify(releaseId) },
  plugins: [tailwindcss(), {
    name: "timmy-release-version",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "app-version.json", source: JSON.stringify({ version: releaseId }) });
    },
  }],
  server: {
    strictPort: true,
    // Same-origin /api in dev, matching production. Keeps cookies and the
    // API's exact-origin CSRF check working on any host, not just localhost.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
