// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { ConfigEnv, Plugin, PluginOption, UserConfig } from "vite";

const baseConfig = defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});

// The wrapper hardcodes `injectSource: { enabled: true }` on its bundled
// @tanstack/devtools-vite plugin with no config surface to disable it. That
// plugin stamps a `data-tsd-source="file:line:col"` attribute onto JSX
// elements for click-to-open-in-editor -- a dev convenience with no operator
// value, and the confirmed root cause of a real bug: it runs as an
// independent transform pass per Vite environment (client vs SSR), and
// their output can diverge, so the server-rendered and client-hydrated
// markup stop matching and React abandons hydration for the whole page. Cut
// only that one plugin from the bundle; every other devtools feature (all
// already disabled by the wrapper itself) is left untouched.
const INJECT_SOURCE_PLUGIN_NAME = "@tanstack/devtools:inject-source";

async function withoutInjectSourcePlugin(
  plugins: PluginOption[] | undefined,
): Promise<PluginOption[]> {
  if (!plugins) return [];
  const resolved = await Promise.all(plugins);
  const kept: PluginOption[] = [];
  for (const plugin of resolved) {
    if (Array.isArray(plugin)) {
      kept.push(await withoutInjectSourcePlugin(plugin));
    } else if (plugin && (plugin as Plugin).name === INJECT_SOURCE_PLUGIN_NAME) {
      continue;
    } else {
      kept.push(plugin);
    }
  }
  return kept;
}

export default async function config(env: ConfigEnv): Promise<UserConfig> {
  const resolved = await baseConfig(env);
  return { ...resolved, plugins: await withoutInjectSourcePlugin(resolved.plugins) };
}
