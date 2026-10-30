/** How a prepared file left the app. The desktop shell reports how its save dialog ended; a browser only starts a download. */
export type Delivery = { state: "started" | "saved" | "cancelled" | "failed"; name: string };
type DesktopBridge = { onDownloadDone: (listener: (state: string, name: string) => void) => () => void };

function desktopBridge(): DesktopBridge | null {
  const value: unknown = Reflect.get(globalThis, "foldcvDesktop");
  return typeof value === "object" && value !== null && "onDownloadDone" in value && typeof value.onDownloadDone === "function"
    ? value as DesktopBridge : null;
}

export function deliveryState(state: string): Delivery["state"] {
  return state === "completed" ? "saved" : state === "cancelled" ? "cancelled" : "failed";
}

export function deliverFile(blob: Blob, name: string): Promise<Delivery> {
  const url = URL.createObjectURL(blob), anchor = document.createElement("a"), desktop = desktopBridge();
  anchor.href = url; anchor.download = name;
  const done = desktop ? new Promise<Delivery>(resolve => {
    const stop = desktop.onDownloadDone((state, saved) => { stop(); resolve({ state: deliveryState(state), name: saved || name }); });
  }) : Promise.resolve<Delivery>({ state: "started", name });
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  return done;
}

/** What the file dialog says once a delivery ends; a cancelled save says nothing. */
export function deliveryMessage(delivery: Delivery | null): string {
  if (delivery?.state === "saved") return `Файл сохранён: ${delivery.name}`;
  return delivery?.state === "started" ? "Скачивание началось." : "";
}
