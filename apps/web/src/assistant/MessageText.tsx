import { errorText } from "./presentation";

export function MessageText({ text, truncated, error }: { text: string; truncated: boolean; error: string | null }) {
  return <><div className="chat-message-text"><p>{text}</p></div>{truncated && <small>Ответ сокращён.</small>}
    {error && <p className="chat-error">{errorText(error)}</p>}</>;
}
