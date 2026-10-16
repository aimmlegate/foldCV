export function BlockedTab({ unavailable = false }: { unavailable?: boolean }) {
  return <main className="new-screen"><section className="source-form" role="alert">
    <h2>{unavailable ? "Не удалось открыть FoldCV" : "FoldCV уже открыт в другой вкладке"}</h2>
    <p>{unavailable ? "Не удалось проверить активную вкладку. Обновите страницу в поддерживаемом браузере."
      : "Продолжите работу в той вкладке. Чтобы использовать эту, закройте другую вкладку FoldCV и обновите страницу."}</p>
  </section></main>;
}
