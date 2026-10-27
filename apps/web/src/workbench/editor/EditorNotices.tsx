import { NotificationSection } from "../ui/NotificationCenter";
import { noticeText } from "../ui/notice-text";

export function EditorNotices({ warning, clearWarning, onOpen }: { warning: string; clearWarning: () => void; onOpen: () => void }) {
  return <NotificationSection count={warning ? 1 : 0} onOpen={onOpen}>
    {warning && <section className="notice-group" aria-label="Замечания"><h3>Замечания</h3>
      <p role="alert" className="notice warning">{noticeText(warning)}<button className="text-button" onClick={clearWarning}>Закрыть</button></p>
    </section>}
  </NotificationSection>;
}
