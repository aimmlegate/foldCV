// Vite needs a local entry to put the polyfills in front of the pdf.js worker.
import "./pdf-polyfills";
import "pdfjs-dist/legacy/build/pdf.worker.min.mjs";
