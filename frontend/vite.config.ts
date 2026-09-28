import { readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev only: MOCK_REGISTER_CHANGES=1 answers /api/register-changes from dev/register-changes.json
// until the backend has the endpoint. API_URL points the proxy at another backend port.
function mockRegisterChanges(req: IncomingMessage, res: ServerResponse): false | undefined {
  if (!process.env.MOCK_REGISTER_CHANGES || !req.url?.startsWith("/api/register-changes")) return undefined;
  res.setHeader("Content-Type", "application/json");
  res.end(readFileSync(new URL("./dev/register-changes.json", import.meta.url)));
  return false;
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: process.env.API_URL ?? "http://127.0.0.1:8000", changeOrigin: true, bypass: mockRegisterChanges },
    },
  },
});
