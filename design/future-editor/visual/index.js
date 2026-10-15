"use strict";
(() => {
  const templates = {
  "shell": [
    "<main class=\"app-shell\">\n    <aside class=\"history\" id=\"history\" aria-label=\"История резюме\">\n      <div class=\"brand-row\"><button class=\"brand\" id=\"brand-button\" aria-label=\"FoldCV — новый исходник\"><svg><use href=\"visual/icons.svg#i-fold\"/></svg>FoldCV<span>.</span></button><button class=\"icon\" id=\"hide-history\" aria-label=\"Свернуть историю\" title=\"Свернуть историю\"><svg><use href=\"visual/icons.svg#i-panel\"/></svg></button></div>\n      <button class=\"button new-button\" id=\"new-button\"><svg><use href=\"visual/icons.svg#i-plus\"/></svg>Новое резюме</button>\n      <div class=\"history-heading\"><span class=\"eyebrow\">Ваши резюме</span><span id=\"history-count\">2</span></div>\n      <div id=\"project-list\" class=\"project-list\"></div>\n      <button class=\"history-open\" id=\"open-project\"><svg><use href=\"visual/icons.svg#i-upload\"/></svg>Открыть .foldcv</button>\n      <footer class=\"history-footer\"><div class=\"connection-mini\"><span class=\"dot\"></span><span>Codex · подписка</span></div><button id=\"settings-button\"><svg><use href=\"visual/icons.svg#i-settings\"/></svg>Настройки<svg class=\"trailing\"><use href=\"visual/icons.svg#i-chevron\"/></svg></button></footer>\n    </aside>\n    <section class=\"main-area\">\n      <header class=\"app-header\">\n        <button class=\"icon show-history\" id=\"show-history\" hidden aria-label=\"Развернуть историю\" title=\"Развернуть историю\"><svg><use href=\"visual/icons.svg#i-panel\"/></svg></button>\n        <div class=\"project-heading\"><span id=\"header-eyebrow\">Рабочий документ</span><h1 id=\"header-title\">Алексей Соколов</h1></div>\n        <div class=\"header-actions\" id=\"header-actions\"><span class=\"session-status\" id=\"session-status\"><span class=\"dot\"></span>Изменений нет</span><button class=\"button quiet\" id=\"save-project\"><svg><use href=\"visual/icons.svg#i-download\"/></svg><span>Сохранить</span></button><button class=\"button primary\" id=\"export-button\">Экспорт DOCX<svg><use href=\"visual/icons.svg#i-arrow\"/></svg></button></div>\n      </header>\n      <div id=\"screen\" class=\"screen\"></div>\n    </section>\n  </main>\n\n  <dialog id=\"modal\" class=\"modal\"><div id=\"modal-content\"></div></dialog>\n  <dialog id=\"rewrite\" class=\"rewrite-panel\" aria-labelledby=\"rewrite-title\"></dialog>\n  <button class=\"selection-action\" id=\"selection-action\" hidden><svg><use href=\"visual/icons.svg#i-spark\"/></svg>Изменить текст</button>\n  <input type=\"file\" id=\"source-file\" accept=\".pdf,.docx,.txt,.md,.markdown\" hidden>\n  <input type=\"file\" id=\"project-file\" accept=\".foldcv,.json\" hidden>\n  <input type=\"file\" id=\"image-file\" accept=\"image/png,image/jpeg,image/webp\" hidden>\n  <div class=\"toast\" id=\"toast\" role=\"status\" hidden></div>"
  ],
  "editor.icon.01": [
    "<svg aria-hidden=\"true\"><use href=\"visual/icons.svg#i-",
    "\"/></svg>"
  ],
  "editor.field.01": [
    "<span data-record=\"",
    "\" data-field=\"",
    "\">",
    "</span>"
  ],
  "editor.sampleProject.01": [
    "",
    "<br>",
    ""
  ],
  "editor.sampleProject.02": [
    "",
    "<br>",
    "<br>",
    ""
  ],
  "editor.sampleProject.03": [
    "",
    "<br>",
    ""
  ],
  "editor.sampleProject.04": [
    "",
    "<br>",
    ""
  ],
  "editor.updateChrome.01": [
    "<div class=\"project-row ",
    "\"><button class=\"project-select\" data-project=\"",
    "\" ",
    " ",
    "><strong>",
    "</strong><small>",
    "</small><em>",
    "</em></button><button class=\"project-delete\" data-delete-project=\"",
    "\" aria-label=\"Удалить проект: ",
    "\" title=\"Удалить резюме\">",
    "</button></div>"
  ],
  "editor.updateChrome.02": [
    "<p class=\"empty-state\">Здесь появятся ваши резюме.</p>"
  ],
  "editor.updateChrome.03": [
    "<span class=\"dot\"></span>",
    ""
  ],
  "editor.updateChrome.04": [
    "<span class=\"dot\"></span><span>",
    "</span>"
  ],
  "editor.mono.01": [
    "<span class=\"tech-monogram\" aria-hidden=\"true\">",
    "</span>"
  ],
  "editor.blockHtml.01": [
    "<div class=\"cv-block ",
    " ",
    "\" data-block=\"",
    "\" data-indent=\"",
    "\"><button class=\"block-handle\" data-block-menu=\"",
    "\" aria-label=\"Действия блока: ",
    "\" title=\"Действия блока\">",
    "</button>",
    "<div class=\"block-content\" contenteditable=\"true\" role=\"textbox\" aria-multiline=\"true\" aria-label=\"",
    "\" data-edit=\"",
    "\" spellcheck=\"false\">",
    "</div></div>"
  ],
  "editor.renderEditor.01": [
    "\n    <div class=\"editor-toolbar\" role=\"toolbar\" aria-label=\"Форматирование документа\">\n      <div class=\"tool-group\"><button class=\"tool\" id=\"undo\" title=\"Отменить (⌘Z)\" aria-label=\"Отменить\">",
    "</button><button class=\"tool\" id=\"redo\" title=\"Повторить (⇧⌘Z)\" aria-label=\"Повторить\">",
    "</button></div>\n      <span class=\"tool-divider\"></span>\n      <select class=\"toolbar-select\" id=\"text-style\" aria-label=\"Стиль текста\"><option value=\"p\">Обычный текст</option><option value=\"h2\">Заголовок</option><option value=\"h3\">Подзаголовок</option><option value=\"blockquote\">Цитата</option></select>\n      <div class=\"tool-group\"><button class=\"tool\" data-format=\"bold\" aria-label=\"Полужирный\" title=\"Полужирный\"><b>B</b></button><button class=\"tool italic\" data-format=\"italic\" aria-label=\"Курсив\" title=\"Курсив\">I</button><button class=\"tool underline\" data-format=\"underline\" aria-label=\"Подчёркнутый\" title=\"Подчёркнутый\">U</button><button class=\"tool\" data-format=\"insertUnorderedList\" aria-label=\"Маркированный список\" title=\"Маркированный список\">",
    "</button></div>\n      <span class=\"tool-divider\"></span>\n      <div class=\"tool-group insert-tools\"><button class=\"tool\" id=\"insert-link\" aria-label=\"Вставить ссылку\" title=\"Ссылка\">",
    "</button><button class=\"tool\" id=\"insert-table\" aria-label=\"Вставить таблицу\" title=\"Таблица\">",
    "</button><button class=\"tool\" id=\"insert-image\" aria-label=\"Вставить изображение\" title=\"Изображение\">",
    "</button></div>\n      <div class=\"tool-group panel-tools\"><button class=\"tool\" id=\"rewrite-button\" aria-label=\"Изменить выбранный текст\" title=\"Изменить выбранный текст\">",
    "<span>Изменить текст</span></button><button class=\"tool\" id=\"facts-toggle\" aria-label=\"Показать или скрыть факты\" aria-pressed=\"",
    "\" aria-controls=\"facts-panel\" title=\"Показать или скрыть факты\">",
    "<span>Факты</span></button><button class=\"tool\" id=\"block-toggle\" aria-label=\"Показать или скрыть действия блока\" aria-pressed=\"",
    "\" aria-controls=\"block-panel\" title=\"Показать или скрыть действия блока\">",
    "<span>Блок</span></button></div>\n    </div>\n    <div class=\"editor-body\">\n      <div class=\"document-workspace\">\n        <div class=\"document-context\"><div class=\"context-left\"><span>Исходный текст</span><span>Шаблон FoldCV</span></div><button id=\"date-warning\">",
    "",
    "</button></div>\n        <div class=\"paper-scroll\"><article class=\"resume-paper\" aria-label=\"Редактируемое резюме, непрерывный документ\">\n          <div class=\"paper-kicker\"><span>РЕЗЮМЕ СПЕЦИАЛИСТА</span><span>F / РЕЗЮМЕ</span></div>\n          <header class=\"paper-heading\">",
    "<span class=\"template-wordmark\" aria-label=\"generic\">generic</span></header>\n          <div class=\"paper-columns\"><aside class=\"paper-sidebar\" aria-label=\"Левая колонка резюме\">",
    "</aside><div class=\"paper-main\" aria-label=\"Основной текст резюме\">",
    "</div></div>\n          <footer class=\"paper-footer\"><span>mail@example.com</span><span>FoldCV</span></footer>\n        </article></div>\n        <footer class=\"editor-footer\"><span id=\"editor-status\">",
    "</span><button id=\"source-button\">",
    "Исходник</button></footer>\n        <div id=\"agent-chat-host\"></div>\n      </div>\n      <aside class=\"facts-panel\" id=\"facts-panel\" aria-label=\"Факты резюме\" ",
    ">",
    "</aside>\n    </div><aside class=\"block-panel\" id=\"block-panel\" aria-label=\"Действия блока\" ",
    "></aside>"
  ],
  "editor.factRow.01": [
    "<div class=\"fact-row\"><button class=\"fact-edit\" data-fact-edit=\"",
    "\"><strong>",
    "</strong>",
    "</button><button class=\"icon\" data-fact-remove=\"",
    "\" aria-label=\"Удалить факт: ",
    "\" title=\"Удалить факт\">",
    "</button></div>"
  ],
  "editor.factRow.02": [
    "<small>",
    "</small>"
  ],
  "editor.technologySummary.01": [
    "<div class=\"technology-select\" data-technology-scope=\"",
    "\">",
    "<div class=\"technology-field\"><div class=\"technology-values\">",
    "<input id=\"",
    "\" class=\"technology-search\" role=\"combobox\" aria-label=\"",
    "\" aria-autocomplete=\"list\" aria-expanded=\"",
    "\" aria-controls=\"",
    "-options\" autocomplete=\"off\" maxlength=\"80\" placeholder=\"",
    "\" value=\"",
    "\"></div><div class=\"technology-field-actions\">",
    "<button type=\"button\" data-technology-toggle aria-label=\"Показать список технологий\" aria-expanded=\"",
    "\" aria-controls=\"",
    "-options\">",
    "</button></div></div><div class=\"technology-menu\" id=\"",
    "-options\" role=\"listbox\" aria-label=\"Список технологий\" aria-multiselectable=\"true\" ",
    ">",
    "</div></div>"
  ],
  "editor.technologySummary.02": [
    "<span class=\"technology-label\">Технологии</span>"
  ],
  "editor.technologySummary.03": [
    "<span class=\"technology-chip\"><span>",
    "</span><button type=\"button\" data-technology-remove=\"",
    "\" aria-label=\"Убрать ",
    "\">",
    "</button></span>"
  ],
  "editor.technologySummary.04": [
    "<button type=\"button\" data-technology-clear aria-label=\"Убрать все технологии: ",
    "\" title=\"Убрать все\">",
    "</button>"
  ],
  "editor.factsHtml.01": [
    "<div class=\"panel-heading\"><h2>Факты</h2><button class=\"icon\" id=\"close-facts\" aria-label=\"Скрыть факты\">",
    "</button></div>",
    ""
  ],
  "editor.factsHtml.02": [
    "<details class=\"fact-group\" data-group=\"",
    "\" open><summary>",
    "</summary>",
    "",
    "</details>"
  ],
  "editor.factsHtml.03": [
    "<button class=\"text-button fact-add\" data-fact-add=\"",
    "\">+ ",
    "</button>"
  ],
  "editor.technologyOptions.01": [
    "<button type=\"button\" role=\"option\" tabindex=\"-1\" aria-selected=\"false\" id=\"",
    "-option-",
    "\" data-technology-option=\"",
    "\" class=\"technology-option ",
    "\">",
    "</button>"
  ],
  "editor.technologyOptions.02": [
    "<span class=\"technology-no-results\">Нет доступных вариантов</span>"
  ],
  "editor.renderBlockPanel.01": [
    "<div class=\"panel-heading\"><h2>Блок</h2><button class=\"icon\" id=\"close-block\" aria-label=\"Скрыть действия блока\">",
    "</button></div><p class=\"block-scope\">",
    "</p><div class=\"block-actions\"><button data-command=\"duplicate\" ",
    ">Дублировать</button><button data-command=\"delete\" class=\"danger\" ",
    ">Удалить</button><button data-command=\"up\" ",
    ">↑ Выше</button><button data-command=\"down\" ",
    ">↓ Ниже</button><button data-command=\"nest\" ",
    ">→ Добавить отступ</button><button data-command=\"unnest\" ",
    ">← Убрать отступ</button><button class=\"wide\" data-command=\"merge\" ",
    ">Объединить с предыдущим</button></div><label for=\"move-region\">Переместить в</label><select id=\"move-region\" ",
    "><option value=\"\">Выберите область</option><option value=\"header\" ",
    ">Шапка документа</option><option value=\"sidebar\" ",
    ">Левая колонка</option><option value=\"main\" ",
    ">Основной текст</option></select>"
  ],
  "editor.editBlock.01": [
    "<span data-record=\"",
    "\" data-field=\"",
    "\">",
    "</span>"
  ],
  "editor.blockCommand.01": [
    "<br>",
    ""
  ],
  "editor.modal.01": [
    "<form id=\"dialog-form\"><div class=\"dialog-heading\"><div>",
    "<h2 id=\"dialog-title\">",
    "</h2></div><button class=\"icon\" type=\"button\" data-close-modal aria-label=\"Закрыть\">",
    "</button></div>",
    "",
    "</form>"
  ],
  "editor.modal.02": [
    "<span class=\"eyebrow\">",
    "</span>"
  ],
  "editor.modal.03": [
    "<div class=\"dialog-actions\">",
    "</div>"
  ],
  "editor.cancelButton.01": [
    "<button class=\"button\" type=\"button\" data-close-modal>Отмена</button>"
  ],
  "editor.editFact.01": [
    "<p class=\"dialog-subtitle\">Изменения появятся в документе после сохранения.</p><div class=\"fact-form-grid\">",
    "</div>",
    ""
  ],
  "editor.editFact.02": [
    "<div class=\"",
    "\"><label for=\"fact-",
    "\">",
    "</label><input id=\"fact-",
    "\" name=\"",
    "\" value=\"",
    "\" ",
    " ",
    " ",
    "></div>"
  ],
  "editor.editFact.03": [
    "<p class=\"dialog-subtitle\">Укажите год, месяц или полную дату, как в исходнике.</p>"
  ],
  "editor.editFact.04": [
    "",
    "<button class=\"button primary\" type=\"submit\">Сохранить факт",
    "</button>"
  ],
  "editor.insertFactBlocks.01": [
    "",
    "<br>",
    ""
  ],
  "editor.insertFactBlocks.02": [
    "",
    "<br>",
    "<br>",
    ""
  ],
  "editor.insertFactBlocks.03": [
    "",
    "<br>",
    ""
  ],
  "editor.removeFact.01": [
    "<p class=\"dialog-copy\">",
    ". Связанные поля будут удалены из документа. Остальной текст сохранится.</p>"
  ],
  "editor.removeFact.02": [
    "",
    "<button class=\"button danger\" type=\"submit\">Удалить факт</button>"
  ],
  "editor.renderNew.01": [
    "<section class=\"new-screen\" aria-label=\"Новое резюме\"><div class=\"source-form\"><h2>Добавить исходник</h2><p>Загрузите резюме или вставьте текст. Он откроется в редакторе без переписывания.</p><button class=\"dropzone\" id=\"choose-source\" type=\"button\"><span class=\"upload-mark\">",
    "</span><span><strong>Выбрать файл</strong><small>PDF, DOCX, TXT, Markdown · можно перетащить сюда</small></span></button>",
    "<label for=\"source-text\">Текст резюме</label><textarea class=\"source-text\" id=\"source-text\" placeholder=\"Имя, опыт работы, навыки…\" ",
    ">",
    "</textarea>",
    "<div class=\"source-bottom\"><button class=\"text-button\" id=\"use-sample\">Вставить пример</button><button class=\"button primary\" id=\"process-source\" ",
    ">Обработать",
    "</button></div><p class=\"source-note muted\">В прототипе обработка показана на примере, без обращения к модели.</p></div></section>"
  ],
  "editor.renderNew.02": [
    "<div class=\"source-filename\">",
    "<span>",
    "</span><button class=\"icon\" id=\"remove-source\" aria-label=\"Убрать файл\">",
    "</button></div>"
  ],
  "editor.renderNew.03": [
    "<p class=\"notice warning\">Прототип не читает PDF и DOCX. Вставьте текст из файла или используйте пример.</p>"
  ],
  "editor.renderProgress.01": [
    "<section class=\"progress-screen\" aria-label=\"Обработка резюме\"><div class=\"progress-content\"><div class=\"progress-icon\">",
    "</div><h2>Обработка резюме</h2><p class=\"muted\">",
    "</p><ol class=\"progress-list\" aria-live=\"polite\">",
    "</ol><button class=\"text-button\" id=\"cancel-process\">Отменить обработку</button></div></section>"
  ],
  "editor.renderProgress.02": [
    "<li class=\"",
    "\"><span class=\"step-indicator\">",
    "</span>",
    "</li>"
  ],
  "editor.renderCheck.01": [
    "<section class=\"check-screen\" aria-label=\"Первичная проверка\"><div class=\"check-content\"><h2>Результат проверки</h2><div class=\"check-result\">",
    "<div><strong>",
    "</strong><p>",
    "</p></div></div>",
    "<div class=\"check-actions\"><button class=\"button primary\" id=\"open-processed\">",
    "",
    "</button><button class=\"text-button\" id=\"back-source\">Вернуться к исходнику</button></div></div></section>"
  ],
  "editor.renderCheck.02": [
    "<div class=\"check-tags\"><span>Кандидат</span><span>2 места работы</span><span>Технологии</span><span>Образование</span><span>2 языка</span></div><p class=\"small muted\">Периоды работы пересекаются. Проверьте даты в редакторе.</p>"
  ],
  "editor.renderCheck.03": [
    "<p class=\"small muted\">Можно продолжить, даже если это не резюме.</p>"
  ],
  "editor.renderSettings.01": [
    "<h3>Модель и подключение</h3><p>Подключение через Codex по подписке ChatGPT.</p><div class=\"connection-status\"><span class=\"connection-check\">",
    "</span><div><strong>",
    "</strong><small>",
    "</small></div></div><label for=\"model-select\">Модель</label><select class=\"model-select\" id=\"model-select\"><option value=\"gpt-5.4\" ",
    ">gpt-5.4</option><option value=\"gpt-5.4-mini\" ",
    ">gpt-5.4-mini</option></select><p class=\"small muted\">Модели показаны для примера.</p><div class=\"quota-line\"><span class=\"quota-bar\"><span></span></span>Использовано 24% · пример</div><div class=\"settings-actions\"><button class=\"button small\" id=\"check-connection\" ",
    ">",
    "</button><button class=\"text-button\" id=\"toggle-connection\">",
    "</button></div><p class=\"settings-disclosure\">Пример подключения без входа в Codex.</p>"
  ],
  "editor.renderSettings.02": [
    "<h3>Общие правила и команды</h3><p>Эти правила действуют для всех резюме и применяются при следующей обработке текста.</p><label for=\"rules-text\">Правила в Markdown</label><textarea class=\"rules-text\" id=\"rules-text\" spellcheck=\"false\">",
    "</textarea><p class=\"small muted\">Сохраните оба заголовка: <code>## Preset: shorten</code> и <code>## Preset: clarify</code> с инструкциями под ними.</p>"
  ],
  "editor.renderSettings.03": [
    "<h3>Проверка изменений</h3><p>Проверять факты и даты после редактирования.</p><div class=\"switch-line\"><label for=\"analysis-toggle\">Автоматически проверять изменения<small>Другие упоминания меняются только с вашего согласия.</small></label><input class=\"switch\" id=\"analysis-toggle\" type=\"checkbox\" ",
    " role=\"switch\"></div><p class=\"settings-disclosure\">Параллельные периоды работы допустимы. Подсказки не блокируют редактирование, сохранение или экспорт.</p>"
  ],
  "editor.renderSettings.04": [
    "<section class=\"settings-screen\" aria-label=\"Настройки\"><div class=\"settings-title\"><button class=\"text-button\" id=\"back-settings\">← Вернуться к резюме</button></div><div class=\"settings-layout\"><nav class=\"settings-nav\" aria-label=\"Разделы настроек\"><button data-settings=\"model\" class=\"",
    "\" ",
    ">Модель и подключение</button><button data-settings=\"rules\" class=\"",
    "\" ",
    ">Общие правила и команды</button><button data-settings=\"analysis\" class=\"",
    "\" ",
    ">Проверка изменений</button></nav><div class=\"settings-content\">",
    "",
    "",
    "<div class=\"settings-actions\"><button class=\"button primary\" id=\"save-settings\" ",
    ">Сохранить изменения</button><button class=\"button quiet\" id=\"cancel-settings\" ",
    ">Отмена</button><span class=\"settings-saved\" id=\"settings-dirty\">",
    "</span></div></div></div></section>"
  ],
  "editor.renderSettings.05": [
    "<p class=\"notice\" role=\"status\">",
    "</p>"
  ],
  "editor.renderSettings.06": [
    "<p class=\"notice error\" role=\"alert\">",
    "</p>"
  ],
  "editor.dateDialog.01": [
    "<p class=\"dialog-copy\">",
    "</p><p class=\"notice\">Редактирование и экспорт доступны.</p>"
  ],
  "editor.dateDialog.02": [
    "<button class=\"button primary\" type=\"button\" data-close-modal>Понятно</button>"
  ],
  "editor.dateDialog.03": [
    "<p class=\"dialog-copy\">",
    " и ",
    ": пересечение — ",
    " мес. Параллельная работа допустима. Если это ошибка, проверьте предлагаемый сдвиг.</p><div class=\"timeline-pair\"><div><small>Сейчас</small><strong>",
    "</strong><p>",
    " — ",
    "</p></div><div><small>После сдвига</small><strong>",
    "</strong><p>",
    " — ",
    "</p></div></div><p class=\"dialog-subtitle\">Длительность периода сохранена: ",
    " мес. Более поздний период остаётся без изменения.</p><div class=\"notice warning\">Редактирование и экспорт доступны при любом решении.</div>"
  ],
  "editor.dateDialog.04": [
    "<button class=\"text-button\" id=\"keep-dates\" type=\"button\">Оставить даты</button><button class=\"button primary\" id=\"apply-dates\" type=\"button\">Изменить даты</button>"
  ],
  "editor.exportDialog.01": [
    "<p class=\"dialog-copy\">",
    "<br>",
    "</p><div class=\"export-format\"><span class=\"format-icon\">W</span><div><strong>Документ Word</strong><small>DOCX · редактируемый текст и таблицы</small></div>",
    "</div><div class=\"export-summary\"><span>Шаблон</span><strong>FoldCV / две колонки</strong></div>",
    "<p class=\"dialog-subtitle\">Прототип не создаёт DOCX. Скачать документ можно в основном приложении.</p>"
  ],
  "editor.exportDialog.02": [
    "<p class=\"notice warning\">Есть пересечение дат. Оно не мешает экспорту; проверьте, что параллельная работа указана верно.</p>"
  ],
  "editor.exportDialog.03": [
    "<button class=\"text-button\" data-close-modal type=\"button\">Вернуться к тексту</button><button class=\"button primary\" id=\"simulate-export\" type=\"button\">Показать пример результата"
  ],
  "editor.exportDialog.04": [
    "</button>"
  ],
  "editor.saveDialog.01": [
    "<p class=\"dialog-copy\">Файл .foldcv хранит исходник, факты и документ.</p><p class=\"notice\">",
    "</p><div class=\"demo-file-row\"><span>",
    "</span><button class=\"button small\" type=\"button\" id=\"",
    "\">",
    "",
    "</button></div>"
  ],
  "editor.saveDialog.02": [
    "<button class=\"button\" data-close-modal type=\"button\">Закрыть</button>"
  ],
  "editor.renderRewrite.01": [
    "<div class=\"dialog-heading\"><div><h2 id=\"rewrite-title\">Изменить текст</h2></div><button class=\"icon\" id=\"close-rewrite\" aria-label=\"Закрыть правку\">",
    "</button></div><p class=\"rewrite-scope\">",
    "Только ",
    " · ",
    " знаков</p><blockquote class=\"rewrite-source\">",
    "</blockquote><label for=\"rewrite-instruction\">Что изменить?</label><textarea id=\"rewrite-instruction\" rows=\"2\">",
    "</textarea><div class=\"rewrite-chips\"><button data-rewrite-preset=\"shorten\">Сократить</button><button data-rewrite-preset=\"clarify\">Сделать яснее</button></div>",
    "<p class=\"rewrite-boundary\">Пример правки без обращения к модели. Своя инструкция здесь не обрабатывается.</p>"
  ],
  "editor.renderRewrite.02": [
    "<button class=\"button primary\" id=\"prepare-rewrite\">Предложить правку"
  ],
  "editor.renderRewrite.03": [
    "</button>"
  ],
  "editor.renderRewrite.04": [
    "<div class=\"proposal-divider\"><span class=\"eyebrow\">Вариант правки</span><p class=\"proposal-text\">",
    "</p>",
    "<p class=\"notice warning\" id=\"stale-warning\" ",
    ">Текст изменился. Запросите новую правку, чтобы сохранить свои изменения.</p><div class=\"dialog-actions\"><button class=\"text-button\" id=\"discard-rewrite\">Отклонить</button><button class=\"button primary\" id=\"apply-rewrite\" ",
    ">Применить",
    "</button></div><button class=\"text-button\" id=\"refresh-rewrite\">Предложить заново</button></div>"
  ],
  "editor.renderRewrite.05": [
    "<p class=\"notice\">Для этого фрагмента нет готового варианта. Текст не изменён.</p>"
  ],
  "editor.openSource.01": [
    "<p class=\"dialog-subtitle\">",
    "</p><div class=\"source-original\">",
    "</div>"
  ],
  "editor.openSource.02": [
    "<button class=\"button\" type=\"button\" data-close-modal>Закрыть</button>"
  ],
  "editor.deleteProject.01": [
    "<p class=\"dialog-copy\">",
    "<br>Резюме будет удалено из списка.</p>"
  ],
  "editor.deleteProject.02": [
    "",
    "<button class=\"button danger\" type=\"submit\">Удалить резюме</button>"
  ],
  "editor.aboutDialog.01": [
    "<p class=\"dialog-copy\">Все данные вымышлены. Обработка текста, подключение к модели и экспорт показаны для примера. Данные не отправляются в сеть. При перезагрузке несохранённые изменения теряются.</p>"
  ],
  "editor.aboutDialog.02": [
    "<button class=\"button primary\" data-close-modal type=\"button\">Продолжить</button>"
  ],
  "editor.insertLink.01": [
    "<label for=\"link-text\">Текст ссылки</label><input id=\"link-text\" name=\"text\" value=\"",
    "\" required autofocus><label for=\"link-url\">Адрес</label><input id=\"link-url\" name=\"url\" type=\"url\" value=\"https://example.com\" required>"
  ],
  "editor.insertLink.02": [
    "",
    "<button class=\"button primary\" type=\"submit\">Вставить ссылку</button>"
  ],
  "editor.insertLink.03": [
    "<a href=\"",
    "\">",
    "</a>"
  ],
  "editor.insertTable.01": [
    "<div class=\"fact-form-grid\"><div><label for=\"table-rows\">Строк</label><input id=\"table-rows\" name=\"rows\" type=\"number\" value=\"3\" min=\"1\" max=\"10\" required></div><div><label for=\"table-columns\">Столбцов</label><input id=\"table-columns\" name=\"columns\" type=\"number\" value=\"2\" min=\"1\" max=\"5\" required></div></div>"
  ],
  "editor.insertTable.02": [
    "",
    "<button class=\"button primary\" type=\"submit\">Вставить таблицу</button>"
  ],
  "editor.insertTable.03": [
    "<table><tbody>",
    "</tbody></table>"
  ],
  "editor.insertTable.04": [
    "<tr>",
    "</tr>"
  ],
  "editor.insertTable.05": [
    "<td>",
    "</td>"
  ],
  "editor.readImage.01": [
    "<img src=\"",
    "\" alt=\"",
    "\"><p>",
    "</p>"
  ],
  "editor.events.01": [
    "<div class=\"export-format\"><span class=\"connection-check\">"
  ],
  "editor.events.02": [
    "</span><div><strong>Пример завершения экспорта</strong><small>Файл здесь не создаётся и не скачивается</small></div></div><p class=\"dialog-copy\">В основном приложении здесь скачивается документ Word.</p>"
  ],
  "editor.events.03": [
    "<button class=\"button primary\" data-close-modal type=\"button\">Вернуться к резюме</button>"
  ],
  "chat.actionIcon.01": [
    "<button class=\"chat-icon\" type=\"button\" data-chat-action=\"",
    "\" aria-label=\"",
    "\" title=\"",
    "\" ",
    ">",
    "</button>"
  ],
  "chat.textHtml.01": [
    "<p>",
    "</p>"
  ],
  "chat.textHtml.02": [
    "<br>"
  ],
  "chat.messageHtml.01": [
    "<article class=\"chat-message ",
    "\" data-chat-message=\"",
    "\">\n      <div class=\"chat-message-heading\"><span>",
    "</span>",
    "</div>\n      ",
    "\n      ",
    "\n      ",
    "\n      ",
    "\n      ",
    "\n      ",
    "\n      ",
    "\n    </article>"
  ],
  "chat.messageHtml.02": [
    "<small>",
    "</small>"
  ],
  "chat.messageHtml.03": [
    "<details class=\"chat-activity\" data-chat-activity=\"",
    "\" ",
    "><summary>",
    "<span>",
    "</span>",
    "</summary><ol>",
    "</ol></details>"
  ],
  "chat.messageHtml.04": [
    "<span class=\"chat-spinner\"></span>"
  ],
  "chat.messageHtml.05": [
    "<li>",
    "</li>"
  ],
  "chat.messageHtml.06": [
    "<div class=\"chat-message-text ",
    "\">",
    "</div>"
  ],
  "chat.messageHtml.07": [
    "<div class=\"chat-thinking\" aria-label=\"Помощник работает\"><i></i><i></i><i></i></div>"
  ],
  "chat.messageHtml.08": [
    "<small class=\"chat-message-attachment\">",
    "",
    "</small>"
  ],
  "chat.messageHtml.09": [
    "<div class=\"chat-findings\">",
    "</div>"
  ],
  "chat.messageHtml.10": [
    "<button type=\"button\" data-chat-block=\"",
    "\">",
    "<span><strong>",
    "</strong><small>",
    "</small></span>",
    "</button>"
  ],
  "chat.messageHtml.11": [
    "<button class=\"chat-source\" type=\"button\" data-chat-source=\"",
    "\">",
    "<span>1. ",
    "</span>",
    "</button>"
  ],
  "chat.messageHtml.12": [
    "<div class=\"chat-receipt\"><span>",
    "<strong>",
    "</strong><small>",
    "</small></span><div><button type=\"button\" class=\"text-button\" data-chat-block=\"",
    "\">Показать</button><button type=\"button\" class=\"text-button\" data-chat-undo=\"",
    "\" ",
    ">Отменить правку</button></div></div>"
  ],
  "chat.messageHtml.13": [
    "<div class=\"chat-message-actions\">",
    "",
    "",
    "</div>"
  ],
  "chat.messageHtml.14": [
    "<button type=\"button\" class=\"chat-retry\" data-chat-action=\"retry\" ",
    ">",
    "",
    "</button>"
  ],
  "chat.messageHtml.15": [
    "<span>Готово</span>"
  ],
  "chat.render.01": [
    "<button type=\"button\" class=\"chat-launcher\" id=\"chat-open\" aria-expanded=\"false\" aria-controls=\"agent-chat-panel\"><span>",
    "Помощник</span><small>",
    "</small>",
    "</button>"
  ],
  "chat.render.02": [
    "<span class=\"chat-spinner\"></span>Работает"
  ],
  "chat.render.03": [
    "<span class=\"dot\"></span>Есть ответ"
  ],
  "chat.render.04": [
    "<section class=\"agent-chat-panel\" id=\"agent-chat-panel\" aria-label=\"Чат с помощником\">\n      <header class=\"chat-header\"><div class=\"chat-title\">",
    "<h2>Помощник</h2><span class=\"chat-access\"><span class=\"dot\"></span>Резюме открыто</span></div><div class=\"chat-header-actions\">",
    "",
    "",
    "",
    "</div></header>\n      ",
    "\n      <div class=\"chat-messages\" id=\"chat-messages\" role=\"log\" aria-label=\"Переписка\" aria-live=\"polite\" aria-relevant=\"additions text\" aria-busy=\"",
    "\">\n        ",
    "\n      </div>\n      <form class=\"chat-composer\" id=\"chat-form\"><div class=\"chat-context\"><span class=\"chat-context-resume\" title=\"",
    "\">",
    "",
    "</span><button type=\"button\" class=\"chat-scope ",
    "\" data-chat-action=\"scope\" ",
    " title=\"",
    "\">",
    "",
    "</button>",
    "</div>\n        <div class=\"chat-input-box\"><label class=\"visually-hidden\" for=\"chat-input\">Сообщение помощнику</label><textarea id=\"chat-input\" rows=\"2\" maxlength=\"5000\" placeholder=\"Спросите о резюме или опишите правку…\">",
    "</textarea><div class=\"chat-composer-controls\"><div class=\"chat-controls-left\">",
    "<label class=\"chat-model-label\" for=\"chat-model\"><span class=\"visually-hidden\">Модель помощника</span><select id=\"chat-model\" title=\"Модель помощника; меняется отдельно от модели обработки\"><option value=\"gpt-5.4\" ",
    ">gpt-5.4</option><option value=\"gpt-5.4-mini\" ",
    ">gpt-5.4-mini</option></select></label><label class=\"chat-mode\" title=\"Проверять резюме без изменений\"><input id=\"chat-check-only\" type=\"checkbox\" ",
    " ",
    ">Только проверка</label><label class=\"chat-mode chat-internet\" title=\"Разрешить поиск в интернете\"><input id=\"chat-internet\" type=\"checkbox\" ",
    " ",
    ">",
    "<span>Интернет</span></label></div>",
    "</div></div>\n        <footer class=\"chat-composer-footer\"><span>Скетч · ответы и действия на примере</span><span>",
    "</span></footer>\n      </form><input id=\"chat-file\" type=\"file\" accept=\".txt,.md,.markdown\" hidden>\n    </section>"
  ],
  "chat.render.05": [
    "<nav class=\"chat-thread-menu\" aria-label=\"Диалоги этого резюме\"><span>Диалоги</span>",
    "</nav>"
  ],
  "chat.render.06": [
    "<button type=\"button\" data-chat-thread=\"",
    "\" ",
    " ",
    ">",
    "<span>",
    "</span></button>"
  ],
  "chat.render.07": [
    "<div class=\"chat-empty\"><span class=\"chat-empty-icon\">",
    "</span><h3>Чат по этому резюме</h3><p>Помощник видит текст и факты. Напишите, что проверить или изменить.</p><div class=\"chat-suggestions\"><button type=\"button\" data-chat-prompt=\"Проверь резюме и укажи, что стоит уточнить.\">",
    "Проверить резюме</button><button type=\"button\" data-chat-prompt=\"Сократи раздел «О специалисте», сохрани факты.\">",
    "Сократить описание</button><button type=\"button\" data-chat-vacancy>",
    "Сравнить с вакансией</button></div></div>"
  ],
  "chat.render.08": [
    "<span class=\"chat-attachment\">",
    "",
    "<button type=\"button\" data-chat-action=\"remove-attachment\" aria-label=\"Убрать вложение\" ",
    ">",
    "</button></span>"
  ],
  "chat.render.09": [
    "<button class=\"chat-send is-stop\" type=\"button\" data-chat-action=\"stop\" aria-label=\"Остановить ответ\" title=\"Остановить ответ\">",
    "</button>"
  ],
  "chat.render.10": [
    "<button class=\"chat-send\" id=\"chat-send\" type=\"submit\" aria-label=\"Отправить сообщение\" title=\"Отправить · Enter\" ",
    ">",
    "</button>"
  ],
  "chat.events.01": [
    "<div class=\"source-original\">",
    "</div>",
    ""
  ],
  "chat.events.02": [
    "<p class=\"dialog-subtitle\">Вымышленная вакансия. Интернет-запрос не выполнялся.</p>"
  ],
  "chat.events.03": [
    "<button class=\"button\" type=\"button\" data-close-modal>Закрыть</button>"
  ]
};
  const copy = {
  "editor.sampleProfile.01": [
    "Фронтенд-разработчик с опытом создания продуктовых интерфейсов. Разрабатываю приложения на React и TypeScript: от первых экранов до поддержки после запуска. В команде «Север» работаю над личным кабинетом и библиотекой компонентов. Люблю понятный код, внимателен к деталям и доступности."
  ],
  "editor.sampleJob.01": [
    "Разрабатываю личный кабинет на React и TypeScript. Создаю и поддерживаю общие компоненты интерфейса, подключаю API, покрываю ключевые сценарии тестами. Вместе с дизайнером улучшаю доступность и согласованность экранов."
  ],
  "editor.sampleOldJob.01": [
    "Создавал сайты и внутренние сервисы для небольших команд. Работал с адаптивной вёрсткой, подключал API и поддерживал выпущенные проекты."
  ],
  "editor.sampleText.01": [
    "Алексей Соколов\nФронтенд-разработчик\nСанкт-Петербург · alexey@example.com\n\nО специалисте\n",
    "\n\nСевер · Фронтенд-разработчик\n2022-01 — настоящее время\n",
    "\nReact, TypeScript, Jest\n\nСтудия Линия · Веб-разработчик\n2019-06 — 2022-03\n",
    "\nJavaScript, HTML, CSS\n\nНавыки: React, TypeScript, JavaScript, Git\nОбразование: СПбПУ, Информатика и вычислительная техника, 2019\nЯзыки: Русский — родной, Английский — B2"
  ],
  "editor.initialRules.01": [
    "# Общие правила\nСохраняй факты, числа и личный вклад. Пиши ясно и по делу.\nНе добавляй неподтверждённые навыки.\n\n## Preset: shorten\nСократи повторы и вводные слова, сохрани смысл и все факты.\n\n## Preset: clarify\nУпрости длинные фразы. Сделай личный вклад понятнее."
  ],
  "editor.sampleProject.01": [
    "Алексей Соколов"
  ],
  "editor.sampleProject.02": [
    "Фронтенд-разработчик"
  ],
  "editor.facts.01": [
    "Санкт-Петербург"
  ],
  "editor.facts.02": [
    "Север"
  ],
  "editor.facts.03": [
    "Фронтенд-разработчик"
  ],
  "editor.facts.04": [
    "настоящее время"
  ],
  "editor.facts.05": [
    "Студия Линия"
  ],
  "editor.facts.06": [
    "Веб-разработчик"
  ],
  "editor.facts.07": [
    "СПбПУ"
  ],
  "editor.facts.08": [
    "Информатика и вычислительная техника"
  ],
  "editor.facts.09": [
    "Русский"
  ],
  "editor.facts.10": [
    "Родной"
  ],
  "editor.facts.11": [
    "Английский"
  ],
  "editor.sampleProject.03": [
    "Контакты"
  ],
  "editor.sampleProject.04": [
    "Санкт-Петербург"
  ],
  "editor.sampleProject.05": [
    "Технологии"
  ],
  "editor.sampleProject.06": [
    "Образование"
  ],
  "editor.sampleProject.07": [
    "СПбПУ"
  ],
  "editor.sampleProject.08": [
    "Информатика и вычислительная техника"
  ],
  "editor.sampleProject.09": [
    "Языки"
  ],
  "editor.sampleProject.10": [
    "Русский"
  ],
  "editor.sampleProject.11": [
    "Родной"
  ],
  "editor.sampleProject.12": [
    "Английский"
  ],
  "editor.sampleProject.13": [
    "О специалисте"
  ],
  "editor.sampleProject.14": [
    "Опыт работы"
  ],
  "editor.sampleProject.15": [
    "Алексей Соколов"
  ],
  "editor.sampleProject.16": [
    "Фронтенд-разработчик"
  ],
  "editor.sampleProject.17": [
    "Резюме — пример.txt"
  ],
  "editor.events.01": [
    "Мария Волкова"
  ],
  "editor.events.02": [
    "Дизайнер интерфейсов"
  ],
  "editor.projectName.01": [
    "Без имени"
  ],
  "editor.projectTitle.01": [
    "Специальность не указана"
  ],
  "editor.markChanged.01": [
    "Есть несохранённые изменения"
  ],
  "editor.updateChrome.01": [
    "Есть изменения"
  ],
  "editor.updateChrome.02": [
    "Рабочая версия"
  ],
  "editor.updateChrome.03": [
    "Новое резюме"
  ],
  "editor.updateChrome.04": [
    "Настройки"
  ],
  "editor.updateChrome.05": [
    "Настройки"
  ],
  "editor.updateChrome.06": [
    "Новый исходник"
  ],
  "editor.updateChrome.07": [
    "Есть изменения"
  ],
  "editor.updateChrome.08": [
    "Изменений нет"
  ],
  "editor.updateChrome.09": [
    "Codex · подписка"
  ],
  "editor.updateChrome.10": [
    "Модель отключена"
  ],
  "editor.navigate.01": [
    "Дождитесь обработки или отмените её."
  ],
  "editor.label.01": [
    "Имя кандидата"
  ],
  "editor.label.02": [
    "Специальность кандидата"
  ],
  "editor.label.03": [
    "Новый блок"
  ],
  "editor.dateLabel.01": [
    "Параллельная работа"
  ],
  "editor.dateLabel.02": [
    "Пересечение дат"
  ],
  "editor.dateLabel.03": [
    "Даты согласованы"
  ],
  "editor.dateLabel.04": [
    "Проверка дат"
  ],
  "editor.renderEditor.01": [
    "Есть несохранённые изменения"
  ],
  "editor.renderEditor.02": [
    "Исходный текст"
  ],
  "editor.groupNames.01": [
    "Кандидат"
  ],
  "editor.groupNames.02": [
    "Опыт работы"
  ],
  "editor.groupNames.03": [
    "Технологии"
  ],
  "editor.groupNames.04": [
    "Образование"
  ],
  "editor.groupNames.05": [
    "Языки"
  ],
  "editor.factRow.01": [
    "Без названия"
  ],
  "editor.label.04": [
    "Технологии: ",
    ""
  ],
  "editor.label.05": [
    "общий список"
  ],
  "editor.technologySummary.01": [
    "Найти…"
  ],
  "editor.technologySummary.02": [
    "Выбрать технологии"
  ],
  "editor.technologySummary.03": [
    "общий список"
  ],
  "editor.factsHtml.01": [
    "Место работы"
  ],
  "editor.factsHtml.02": [
    "Язык"
  ],
  "editor.technologyOptions.01": [
    "Добавить «",
    "»"
  ],
  "editor.setTechnologies.01": [
    "Технологии обновлены"
  ],
  "editor.renderBlockPanel.01": [
    "Выберите текст в документе"
  ],
  "editor.editBlock.01": [
    "Текст и связанные факты обновлены"
  ],
  "editor.historyAction.01": [
    "Изменение отменено"
  ],
  "editor.historyAction.02": [
    "Изменение повторено"
  ],
  "editor.blockCommand.01": [
    "Это первый блок в области."
  ],
  "editor.blockCommand.02": [
    "Это последний блок в области."
  ],
  "editor.blockCommand.03": [
    "Расположение блоков изменено"
  ],
  "editor.addBlock.01": [
    "Добавлен новый блок"
  ],
  "editor.factFields.01": [
    "Имя и фамилия"
  ],
  "editor.factFields.02": [
    "Специальность"
  ],
  "editor.factFields.03": [
    "Город"
  ],
  "editor.factFields.04": [
    "Электронная почта"
  ],
  "editor.factFields.05": [
    "Компания"
  ],
  "editor.factFields.06": [
    "Должность"
  ],
  "editor.factFields.07": [
    "Начало"
  ],
  "editor.factFields.08": [
    "Окончание"
  ],
  "editor.factFields.09": [
    "Технология"
  ],
  "editor.factFields.10": [
    "Учебное заведение"
  ],
  "editor.factFields.11": [
    "Специальность"
  ],
  "editor.factFields.12": [
    "Год окончания"
  ],
  "editor.factFields.13": [
    "Язык"
  ],
  "editor.factFields.14": [
    "Уровень"
  ],
  "editor.editFact.01": [
    "Изменить факт"
  ],
  "editor.editFact.02": [
    "Добавить факт"
  ],
  "editor.editFact.03": [
    "placeholder=\"2022-01 или настоящее время\""
  ],
  "editor.editFact.04": [
    "Факт сохранён"
  ],
  "editor.editFact.05": [
    "Факт сохранён"
  ],
  "editor.removeFact.01": [
    "Удалить факт?"
  ],
  "editor.removeFact.02": [
    "Факт удалён. Проверьте текст документа."
  ],
  "editor.labels.01": [
    "Проверяем текст"
  ],
  "editor.labels.02": [
    "Извлекаем факты"
  ],
  "editor.labels.03": [
    "Открываем редактор"
  ],
  "editor.renderProgress.01": [
    "Вставленный текст"
  ],
  "editor.renderCheck.01": [
    "Текст похож на резюме"
  ],
  "editor.renderCheck.02": [
    "Возможно, это не резюме"
  ],
  "editor.renderCheck.03": [
    "Найдены сведения о кандидате, работе, навыках, образовании и языках."
  ],
  "editor.renderCheck.04": [
    "В прототипе имя и специальность берутся из первых строк. Остальные сведения можно добавить вручную."
  ],
  "editor.renderCheck.05": [
    "Открыть редактор"
  ],
  "editor.renderCheck.06": [
    "Всё равно продолжить"
  ],
  "editor.name.01": [
    "Без имени"
  ],
  "editor.openProcessed.01": [
    "Вставленный текст"
  ],
  "editor.openProcessed.02": [
    "Вставленный текст"
  ],
  "editor.openProcessed.03": [
    "Резюме открыто"
  ],
  "editor.readSource.01": [
    "Выберите PDF, DOCX, TXT или Markdown."
  ],
  "editor.readSource.02": [
    "Для прототипа выберите текстовый файл до 2 МБ."
  ],
  "editor.readSource.03": [
    "Не удалось прочитать файл. Попробуйте вставить текст."
  ],
  "editor.renderSettings.01": [
    "Подписка подключена"
  ],
  "editor.renderSettings.02": [
    "Модель отключена"
  ],
  "editor.renderSettings.03": [
    "Подключите Codex для обработки текста"
  ],
  "editor.renderSettings.04": [
    "Проверяем…"
  ],
  "editor.renderSettings.05": [
    "Проверить подключение"
  ],
  "editor.renderSettings.06": [
    "Отключить модель"
  ],
  "editor.renderSettings.07": [
    "Подключить Codex"
  ],
  "editor.renderSettings.08": [
    "Есть несохранённые изменения"
  ],
  "editor.renderSettings.09": [
    "Изменения сохранены"
  ],
  "editor.updateSettingsDirty.01": [
    "Есть несохранённые изменения"
  ],
  "editor.updateSettingsDirty.02": [
    "Изменения сохранены"
  ],
  "editor.saveSettings.01": [
    "Добавьте оба раздела и инструкции под ними. Объём правил — не больше 32 КБ."
  ],
  "editor.saveSettings.02": [
    "Настройки сохранены"
  ],
  "editor.dateDialog.01": [
    "Пересечения не найдены"
  ],
  "editor.dateDialog.02": [
    "Проверьте периоды работы"
  ],
  "editor.dateDialog.03": [
    "Проверка дат"
  ],
  "editor.dateDialog.04": [
    "Эти два периода не пересекаются. Даты можно изменить в фактах."
  ],
  "editor.dateDialog.05": [
    "Для расчёта укажите месяц и год начала обоих мест работы и окончания предыдущего. Например, 2022-03. Даты можно изменить в фактах."
  ],
  "editor.dateDialog.06": [
    "Периоды пересекаются"
  ],
  "editor.dateDialog.07": [
    "Проверка дат"
  ],
  "editor.exportDialog.01": [
    "Сначала откройте резюме."
  ],
  "editor.exportDialog.02": [
    "Экспорт DOCX"
  ],
  "editor.saveDialog.01": [
    "Открыть проект"
  ],
  "editor.saveDialog.02": [
    "Сохранить проект"
  ],
  "editor.saveDialog.03": [
    "Продолжить работу"
  ],
  "editor.saveDialog.04": [
    "Файл .foldcv"
  ],
  "editor.saveDialog.05": [
    "Прототип открывает только свои файлы .demo.json. Файлы .foldcv открываются в основном приложении."
  ],
  "editor.saveDialog.06": [
    "Прототип сохраняет данные в .demo.json. Для работы в приложении нужен файл .foldcv."
  ],
  "editor.saveDialog.07": [
    "Файл .demo.json"
  ],
  "editor.saveDialog.08": [
    "Открыть .demo.json"
  ],
  "editor.saveDialog.09": [
    "Скачать .demo.json"
  ],
  "editor.downloadDemo.01": [
    "Файл .demo.json скачан"
  ],
  "editor.openDemo.01": [
    "Архив .foldcv открывается в основном приложении. Здесь нужен снимок .demo.json."
  ],
  "editor.openDemo.02": [
    "Демонстрационный снимок должен быть меньше 10 МБ."
  ],
  "editor.openDemo.03": [
    "Файл .demo.json открыт"
  ],
  "editor.openDemo.04": [
    "Этот файл не является поддерживаемым снимком прототипа."
  ],
  "editor.beginRewrite.01": [
    "Выберите текст в документе."
  ],
  "editor.beginRewrite.02": [
    "Сократи, сохрани смысл и факты"
  ],
  "editor.renderRewrite.01": [
    "этот блок"
  ],
  "editor.renderRewrite.02": [
    "выделенный фрагмент"
  ],
  "editor.prepareRewrite.01": [
    "Блок удалён. Выберите другой текст."
  ],
  "editor.prepareRewrite.02": [
    "Фронтенд-разработчик. Создаю продуктовые интерфейсы на React и TypeScript — от первых экранов до поддержки после запуска. В команде «Север» развиваю личный кабинет и библиотеку компонентов. Уделяю внимание доступности и качеству кода."
  ],
  "editor.prepareRewrite.03": [
    "Разрабатываю личный кабинет и общие компоненты на React и TypeScript. Подключаю API и покрываю ключевые сценарии тестами. Вместе с дизайнером улучшаю доступность и согласованность интерфейса."
  ],
  "editor.prepareRewrite.04": [
    "Фронтенд-разработчик продуктовых интерфейсов."
  ],
  "editor.applyRewrite.01": [
    "Выделение изменилось. Выберите текст заново."
  ],
  "editor.applyRewrite.02": [
    "Выделенный текст изменён"
  ],
  "editor.applyRewrite.03": [
    "Правка применена. Её можно отменить."
  ],
  "editor.openSource.01": [
    "Исходный текст"
  ],
  "editor.openSource.02": [
    "Источник"
  ],
  "editor.deleteProject.01": [
    "Удалить резюме?"
  ],
  "editor.deleteProject.02": [
    "История"
  ],
  "editor.deleteProject.03": [
    "Резюме удалено"
  ],
  "editor.aboutDialog.01": [
    "О прототипе"
  ],
  "editor.insertLink.01": [
    "Добавить ссылку"
  ],
  "editor.insertLink.02": [
    "Редактирование"
  ],
  "editor.insertLink.03": [
    "Портфолио"
  ],
  "editor.insertLink.04": [
    "Используйте адрес http:// или https://."
  ],
  "editor.insertTable.01": [
    "Добавить таблицу"
  ],
  "editor.insertTable.02": [
    "Редактирование"
  ],
  "editor.insertTable.03": [
    "Навык"
  ],
  "editor.insertTable.04": [
    "Уровень"
  ],
  "editor.readImage.01": [
    "Выберите PNG, JPEG или WebP."
  ],
  "editor.readImage.02": [
    "Для прототипа выберите изображение до 3 МБ."
  ],
  "editor.readImage.03": [
    "Не удалось прочитать изображение."
  ],
  "editor.readImage.04": [
    "Изображение добавлено локально."
  ],
  "editor.events.03": [
    "Сократи, сохрани смысл и факты"
  ],
  "editor.events.04": [
    "Сделай формулировку яснее, сохрани факты"
  ],
  "editor.events.05": [
    "Экспорт DOCX"
  ],
  "editor.events.06": [
    "Даты оставлены без изменений"
  ],
  "editor.events.07": [
    "Даты изменились. Откройте проверку заново."
  ],
  "editor.events.08": [
    "Даты изменены"
  ],
  "editor.events.09": [
    "Резюме — пример.txt"
  ],
  "editor.events.10": [
    "Изменения отменены."
  ],
  "editor.events.11": [
    "Подключение показано для примера. Вход не выполнялся."
  ],
  "editor.events.12": [
    "Модель отключена. Сохраните настройки."
  ],
  "editor.events.13": [
    "Это пример результата. Подключение к Codex не проверялось."
  ],
  "editor.events.14": [
    "Резюме — пример.txt"
  ],
  "chat.vacancy.01": [
    "Фронтенд-разработчик. React, TypeScript, доступность интерфейсов, тестирование и работа с дизайнером. Пример вакансии для прототипа."
  ],
  "chat.shortened.01": [
    "Фронтенд-разработчик. Создаю интерфейсы на React и TypeScript. В команде «Север» разрабатываю личный кабинет и библиотеку компонентов. Уделяю внимание доступности и качеству кода."
  ],
  "chat.chars.01": [
    "знак"
  ],
  "chat.chars.02": [
    "знака"
  ],
  "chat.chars.03": [
    "знаков"
  ],
  "chat.newThread.01": [
    "Новый диалог"
  ],
  "chat.captureContext.01": [
    "Фрагмент · ",
    "",
    ""
  ],
  "chat.captureContext.02": [
    "Убрать выделенный фрагмент"
  ],
  "chat.messageHtml.01": [
    "Вы"
  ],
  "chat.messageHtml.02": [
    "Помощник"
  ],
  "chat.messageHtml.03": [
    "Работа остановлена"
  ],
  "chat.messageHtml.04": [
    "Не удалось завершить"
  ],
  "chat.messageHtml.05": [
    "",
    " действия"
  ],
  "chat.messageHtml.06": [
    "Правка отменена"
  ],
  "chat.messageHtml.07": [
    "Изменён 1 блок"
  ],
  "chat.messageHtml.08": [
    "Скопировать ответ"
  ],
  "chat.messageHtml.09": [
    "Повторить"
  ],
  "chat.messageHtml.10": [
    "Ответить заново"
  ],
  "chat.scopeText.01": [
    "Фрагмент · ",
    ""
  ],
  "chat.scopeText.02": [
    "Всё резюме"
  ],
  "chat.render.01": [
    "Новый диалог"
  ],
  "chat.render.02": [
    "История диалогов"
  ],
  "chat.render.03": [
    "Уменьшить чат"
  ],
  "chat.render.04": [
    "Развернуть чат"
  ],
  "chat.render.05": [
    "Скрыть чат"
  ],
  "chat.render.06": [
    "Убрать выделенный фрагмент"
  ],
  "chat.render.07": [
    "Выделите текст в документе, чтобы обсудить его"
  ],
  "chat.render.08": [
    "Прикрепить текстовый файл"
  ],
  "chat.render.09": [
    "Модель выше — для следующего сообщения"
  ],
  "chat.render.10": [
    "Enter — отправить · Shift + Enter — новая строка"
  ],
  "chat.stop.01": [
    "Ответ остановлен."
  ],
  "chat.stop.02": [
    " Правка в резюме сохранена; её можно отменить."
  ],
  "chat.message.01": [
    "Читаю выделенный фрагмент"
  ],
  "chat.message.02": [
    "Читаю резюме и факты"
  ],
  "chat.send.01": [
    "Не удалось подключиться к модели. Сообщение сохранено. Проверьте подключение и попробуйте ещё раз."
  ],
  "chat.send.02": [
    "Прочитан фрагмент · ",
    ""
  ],
  "chat.send.03": [
    "Прочитаны текст и факты: ",
    ""
  ],
  "chat.send.04": [
    "Сопоставляю требования из вложения · пример"
  ],
  "chat.send.05": [
    "Проверяю факты и даты"
  ],
  "chat.finish.01": [
    "Работа остановлена: открыто другое резюме."
  ],
  "chat.finish.02": [
    "Текст изменился во время работы. Правка не внесена. Выделите нужный фрагмент и отправьте запрос заново."
  ],
  "chat.finish.03": [
    "Фронтенд-разработчик продуктовых интерфейсов."
  ],
  "chat.finish.04": [
    "Не удалось найти фрагмент. Выделите его заново."
  ],
  "chat.finish.05": [
    "Помощник изменил текст"
  ],
  "chat.finish.06": [
    "Выделенный фрагмент"
  ],
  "chat.finish.07": [
    "О специалисте"
  ],
  "chat.finish.08": [
    "Изменён 1 блок; проверены связанные факты"
  ],
  "chat.finish.09": [
    "Сократил выделенный фрагмент. Текст вокруг него сохранён."
  ],
  "chat.finish.10": [
    "Сократил раздел «О специалисте»: убрал повторы и общие формулировки. Опыт, технологии и названия компаний сохранены."
  ],
  "chat.finish.11": [
    "Для этого текста в скетче нет готовой правки. Резюме осталось без изменений."
  ],
  "chat.finish.12": [
    "Сопоставление завершено · пример"
  ],
  "chat.finish.13": [
    "В примере вакансии нужны React, TypeScript, тестирование и работа с дизайнером. Сопоставьте эти требования с описанием опыта.\n\nДля более точного отклика стоит уточнить личный вклад и результаты работы. Новые навыки и достижения не добавлены."
  ],
  "chat.finish.14": [
    "Файл «",
    "» добавлен к сообщению. В нём ",
    ".\n\nВ скетче можно просмотреть вложение. Анализ произвольного файла здесь не выполняется."
  ],
  "chat.finish.15": [
    "Проверка завершена"
  ],
  "chat.finish.16": [
    "Прочитал выделенный фрагмент. В скетче можно запросить его сокращение. Текст не изменён."
  ],
  "chat.finish.17": [
    "Прочитал резюме: ",
    ". Сверил сведения в панели фактов. Резюме не изменено."
  ],
  "chat.finish.18": [
    "Уточнить даты работы"
  ],
  "chat.finish.19": [
    "У «Севера» и «Студии Линия» пересекаются периоды. Это может быть параллельная работа."
  ],
  "chat.finish.20": [
    "Сократить общие формулировки"
  ],
  "chat.finish.21": [
    "В разделе «О специалисте» можно точнее описать вклад и убрать повторы."
  ],
  "chat.demo.01": [
    "Проверка резюме"
  ],
  "chat.demo.02": [
    "Проверь резюме. Что стоит уточнить перед отправкой?"
  ],
  "chat.demo.03": [
    "Прочитаны текст и факты резюме"
  ],
  "chat.demo.04": [
    "Проверены даты работы"
  ],
  "chat.demo.05": [
    "Проверены связанные сведения"
  ],
  "chat.demo.06": [
    "В примере нашлись два места для уточнения. Резюме не изменено."
  ],
  "chat.demo.07": [
    "Уточнить даты работы"
  ],
  "chat.demo.08": [
    "Два места работы пересекаются на 3 месяца. Если работа была параллельной, даты можно оставить."
  ],
  "chat.demo.09": [
    "Сократить описание"
  ],
  "chat.demo.10": [
    "В разделе «О специалисте» есть общие фразы. Можно оставить опыт, технологии и личный вклад."
  ],
  "chat.demo.11": [
    "Проверь резюме и укажи, что стоит уточнить."
  ],
  "chat.events.01": [
    "Работа остановлена при переходе на другой экран."
  ],
  "chat.events.02": [
    "Вакансия — пример.txt"
  ],
  "chat.events.03": [
    "Сравни резюме с требованиями вакансии."
  ],
  "chat.events.04": [
    "Этот блок уже удалён."
  ],
  "chat.events.05": [
    "Источник"
  ],
  "chat.events.06": [
    "После этой правки были другие изменения. Используйте общую отмену в редакторе."
  ],
  "chat.events.07": [
    "Ответ скопирован"
  ],
  "chat.events.08": [
    "Не удалось скопировать. Выделите текст ответа вручную."
  ],
  "chat.events.09": [
    "Выберите TXT или Markdown до 20 КБ."
  ],
  "chat.events.10": [
    "Не удалось прочитать файл."
  ]
};
  function fill(table, name, values) {
    const parts = table[name];
    if (!parts || values.length !== parts.length - 1) throw new Error("Invalid visual template: " + name);
    return parts.reduce((html, part, index) => html + (index ? String(values[index - 1]) : "") + part, "");
  }
  window.FoldCVVisual = Object.freeze({
    markup: (name, ...values) => fill(templates, name, values),
    text: (name, ...values) => fill(copy, name, values),
  });
})();
