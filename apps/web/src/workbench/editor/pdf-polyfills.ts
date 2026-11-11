// The legacy build of pdf.js brings newer JavaScript with it, all but these two functions of Safari 17.4.
// The page and the PDF worker each load this file: a worker has its own globals.

if (!("withResolvers" in Promise)) Object.defineProperty(Promise, "withResolvers", { configurable: true, writable: true,
  value<T>(this: PromiseConstructor) {
    let resolve!: (value: T | PromiseLike<T>) => void, reject!: (reason?: unknown) => void;
    const promise = new this<T>((fulfil, fail) => { resolve = fulfil; reject = fail; });
    return { promise, resolve, reject };
  } });

// The real one also detaches its buffer; pdf.js drops that buffer right after the call.
if (!("transferToFixedLength" in ArrayBuffer.prototype)) Object.defineProperty(ArrayBuffer.prototype, "transferToFixedLength", {
  configurable: true, writable: true,
  value(this: ArrayBuffer, length = this.byteLength) {
    const copy = new ArrayBuffer(length);
    new Uint8Array(copy).set(new Uint8Array(this, 0, Math.min(length, this.byteLength)));
    return copy;
  } });
