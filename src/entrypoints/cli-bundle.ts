// Bundled entry point: prelude shims + env defaults + CLI.
declare const MACRO: { VERSION: string; ISSUES_EXPLAINER: string; [k: string]: string };
const globalAny: any = globalThis as any;
if (!globalAny.MACRO) {
  globalAny.MACRO = new Proxy({
    VERSION: '1.0',
    ISSUES_EXPLAINER: '',
  }, {
    get(t, p: string) {
      if (p in t) return (t as any)[p];
      return '';
    }
  });
}
if (!globalAny.feature) {
  (globalThis as any).feature = (_name: string) => false;
}

// No explicit URLs or API keys are baked into the binary.
// Connection settings (ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY) MUST be
// provided by the environment — normally set by the `qntelli` wrapper
// (installed by install.sh), which reads them from the huanxin dp4 config.
function setDefaultEnv(key: string, value: string) {
  if (!process.env[key]) process.env[key] = value;
}
// Model default matches the huanxin dp4 upstream; the base URL + API key are
// always supplied externally (never hardcoded here).
setDefaultEnv('ANTHROPIC_MODEL', 'dp4');
setDefaultEnv('ANTHROPIC_SMALL_FAST_MODEL', 'dp4');
setDefaultEnv('ANTHROPIC_DEFAULT_SONNET_MODEL', 'dp4');
setDefaultEnv('ANTHROPIC_DEFAULT_OPUS_MODEL', 'dp4');
setDefaultEnv('ANTHROPIC_DEFAULT_HAIKU_MODEL', 'dp4');
setDefaultEnv('CLAUDE_CODE_SUBAGENT_MODEL', 'dp4');
setDefaultEnv('CLAUDE_CODE_EFFORT_LEVEL', 'max');
// Disable telemetry & non-essential traffic so the CLI never phones home.
setDefaultEnv('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', '1');
setDefaultEnv('DISABLE_TELEMETRY', '1');
setDefaultEnv('NODE_ENV', 'production');

// Now hand off to the real CLI entrypoint.
import('./cli.tsx');
