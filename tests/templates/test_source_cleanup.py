"""The no-rewrite mode keeps source wording but not list punctuation or the candidate's contacts."""

import pytest

from packages.resume_core.template_source_cleanup import clean_source_wording, list_item_text, without_contacts


@pytest.mark.parametrize(('source', 'shown'), [
    ('- Разработка API;', 'Разработка API'),
    ('– Настройка CI.', 'Настройка CI'),
    ('— Поддержка релизов,', 'Поддержка релизов'),
    ('• Ревью кода', 'Ревью кода'),
    ('*Менторинг', 'Менторинг'),
    ('1. Разработка', 'Разработка'),
    ('12) Разработка', 'Разработка'),
    ('Первая часть.\n- вторая часть.', 'Первая часть.\nвторая часть'),
])
def test_a_list_item_loses_its_marker_and_closing_punctuation(source, shown):
    assert list_item_text(source) == shown


@pytest.mark.parametrize('kept', ['-5% затрат', '3D-моделирование', '.NET и C#', 'Работа с БД и т.д.', 'Перенос данных и др.',
    'Ожидание результата...', 'Рост в 2 раза', 'Node.js', 'Этап 1: анализ:'])
def test_wording_that_only_looks_like_punctuation_stays(kept):
    assert list_item_text(kept) == kept


def test_a_list_item_of_nothing_but_marks_keeps_its_text():
    assert list_item_text('- .') == '- .'


@pytest.mark.parametrize(('source', 'shown'), [
    ('Телефон: +7 (916) 123-45-67', ''),
    ('Email: ivan.petrov@example.com', ''),
    ('8 916 123 45 67, ivan@example.com', ''),
    ('Telegram: @ivan_petrov', ''),
    ('Telegram @ivan_petrov', ''),
    ('https://t.me/ivan_petrov', ''),
    ('https://www.linkedin.com/in/ivan-petrov/', ''),
    ('hh.ru/resume/0123456789', ''),
    ('Backend-разработчик. Почта: ivan@example.com', 'Backend-разработчик.'),
    ('Опыт 5 лет\nТелефон: +7 916 123 45 67\nGo и Kafka', 'Опыт 5 лет\nGo и Kafka'),
])
def test_contacts_leave_the_text(source, shown):
    assert without_contacts(source) == shown


@pytest.mark.parametrize('kept', ['Бот для Telegram на Go', 'Интеграция с hh.ru и LinkedIn', 'Проект https://github.com/example/tool',
    'Рост 2015-2019 и 2020-2024', 'Оборот 800 000 рублей', 'Обработка 1 000 000 событий', 'Skype for Business'])
def test_ordinary_text_about_services_and_numbers_stays(kept):
    assert without_contacts(kept) == kept


def test_only_list_pointers_lose_their_punctuation():
    assert clean_source_wording('- Разработка.', '/0/tasks/1/value') == 'Разработка'
    assert clean_source_wording('- Разработка.', '/items/1') == 'Разработка'
    assert clean_source_wording('Разработка сервисов.', '/text') == 'Разработка сервисов.'
    assert clean_source_wording('Разработка сервисов.', '/0/project/description') == 'Разработка сервисов.'
    assert clean_source_wording('Телефон: +7 916 123 45 67', '/0/tasks/1/value') == ''


@pytest.mark.parametrize(('source', 'shown'), [
    ('- Результат: Сократил время сборки.', 'Сократил время сборки'),
    ('Решение: Разделил работу на три потока.', 'Разделил работу на три потока'),
    ('Задачи:\n- Разработка API;\n- Настройка CI.', 'Разработка API;\nНастройка CI'),
    ('Основные технологии: Kotlin, Spring.', 'Kotlin, Spring'),
    ('Project: Billing platform', 'Billing platform'),
])
def test_a_list_item_loses_the_label_the_source_gave_its_kind(source, shown):
    assert clean_source_wording(source, '/0/results/0/value') == shown


def test_a_text_field_loses_its_marker_and_label_but_keeps_its_closing_punctuation():
    assert clean_source_wording('- Суть проекта: Система управления доступом.', '/0/project/description') == 'Система управления доступом.'
    assert clean_source_wording('Роль: Архитектор.', '/0/role_details/scope') == 'Архитектор.'


@pytest.mark.parametrize('kept', ['Этап 1: анализ', 'Java: 5 лет', 'Результативность: высокая', 'Проектная работа'])
def test_wording_that_only_looks_like_a_label_stays(kept):
    assert clean_source_wording(kept, '/0/tasks/0/value') == kept


def test_a_line_of_nothing_but_a_label_keeps_its_text():
    assert clean_source_wording('Задачи:', '/0/tasks/0/value') == 'Задачи:'


LINE = ('- Результат:  Сборка занимала 40 минут. После переноса кэша она занимает 12 минут. '
    'На проекте было два разработчика и один тестировщик. Сбоев на приёмочных испытаниях не зафиксировано.')


@pytest.mark.parametrize('value', [
    'На проекте было два разработчика и один тестировщик.',
    'Сбоев на приёмочных испытаниях не зафиксировано',
    'Сборка занимала 40 минут. После переноса кэша она занимает 12 минут.',
    'Результат: Сборка занимала 40 минут.',
    'сбоев на приёмочных испытаниях не зафиксировано.',
])
def test_a_value_made_of_the_cited_sentences_is_verbatim(value):
    from packages.resume_core.template_wording import verbatim
    assert verbatim(value, LINE)


@pytest.mark.parametrize('value', ['Сократил сборку с 40 до 12 минут.', 'Сбоев не зафиксировано', ''])
def test_a_reworded_or_shortened_sentence_is_not_verbatim(value):
    from packages.resume_core.template_wording import verbatim
    assert not verbatim(value, LINE)
    assert not verbatim('x', '')


def test_verbatim_ignores_the_form_of_lines():
    from packages.resume_core.template_wording import verbatim
    assert verbatim('создание веб-сервисов с нуля (REST, SOAP) в сфере здравоохранения',
        '- Создание веб-сервисов с нуля (REST, SOAP) в сфере здравоохранения;')
    assert verbatim('Первая часть\nвторая часть', 'Первая часть.\n- вторая часть.')
