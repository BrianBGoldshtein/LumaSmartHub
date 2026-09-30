import type { Snapshot } from "./types";

export async function fetchSnapshot(): Promise<Snapshot> {
  const response = await fetch("/api/v1/state");
  if (!response.ok) throw new Error(`Luma API returned ${response.status}`);
  return response.json();
}

export async function sendCommand(name: string, value?: unknown): Promise<Snapshot> {
  const response = await fetch("/api/v1/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, value, source: "touchscreen" }),
  });
  if (!response.ok) throw new Error(`Command failed with ${response.status}`);
  return (await response.json()).snapshot;
}

export function watchSnapshots(onSnapshot: (snapshot: Snapshot) => void, onDisconnect?: () => void, onAction?: (action: {name:string;page?:Snapshot["state"]["active_page"];overlay?:string})=>void): () => void {
  let stopped = false;
  let socket: WebSocket | undefined;
  let retry: number | undefined;
  const connect = () => {
    if (stopped) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/api/v1/events`);
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.data) onSnapshot(message.data);
      if (message.action) onAction?.(message.action);
    };
    socket.onclose = () => {
      if (!stopped) onDisconnect?.();
      if (!stopped) retry = window.setTimeout(connect, 1800);
    };
  };
  connect();
  return () => {
    stopped = true;
    if (retry) clearTimeout(retry);
    socket?.close();
  };
}
