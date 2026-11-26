import { useEffect, useRef, useState } from "react";
import Cropper from "react-easy-crop";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { errorMessage } from "../../errors/messages";
import { acceptedTypes, cropImage, pickProblem, type CropArea, type ImageOutput } from "./crop";

/** D187: the one image dialog: pick a file, move it in a fixed square frame, zoom, save. The photo's frame has rounded
 * corners; an icon's is plain. The result goes to `save` as base64; Python checks it again. */
export function ImageDialog({ title, output, rounded, save, close }: {
  title: string; output: ImageOutput; rounded: boolean; save: (image: string) => Promise<void>; close: () => void;
}) {
  const input = useRef<HTMLInputElement>(null), image = useRef<HTMLImageElement | null>(null);
  const [source, setSource] = useState<string | null>(null), [problem, setProblem] = useState("");
  const [crop, setCrop] = useState({ x: 0, y: 0 }), [zoom, setZoom] = useState(1), [area, setArea] = useState<CropArea | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);
  function pick(file: File | undefined) {
    if (!file) return;
    const refused = pickProblem(file);
    if (refused) { setProblem(refused); return; }
    const url = URL.createObjectURL(file), probe = new Image();
    probe.onload = () => { image.current = probe; setProblem(""); setZoom(1); setCrop({ x: 0, y: 0 }); setSource(url); };
    probe.onerror = () => { URL.revokeObjectURL(url); setProblem("Не удалось прочитать файл. Выберите другое изображение."); };
    probe.src = url;
  }
  async function confirm() {
    if (!image.current || !area) return;
    setBusy(true); setProblem("");
    try { await save(await cropImage(image.current, area, output)); close(); }
    catch (error) { setProblem(error instanceof Error && error.message.startsWith("IMAGE_") ? errorMessage(error.message) : errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <Dialog open close={() => { if (!busy) close(); }} title={title}>
    <div className={rounded ? "image-dialog rounded" : "image-dialog"}>
      {source ? <div className="image-crop">
        <Cropper image={source} crop={crop} zoom={zoom} aspect={1} minZoom={1} maxZoom={4} showGrid={false} keyboardStep={8}
          onCropChange={setCrop} onZoomChange={setZoom} onCropComplete={(_area, pixels) => setArea(pixels)} />
      </div> : <button type="button" className="image-pick" disabled={busy} onClick={() => input.current?.click()}>Выбрать изображение</button>}
      {source && <label className="image-zoom">Масштаб<input type="range" min={1} max={4} step={0.05} value={zoom} disabled={busy}
        aria-label="Масштаб" onChange={event => setZoom(Number(event.currentTarget.value))} /></label>}
      {source && <button type="button" className="text-button" disabled={busy} onClick={() => input.current?.click()}>Другой файл</button>}
      <input ref={input} hidden type="file" accept={acceptedTypes} aria-label="Файл изображения"
        onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; pick(file); }} />
      {problem && <p className="notice error" role="alert">{problem}</p>}
    </div>
    <div className="dialog-actions"><Button disabled={busy} onClick={close}>Отмена</Button>
      <Button variant="primary" busy={busy} busyLabel="Сохраняем…" disabled={!source || !area} onClick={() => void confirm()}>Сохранить</Button></div>
  </Dialog>;
}
