export const applicationTabLock = "foldcv:active-tab";
export type TabLease = { release: () => void };
export type TabLockRequest = (name: string, work: (available: boolean) => Promise<void>) => Promise<void>;
let activeOwner: symbol | null = null;
export function applicationTabActive(): boolean { return activeOwner !== null; }

function browserRequest(): TabLockRequest | null {
  if (typeof navigator === "undefined" || !navigator.locks) return null;
  return async (name, work) => {
    await navigator.locks.request(name, { mode: "exclusive", ifAvailable: true }, lock => work(lock !== null));
  };
}

/** Hold one browser lock before mounting any application controls or API clients. */
export function claimApplicationTab(request: TabLockRequest | null = browserRequest()): Promise<TabLease | null> {
  if (!request) return Promise.reject(new Error("TAB_LOCK_UNAVAILABLE"));
  let release = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  return new Promise((resolve, reject) => {
    void request(applicationTabLock, async available => {
      if (!available) { resolve(null); return; }
      const owner = Symbol(); activeOwner = owner;
      resolve({ release: () => { if (activeOwner === owner) activeOwner = null; release(); } });
      await held;
    }).catch(reject);
  });
}
