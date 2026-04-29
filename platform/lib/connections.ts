export type ConnectionId = "comfyui" | "openwebui" | "grok" | "prompt_guard";

export type ConnectionDef = {
  id: ConnectionId;
  label: string;
  url_var: string;
  token_var: string | null;
  token_blank_allowed: boolean;
  default_url: string | null;
};

export const CONNECTIONS: ConnectionDef[] = [
  {
    id: "comfyui",
    label: "ComfyUI",
    url_var: "COMFYUI_URL",
    token_var: null,
    token_blank_allowed: true,
    default_url: null,
  },
  {
    id: "openwebui",
    label: "OpenWebUI / Gemma",
    url_var: "OPENWEBUI_URL",
    token_var: "OPENWEBUI_API_KEY",
    token_blank_allowed: true,
    default_url: null,
  },
  {
    id: "grok",
    label: "Grok",
    url_var: "GROK_BASE_URL",
    token_var: "GROK_API_KEY",
    token_blank_allowed: false,
    default_url: "https://api.x.ai/v1",
  },
  {
    id: "prompt_guard",
    label: "Prompt Guard",
    url_var: "PROMPT_GUARD_URL",
    token_var: null,
    token_blank_allowed: true,
    default_url: null,
  },
];

export function getConnectionDef(id: string): ConnectionDef | undefined {
  return CONNECTIONS.find((c) => c.id === id);
}
