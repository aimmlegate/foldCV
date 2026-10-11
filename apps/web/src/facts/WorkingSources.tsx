import type { WorkingDraft } from "./working";

const control = "rounded border border-outline bg-panel px-3 py-2 text-content hover:bg-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function WorkingSources({ working }: { working: WorkingDraft }) {
  function download(index: number) {
    const source = working.sources[index];
    if (!source) return;
    const url = URL.createObjectURL(new Blob([Uint8Array.from(source.originalBytes)], { type: source.entry.result.mimeType }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = source.entry.result.originalName;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return <div className="mt-4 space-y-3">
    {working.sources.map(({ entry }, index) => <details key={entry.result.sourceId} className="rounded border border-outline p-3">
      <summary className="cursor-pointer font-semibold">{entry.result.originalName} · {entry.result.units.length} фрагментов · {entry.result.gaps.length} пробелов</summary>
      <button type="button" className={`${control} mt-2`} onClick={() => download(index)}>Скачать неизменённый оригинал</button>
      <div className="mt-2 max-h-72 space-y-2 overflow-auto text-sm">{entry.result.units.map((unit) => <p key={unit.id} className="whitespace-pre-wrap break-words border-l-2 border-outline pl-2">
        <span className="text-xs text-muted">{unit.id} · {unit.location.kind}</span><br />{unit.text}
        {entry.overlays[`unit:${unit.id}`] && <span className="block text-accent">Исправление: {entry.overlays[`unit:${unit.id}`]}</span>}
      </p>)}{entry.result.gaps.map((gap, gapIndex) => <p key={`gap:${gapIndex}`} className="border-l-2 border-danger pl-2">
        {gap.code} · {gap.location.kind}{entry.overlays[`gap:${gapIndex}`] && <span className="block">Ваш текст: {entry.overlays[`gap:${gapIndex}`]}</span>}
      </p>)}</div>
    </details>)}
  </div>;
}
