import { useState } from "react";
import type { EditorPhoto } from "../../contracts/generated/contracts";
import { Icon } from "../ui/Icon";
import { ImageDialog } from "../images/ImageDialog";

/** D187: the photo of the résumé in Facts, group «Кандидат»: the quiet «+ Фото» when there is none, else a small picture
 * with «Заменить» and remove. Nothing asks for a photo. */
export function PhotoControl({ photo, busy, setPhoto }: { photo: EditorPhoto | null; busy: boolean; setPhoto: (image: string | null) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  return <div className="fact-photo">
    {photo ? <><img className="fact-photo-preview" src={photo.url} alt="Фото в резюме" />
      <button type="button" className="text-button" disabled={busy} onClick={() => setOpen(true)}>Заменить</button>
      <button type="button" className="icon" aria-label="Убрать фото" title="Убрать фото" disabled={busy}
        onClick={() => void setPhoto(null).catch(() => {})}><Icon name="close" /></button></>
      : <button type="button" className="text-button fact-add" disabled={busy} onClick={() => setOpen(true)}>+ Фото</button>}
    {open && <ImageDialog title="Фото" output={{ size: 800, type: "image/jpeg" }} rounded save={image => setPhoto(image)} close={() => setOpen(false)} />}
  </div>;
}
