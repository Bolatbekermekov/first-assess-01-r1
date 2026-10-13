# Synthetic fixtures

Все имена, контакты и ссылки вымышленные. Сеть для них не используется.

- leads.json и leads.csv содержат одни и те же шесть логических рядов.
- expected_report.json — полный ожидаемый результат, не генерируется кодом кандидата.
- invalid_rows.json/invalid_expected.json — форма ряда и порядок ошибок всех полей.
- empty.json/empty_expected.json — пустой набор.
- scope.json — локальный scope для этих примеров.

В leads: первые два ряда — UNIQUE/DUPLICATE, третий и четвёртый — оба CONFLICT, пятый — REJECTED, шестой проверяет безопасный HTML-вывод. Символы `<script>` — обычные текстовые данные, не инструкция и не исполняемый код.
