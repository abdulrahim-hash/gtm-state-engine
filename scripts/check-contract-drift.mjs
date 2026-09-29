import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const artifacts = [
  resolve("packages/contracts/openapi.json"),
  resolve("packages/contracts/src/generated/api.ts"),
];
const before = new Map(artifacts.map((artifact) => [artifact, readFileSync(artifact)]));
const command = process.platform === "win32" ? "cmd.exe" : "npm";
const args =
  process.platform === "win32"
    ? ["/d", "/s", "/c", "npm run contracts:generate"]
    : ["run", "contracts:generate"];
const generation = spawnSync(command, args, {
  cwd: process.cwd(),
  encoding: "utf8",
  stdio: "inherit",
});

if (generation.error) {
  console.error(generation.error.message);
  process.exit(1);
}

if (generation.status !== 0) {
  process.exit(generation.status ?? 1);
}

const changed = artifacts.filter((artifact) => !before.get(artifact)?.equals(readFileSync(artifact)));
if (changed.length > 0) {
  console.error("Generated API contracts are stale:");
  for (const artifact of changed) {
    console.error(`- ${artifact}`);
  }
  process.exit(1);
}

console.log("Generated API contracts are current.");
