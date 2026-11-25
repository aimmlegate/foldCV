import type { DateWarning } from "../../projects/api";

/** How long the dialog waits after the last date change before it asks Python for warnings (D182, J6-b). */
export const dateCheckDelay = 400;

type Timers = { set: (run: () => void, delay: number) => unknown; clear: (timer: unknown) => void };
const browserTimers: Timers = { set: (run, delay) => setTimeout(run, delay), clear: timer => clearTimeout(timer as ReturnType<typeof setTimeout>) };

/** The date dialog's check before Save: one call after the last change, none while no date changed, and only the answer
 * to the newest values shows. A failed or late check shows nothing; nothing here can block Save. */
export function dateChecker({ check, show, delay = dateCheckDelay, timers = browserTimers }: {
  check: (values: Record<string, string>) => Promise<readonly DateWarning[]>;
  show: (warnings: readonly DateWarning[]) => void;
  delay?: number; timers?: Timers;
}) {
  let timer: unknown, sequence = 0;
  return {
    /** `read` gives the form's values when the delay ends, and whether a date differs from the dialog's start. */
    schedule(read: () => { values: Record<string, string>; changed: boolean } | null) {
      if (timer !== undefined) timers.clear(timer);
      timer = timers.set(() => {
        timer = undefined;
        const form = read();
        if (!form) return;
        const mine = ++sequence;
        if (!form.changed) { show([]); return; }
        check(form.values).then(found => { if (mine === sequence) show(found); }, () => { if (mine === sequence) show([]); });
      }, delay);
    },
    /** The dialog closed: no further call, and a late answer shows nothing. */
    dispose() {
      if (timer !== undefined) timers.clear(timer);
      timer = undefined;
      sequence++;
    },
  };
}

/** The dialog's lines for Python's warnings: the other job's row name with its period, or the end before the start. */
export function dateWarningLines(warnings: readonly DateWarning[], jobName: (recordId: string) => string, overlap: (names: string[]) => string): string[] {
  return [...new Set(warnings.map(item => item.kind === "reversed" ? "Окончание раньше начала"
    : `${overlap([jobName(item.recordId)])} (${item.period})`))];
}
