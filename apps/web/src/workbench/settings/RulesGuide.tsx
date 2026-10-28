/** Which instruction on the rules page reaches the model, and at which step. */
export function RulesGuide() {
  return <dl className="rules-guide" aria-label="Где действуют инструкции">
    <dt>Шаблон: извлечение</dt>
    <dd><strong>Импорт резюме.</strong> Разделы <code>extract</code> в <code>model</code> (общие правила) и в блоках шаблона задают, какие данные взять из исходного файла.</dd>
    <dt>Шаблон: переписывание</dt>
    <dd><strong>Импорт резюме, если отмечено «Разрешить переписывание текста».</strong> Разделы <code>rewrite</code> в <code>model</code> и в блоках задают, как переписать текст. Без галочки текст остаётся как в источнике.</dd>
    <dt>Команды «Сократить» и «Сделать яснее»</dt>
    <dd><strong>Изменение текста в редакторе.</strong> Кнопки в окне «Изменить текст» подставляют инструкцию из разделов <code>## Preset: shorten</code> и <code>## Preset: clarify</code>. Её можно поправить перед отправкой.</dd>
    <dt>Помощник</dt>
    <dd><strong>Чат с открытым резюме.</strong> Работает по встроенным навыкам <code>/import-resume</code> и <code>/format-resume</code>. Правила с этой страницы ему не передаются.</dd>
  </dl>;
}
