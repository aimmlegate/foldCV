import { useEffect, useState } from "react";
import { globalJobs } from "./global";

export function useGlobalJobs() {
  const registry = globalJobs(), [view, setView] = useState(registry.view);
  useEffect(() => registry.subscribe(setView), [registry]);
  return { registry, view };
}
