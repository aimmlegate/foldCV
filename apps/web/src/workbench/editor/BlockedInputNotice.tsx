/** Unsaved input the queue cannot send: the user keeps it or returns to the saved text, and either choice opens the queue. */
export function BlockedInputNotice({ text, keep, discard }: { text: string; keep: () => void; discard: () => void }) {
  return <div className="notice warning" role="alert">
    <p>{text}</p>
    <button type="button" onClick={keep}>Сохранить мой текст</button>
    <button type="button" className="text-button" onClick={discard}>Вернуть сохранённый текст</button>
  </div>;
}
