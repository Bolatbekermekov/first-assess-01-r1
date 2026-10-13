# Нормативный контракт FIRST-ASSESS-01 R1

Это локальные схемы проверки кандидата. Они не являются контрактами production FIRST. Все функции используют только стандартную библиотеку Python 3.12. Входные mutable объекты не изменять, mutable выходы не разделяют память с входами. Результат не зависит от текущего времени, случайности, окружения, сети или предыдущих запусков.

## API

В `assess_workbench/api.py` экспортировать:

```python
class WorkbenchError(ValueError):
    # .code — стабильный код, str(error) == code, без входных значений.
    ...
def load_rows(data: bytes, *, format: str) -> list: ...
def analyze_rows(rows: list, *, scope: dict) -> dict: ...
def render_html(report: dict) -> str: ...
```

В каркасе эти функции не реализованы. Можно создавать внутренние модули в `assess_workbench/`. `__init__.py` не обязан реэкспортировать API. Импорт не вызывает CLI, чтение файлов или другие побочные эффекты.

## 1. Scope и ограничения API

`scope` — обычный dict с ровно тремя ключами:

```json
{"schema_version":"ASSESS_SCOPE_V1","client_id":"synthetic-client","campaign_id":"synthetic-campaign"}
```

Оба ID — str, ASCII fullmatch `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`. Это локальные идентификаторы стенда; не следует выдавать их за проверенный runtime campaign UUID. Схема сравнивается точно.

`analyze_rows`: сначала проверить scope целиком (ошибка INVALID_SCOPE), затем тип rows — именно list (INVALID_ROWS), затем длину <= 10000 (TOO_MANY_ROWS). Пустой список допустим. После этих проверок некорректная отдельная строка становится REJECTED в отчёте и не вызывает исключение. Подклассы dict/list/str не требуется поддерживать; для примитивов контракт проверяется по точному builtin типу. bool не считается int.

## 2. Поля ряда и точная нормализация

Каждый ряд — dict ровно с шестью полями в указанном порядке проверки:

`company_name`, `contact_email`, `website_url`, `country_code`, `language`, `source_ref`.

Не dict или неизвестные/отсутствующие ключи: ряд REJECTED, codes=[INVALID_ROW_SCHEMA]. Не пытаться дополнительно проверять поля этого ряда. Иначе проверить все шесть полей и накопить не более одного кода на поле в порядке выше.

Общее правило для каждого поля: тип именно str, исходная длина <= 4096 Unicode code points, нет символов NUL, управляющих U+0001..U+001F / U+007F и surrogate code points U+D800..U+DFFF. Это означает, что встроенные табы/переводы строк недопустимы; внешние обычные пробелы допускаются. Нарушение общего правила даёт только код этого поля. Пределы ниже применяются после описанной нормализации. Не выполнять HTML unescape, URL decode, транслитерацию или NFKC.

| Поле | Нормализация и проверка | Код |
|---|---|---|
| company_name | Unicode NFC, затем `" ".join(value.split())`; длина 1..200 | INVALID_COMPANY_NAME |
| contact_email | `strip().lower()`; только ASCII, длина <=254; fullmatch `[a-z0-9.!#$%&'*+/=?^_\x60{\x7c}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+`; локальная часть <=64, не начинается/заканчивается точкой, не содержит `..`; каждая domain label <=63 | INVALID_CONTACT_EMAIL |
| website_url | strip(); пустая строка допустима; иначе длина <=2048, только ASCII без любого whitespace, начинается точно `https://`; разобрать urlsplit; непустой hostname с как минимум одной точкой и label regex `[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?`, каждая label <=63, hostname <=253; username/password/port запрещены, netloc не содержит `:`, `@`, `[`, `]`; fragment запрещён, в том числе пустой `#`; hostname lowercase, сохранить path и query без декодирования; `https://example.test` и `https://example.test/` остаются различными. Пустой конечный `?` допускается и исчезает при urlunsplit; иные path/query сохраняются. | INVALID_WEBSITE_URL |
| country_code | strip().upper(); пустая строка или fullmatch ASCII `[A-Z]{2}`; это синтаксис, не сверка справочника стран | INVALID_COUNTRY_CODE |
| language | strip(); пустая строка или fullmatch ASCII `[A-Za-z]{2}(?:-[A-Za-z]{2})?`; primary lowercase, region uppercase, например EN-us → en-US | INVALID_LANGUAGE |
| source_ref | strip(); длина 1..200; сохранить регистр и внутренние пробелы; это непрозрачная ссылка на источник, её не открывать | INVALID_SOURCE_REF |

В таблице backtick внутри email regex обозначен escape `\x60`, который соответствует обычному символу U+0060. Unicode casefold применяется только при сравнении названия компании ниже. Email normalization intentionally ограничен описанной ASCII схемой, это не полный RFC-парсер и не проверка доставляемости.

Если хотя бы одно поле невалидно: status REJECTED, normalized=null, codes — все ошибки по порядку, duplicate_of_row=null. Даже если email валиден, такой ряд полностью исключён из поиска дублей.

## 3. Группировка точных дублей и конфликтов

Группировать только валидные строки по точному нормализованному contact_email внутри данного scope. Другие наборы/запуски не сравниваются. Изменение scope не меняет классификацию рядов, но scope результата обязательно соответствует входу.

Для каждого ряда ключ метаданных — кортеж:

`(normalized.company_name.casefold(), normalized.website_url, normalized.country_code, normalized.language)`.

source_ref не входит в ключ: разные ссылки на источник не превращают одинаковый контакт в конфликт. Название в выходе сохраняется с нормализованным регистром исходного ряда, не заменяется названием другого ряда.

- Группа из одного валидного ряда: UNIQUE, codes=[VALID_RECORD], duplicate_of_row=null.
- Группа из нескольких рядов с одинаковым ключом метаданных: самый ранний ряд UNIQUE, остальные DUPLICATE, codes=[EXACT_DUPLICATE], duplicate_of_row — номер первого ряда. Никакие поля рядов не сливаются и не отбрасываются.
- Если внутри email-группы есть хотя бы два разных ключа метаданных: **все** её ряды CONFLICT, codes=[EMAIL_METADATA_CONFLICT], duplicate_of_row=null. Даже два одинаковых первых ряда становятся CONFLICT, если третий отличается. Пустое значение и непустое различаются; это конфликт, автоматического обогащения нет.

Идентичный website или company_name при разных email не означает дубль. Подадресация `+tag`, точки в local part и похожие домены не удаляются. Никакой fuzzy-дедупликации. Порядок выхода равен порядку входных рядов; номера 1-based. Перестановка рядов может изменить представителя DUPLICATE, что ожидаемо.

## 4. Выход analyze_rows

Обычный dict ровно со следующими ключами:

```json
{
  "schema_version":"ASSESS_LEAD_REPORT_V1",
  "scope":{"schema_version":"ASSESS_SCOPE_V1","client_id":"synthetic-client","campaign_id":"synthetic-campaign"},
  "summary":{"total":0,"unique":0,"duplicate":0,"conflict":0,"rejected":0},
  "rows":[]
}
```

Каждый rows элемент ровно `{row_number,status,codes,normalized,duplicate_of_row}`. row_number — int начиная с1. normalized — dict ровно из шести канонических полей либо null. status — UNIQUE/DUPLICATE/CONFLICT/REJECTED. codes — непустой list строк по правилам выше. summary содержит количества рядов, не групп; total равен сумме четырёх статусов. Отчёт не содержит сырой вход, момент запуска, случайные ID или разрешения на дальнейшие действия.

## 5. load_rows: bytes → list

Порядок ошибок: data type (INVALID_DATA), format строго 'json' или 'csv' (INVALID_FORMAT), bytes limit 10485760 включительно (INPUT_TOO_LARGE), UTF-8 decoding с допускаемым единственным BOM в начале (INVALID_ENCODING), синтаксис/структура файла (INVALID_DOCUMENT), количество рядов (TOO_MANY_ROWS). Не выводить фрагменты входа в исключениях.

JSON: обычный JSON array. Пустой array допустим. Некорректные элементы array передаются неизменёнными в анализатор для REJECTED. Запрещены повторяющиеся ключи в любом JSON object, NaN/Infinity/-Infinity; после корневого значения допускается только JSON whitespace. Не array → INVALID_DOCUMENT. Ошибку RecursionError парсера преобразовать в INVALID_DOCUMENT. JSON string/number/null values в отдельных рядах допустимы на этой стадии; analyze_rows даст REJECTED. Пустой файл → INVALID_DOCUMENT.

CSV: UTF-8, разделитель comma, quotechar double quote, doublequote=True, strict=True; CRLF или LF. Заголовок — ровно шесть названий полей выше, без повторов и в любом порядке. Никаких комментариев, автоматической нормализации заголовка, дополнительных колонок или пропуска строк. Число ячеек каждой записи должно быть ровно6. Даже пустая физическая CSV запись, которую csv.reader выдаёт как [], — INVALID_DOCUMENT. Перевод строки внутри quoted cell поддерживается парсером, но значение затем REJECTED по общему правилу полей. Для чтения csv использовать StringIO(newline=''). Только header → пустой список. Ошибки csv.Error, duplicate headers, wrong header/cell count → INVALID_DOCUMENT. Конечный обычный line terminator не считается дополнительной пустой записью. Проверка лимита строк после полного успешного синтаксического разбора; не маскировать malformed document кодом TOO_MANY_ROWS. csv.field_size_limit установить достаточно высоким для всех файлов допустимого bytes limit и восстановить после использования.

## 6. render_html

Принимает только отчёт, полученный analyze_rows. Полная повторная проверка произвольного отчёта не требуется. Вернуть детерминированный полный документ с doctype/html/head/meta charset UTF-8/body, видимыми scope, summary и таблицей всех рядов, их номером, статусом, reason codes, всеми нормализованными полями и duplicate_of_row. Для REJECTED показать причину, не исходный вход. Пустой набор показать явно.

Все значения из данных, включая scope/поля/codes, экранировать `html.escape(str(value), quote=True)` перед HTML-вставкой. Не создавать из website/source_ref ссылок, атрибутов, скриптов или событий. Никаких script/iframe/form, внешних styles/fonts/images, JavaScript, сетевых адресов ресурсов. Допускается статический встроенный CSS. Отчёт читается как локальный файл. Поля не скрываются и не сокращаются. HTML-шаблон и стили на усмотрение автора, точное равенство байтов HTML с эталоном не требуется; одинаковый report даёт одинаковый HTML.

## 7. CLI

```text
python -m assess_workbench --input FILE --format json|csv --client-id ID --campaign-id ID --out-dir NEW_DIRECTORY
```

Все пять параметров обязательны. Чтение только заданного входа. out-dir не должен существовать; его родитель уже должен быть существующим каталогом. Никогда не перезаписывать или удалять существующий путь. Сначала полностью прочитать/проанализировать вход и сгенерировать оба содержимых отчёта, затем создать out-dir через mkdir(exist_ok=False). Не создавать каталог при ошибке входных данных. Не следовать существующему symlink out-dir. Race на mkdir трактуется OUTPUT_EXISTS. Если запись после успешного создания собственного каталога не удалась, вернуть IO_ERROR; частично созданный каталог разрешено оставить, но не заявлять успешный отчёт и не удалять чужие пути.

Успех создаёт ровно report.json и report.html внутри out-dir. JSON: ensure_ascii=False, sort_keys=True, indent=2, финальный LF, UTF-8 без BOM. HTML: UTF-8 без BOM. Ряды REJECTED/CONFLICT — результат анализа, не ошибка CLI: exit0, stdout ровно `REPORT_CREATED\n`, stderr пусто. Ошибка аргументов argparse может выводить стандартную справку, exit2; пользовательские значения не должны попадать в собственные исключения/traceback. Для ошибок после разбора аргументов stdout пусто, stderr ровно `ERROR <CODE>\n`, exit2. WorkbenchError → его code; проблемы чтения/записи/родителя → IO_ERROR; уже существующий out-dir → OUTPUT_EXISTS. Не ловить KeyboardInterrupt/SystemExit как успешный результат. Каркас без реализации может завершаться отдельным NOT_IMPLEMENTED; это не допустимое поведение готового возврата.

Порядок CLI: разбор аргументов; read input (OSError → IO_ERROR); load_rows; analyze_rows; render_html; проверка/создание out-dir; запись. Если и input плох, и output уже существует, приоритет имеет ошибка входа. Избегать чтения файла целиком сверх лимита: достаточно read(limit+1) и INPUT_TOO_LARGE. Это ограничение CLI не меняет контракт load_rows.

## 8. Независимость и граница результата

Вычислительные API не открывают файлы и не используют сеть. Файловый ввод/вывод только в CLI по указанным путям. Все production namespaces FIRST отсутствуют. Связь с проектом — предметная область и возможное будущее переиспользование, а не импорт соседнего модуля. Предложение будущей интеграции не является частью её реализации и требует отдельного решения/контракта. Возврат не увеличивает продуктовый прогресс автоматически.
