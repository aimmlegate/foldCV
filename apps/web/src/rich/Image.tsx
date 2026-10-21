import { errorMessage } from "../errors/messages";
import { createContext, useContext, useRef, useState } from "react";
import { createReactBlockSpec } from "@blocknote/react";

export const ImageActions = createContext<{ source: (asset: string) => string; upload: (file: File, block: string) => Promise<void>; cancel: (block: string) => void }>({
  source: () => "", upload: async () => {}, cancel: () => {},
});
export const image = createReactBlockSpec({ type: "image", content: "inline", propSchema: {
  assetId: { default: "" }, alt: { default: "" }, width: { default: 160 }, height: { default: 80 },
  textAlignment: { default: "left", values: ["left", "center", "right"] },
} }, { toExternalHTML: ({ block, contentRef }) => <figure data-asset-id={block.props.assetId}>
  <img alt={block.props.alt} width={block.props.width * 4 / 3} height={block.props.height * 4 / 3} /><figcaption ref={contentRef} /></figure>,
  render: function LocalImage({ block, editor, contentRef }) {
  const actions = useContext(ImageActions), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const label = block.props.assetId ? "Заменить изображение" : "Выбрать изображение";
  return <figure className="cv-image" style={{ textAlign: block.props.textAlignment }}>
    <div contentEditable={false}>
      {block.props.assetId && <img src={actions.source(block.props.assetId)} alt={block.props.alt}
        style={{ width: `${block.props.width}pt`, maxWidth: "100%", height: "auto" }} />}
      <div className="cv-image-controls" data-uir-engine-ui="true">
        <button type="button" className="text-button" disabled={busy} onClick={() => fileInput.current?.click()}>{label}</button>
        <input ref={fileInput} hidden aria-label={label} type="file" accept="image/png,image/jpeg,image/webp" disabled={busy}
          onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
            if (file) { setBusy(true); setError(""); void actions.upload(file, block.id).catch(error => setError(error instanceof Error ? error.message : "IMAGE_INVALID")).finally(() => setBusy(false)); } }} />
        {busy && <button onClick={() => actions.cancel(block.id)}>Остановить загрузку</button>}
        {block.props.assetId && <><label>Описание<input aria-label="Описание изображения" value={block.props.alt}
          onChange={event => editor.updateBlock(block.id, { props: { alt: event.currentTarget.value } })} /></label>
          <label>Ширина<input aria-label="Ширина изображения" type="number" min="1" value={block.props.width}
            onChange={event => { const width = Number(event.currentTarget.value); if (width > 0 && Number.isFinite(width))
              editor.updateBlock(block.id, { props: { width, height: width * block.props.height / block.props.width } }); }} /></label></>}
        {error && <span role="alert">{errorMessage(error)}</span>}
      </div>
    </div><figcaption ref={contentRef} />
  </figure>;
} });
