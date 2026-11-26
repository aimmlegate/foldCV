/** D187: the cropped square at a fixed size, drawn in the browser; Python checks the result again. */
export type CropArea = { x: number; y: number; width: number; height: number };
export type ImageOutput = { size: number; type: "image/jpeg" | "image/png" };

/** Files above this size are refused before they are read (G1-d). */
export const pickLimit = 20 * 1024 * 1024;
/** Raster types the web views read; SVG is no input in this task. */
export const acceptedTypes = "image/jpeg,image/png,image/webp,image/gif,image/bmp,image/avif";

export function pickProblem(file: { size: number; type: string }): string | null {
  if (file.size > pickLimit) return "Файл больше 20 МБ. Выберите файл меньше.";
  if (!file.type.startsWith("image/") || file.type === "image/svg+xml") return "Это не изображение. Выберите JPEG, PNG или WebP.";
  return null;
}

/** The sizes a large reduction steps through, halving each time, so the canvas never scales down by more than half at once
 * (one large step gives a grainy picture). */
export function halvings(source: number, target: number): number[] {
  const steps: number[] = [];
  for (let size = source; size / 2 > target; size = Math.round(size / 2)) steps.push(Math.round(size / 2));
  return [...steps, target];
}

/** The crop of a decoded image as base64 of the output type. The browser applies the file's EXIF orientation when it
 * decodes, so the picture stands upright; the canvas writes no metadata. */
export async function cropImage(image: HTMLImageElement, area: CropArea, output: ImageOutput): Promise<string> {
  let canvas = document.createElement("canvas");
  canvas.width = canvas.height = Math.max(1, Math.round(area.width));
  let context = canvas.getContext("2d");
  if (!context) throw new Error("IMAGE_INVALID");
  if (output.type === "image/jpeg") { context.fillStyle = "#ffffff"; context.fillRect(0, 0, canvas.width, canvas.height); }
  context.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, canvas.width, canvas.height);
  for (const size of halvings(canvas.width, Math.min(output.size, canvas.width))) {
    const next = document.createElement("canvas");
    next.width = next.height = size;
    context = next.getContext("2d");
    if (!context) throw new Error("IMAGE_INVALID");
    context.imageSmoothingEnabled = true; context.imageSmoothingQuality = "high";
    context.drawImage(canvas, 0, 0, size, size);
    canvas = next;
  }
  const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, output.type, 0.9));
  if (!blob) throw new Error("IMAGE_INVALID");
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let text = "";
  for (let index = 0; index < bytes.length; index += 0x8000) text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(text);
}
