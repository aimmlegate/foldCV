import catalog from "../../../../contracts/error-messages.ru.json" with { type: "json" };

const codes: Readonly<Record<string, string>> = catalog.codes;
const messages: Readonly<Record<string, string>> = catalog.messages;
export const defaultErrorMessage = catalog.messages.generic;

export function knownErrorMessage(code: string): string | null {
  const key = Object.hasOwn(codes, code) ? codes[code] : undefined;
  return key && Object.hasOwn(messages, key) ? messages[key] ?? null : null;
}

function readable(value: string): boolean {
  return value.length <= 2000 && /[А-Яа-яЁё]/u.test(value)
    && !value.split(/[^\p{L}\p{N}_-]+/u).some(token => Object.hasOwn(codes, token))
    && !/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/u.test(value)
    && !/(?:\/(?:Users|private|tmp|home|var|etc|opt|usr)\/|[A-Za-z]:\\|(?:^|\n)\s*at\s+\S|Traceback|Error:|https?:\/\/)/u.test(value);
}

/** A refused export names its fragment, because the refused character may be one nobody can see. */
function fragmentNote(error: unknown): string {
  const body = typeof error === "object" && error !== null && "body" in error ? error.body : null;
  const fragment = typeof body === "object" && body !== null && "fragment" in body ? body.fragment : null;
  return typeof fragment === "string" && fragment ? ` Фрагмент: «${fragment}».` : "";
}

/** Translate only at presentation boundaries; callers keep the original error for recovery. */
export function errorMessage(error: unknown, fallback = defaultErrorMessage): string {
  let value: string | null = typeof error === "string" ? error : null;
  if (typeof error === "object" && error !== null) {
    if ("code" in error && typeof error.code === "string") value = error.code;
    else if (error instanceof Error) value = error.message;
    if ("name" in error && error.name === "AbortError") return catalog.messages.cancelled;
  }
  if (value) {
    const known = knownErrorMessage(value);
    if (known) return known + fragmentNote(error);
    if (/Failed to fetch|NetworkError|Load failed|fetch failed|ECONNREFUSED/u.test(value)) return catalog.messages.connection;
    if (readable(value)) return value;
  }
  return readable(fallback) ? fallback : defaultErrorMessage;
}

export function messageText(value: string, fallback = defaultErrorMessage): string {
  return value ? errorMessage(value, fallback) : "";
}
