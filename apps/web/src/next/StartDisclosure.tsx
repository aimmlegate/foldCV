import { useEffect, useRef, useState } from "react";
import { ConnectionWorkflow, type ConnectionView } from "../connection/workflow";

export function StartDisclosure({ settings }: { settings: () => void }) {
  const [view, setView] = useState<ConnectionView>(() => new ConnectionWorkflow(() => {}).view);
  const workflowRef = useRef<ConnectionWorkflow | null>(null);
  if (!workflowRef.current) workflowRef.current = new ConnectionWorkflow(setView);
  const workflow = workflowRef.current;
  useEffect(() => { void workflow.peek();return () => workflow.close(); }, [workflow]);
  const snapshot = view.snapshot;
  return <section className="next-disclosure" aria-label="Хранение и модель">
    <p>Исходники и правки сохраняются локально. «Сохранено» означает запись на диск. Вставленный текст и пример остаются в окне до нажатия «Создать резюме».</p>
    <p>Выбор файла читает и сохраняет его без обращения к модели. При создании выбранный текст передаётся модели через CLI.</p>
    <p>{snapshot.selectedModel ? `Выбранная модель: ${snapshot.selectedModel}.` : "Модель выбирается в Настройках."}
      {!snapshot.generationReady && " Доступ проверяется перед операцией."} <button onClick={settings}>Открыть Настройки</button></p>
    {snapshot.experimentalMode && <p>Персональный режим CLI: провайдер может хранить запросы, ответы и следы работы. Выделенный вход остаётся после отключения.</p>}
  </section>;
}
