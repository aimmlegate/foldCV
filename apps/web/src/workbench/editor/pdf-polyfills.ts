// The legacy build of pdf.js brings newer JavaScript with it, all but these functions that Safari lacks.
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

// WebKit has no async iteration of a stream, and pdf.js reads the text of a page with it (getTextContent): without
// this the lines the resume does not show got no mark in a PDF original on macOS.
if (!(Symbol.asyncIterator in ReadableStream.prototype)) Object.defineProperty(ReadableStream.prototype, Symbol.asyncIterator, {
  configurable: true, writable: true,
  value<T>(this: ReadableStream<T>): AsyncIterableIterator<T> {
    const reader = this.getReader();
    return {
      async next() {
        const step = await reader.read();
        if (!step.done) return { done: false, value: step.value };
        reader.releaseLock();
        return { done: true, value: undefined };
      },
      // A loop left early gives the stream up, as the real iterator does.
      async return(value?: unknown) {
        await reader.cancel();
        reader.releaseLock();
        return { done: true, value };
      },
      [Symbol.asyncIterator]() { return this; },
    };
  } });
