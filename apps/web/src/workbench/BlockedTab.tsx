export function BlockedTab({ unavailable = false }: { unavailable?: boolean }) {
  return <main className="new-screen"><section className="source-form" role="alert">
    <h2>{unavailable ? "Не удалось открыть FoldCV" : "FoldCV уже открыт в другой вкладке"}</h2>
    <p>{unavailable ? "Не удалось проверить другие вкладки. Обновите страницу."
      : "Работайте в той вкладке или закройте её и обновите эту страницу."}</p>
  </section></main>;
}
