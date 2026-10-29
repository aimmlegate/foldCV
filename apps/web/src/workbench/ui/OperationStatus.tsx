import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { Spinner } from "./Spinner";

export { Spinner };

export function elapsedText(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function Elapsed({ startedAt, finishedAt, active = true }: { startedAt?: string | number | null | undefined;
  finishedAt?: string | number | null | undefined; active?: boolean }) {
  const [mountedAt] = useState(Date.now), [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const start = typeof startedAt === "number" ? startedAt : Date.parse(startedAt ?? "");
  const end = typeof finishedAt === "number" ? finishedAt : Date.parse(finishedAt ?? "");
  const label = elapsedText((Number.isFinite(end) ? end : now) - (Number.isFinite(start) ? start : mountedAt));
  return <time className="operation-elapsed" role="timer" aria-live="off" aria-label={`Прошло ${label}`}>{label}</time>;
}

export function OperationStatus({ label, detail, state = "working", timed = false, startedAt, className = "" }: {
  label: string; detail?: string | undefined; state?: "working" | "waiting" | "success" | "error";
  timed?: boolean; startedAt?: string | number | null | undefined; className?: string;
}) {
  return <div className={`operation-status ${className}`} data-state={state}>
    {state === "working" || state === "waiting" ? <Spinner /> : <Icon name={state === "success" ? "check" : "info"} />}
    <span className="operation-copy"><span role="status">{label}</span>{detail && <small>{detail}</small>}</span>
    {timed && <Elapsed startedAt={startedAt} active={state === "working" || state === "waiting"} />}
  </div>;
}
