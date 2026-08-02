import * as fs from "fs";
import * as path from "path";

export interface ChatletsConfig {
  provider: string;
  baseURL: string;
  apiKey: string;
  model: string;
  allowList: string[];
  allowAll: boolean;
}

const DEFAULT_CONFIG: ChatletsConfig = {
  provider: "openai",
  baseURL: "http://localhost:8080/v1",
  apiKey: "sk-fallback",
  model: "gpt-4",
  allowList: [],
  allowAll: true,
};

export function loadChatletsConfig(): ChatletsConfig {
  // Look for config/config.json at the project root
  // Walk up the directory tree to find it
  let dir = process.cwd();
  const root = "/";
  while (dir !== root) {
    const configPath = path.join(dir, "config", "config.json");
    if (fs.existsSync(configPath)) {
      try {
        const raw = fs.readFileSync(configPath, "utf-8");
        const parsed = JSON.parse(raw) as Partial<ChatletsConfig>;
        return { ...DEFAULT_CONFIG, ...parsed } as ChatletsConfig;
      } catch {
        return DEFAULT_CONFIG;
      }
    }
    dir = path.dirname(dir);
  }
  return DEFAULT_CONFIG;
}

export function getBashCommandsPrompt(config: ChatletsConfig): string {
  if (config.allowAll) {
    return "You can execute any shell command via the bash tool.";
  }
  if (config.allowList.length === 0) {
    return "You can execute no shell commands via the bash tool.";
  }
  const list = config.allowList.join(", ");
  return `You can execute these shell commands: ${list}.`;
}
