# TEST_MATRIX — FIRST-ASSESS-01, возврат R5

Требование (пункт `CONTRACT.md` или критерий приёмки) → тест → фактический журнал → статус. Строки, изменённые в R5, помечены **R5**; пометки **R2**/**R3**/**R4** сохранены. Разбор: `docs/R2_REWORK.md`, `docs/R3_REWORK.md`, `docs/R4_REWORK.md`, `docs/R5_REWORK.md`.

**Обозначения тестов.** «Свой» — `tests/test_candidate_<модуль>.py`, записан как `<модуль>.<Класс>.<тест>`; `*` означает все тесты класса. «Публичный» — `tests/test_public_acceptance.py`.

**Журналы.**
- Свои тесты: `logs/04_candidate_tests.txt` (Linux, 155/155 OK) и `logs/13_macos_candidate_tests.txt` (macOS, 155/155 OK).
- Публичные: `logs/03_run_acceptance.txt` и `evidence/` (Linux, 12/12, `PASS_PUBLIC_ONLY`), `logs/14_macos_public_tests.txt` (macOS, 12/12).
- Регрессионные проверки R5:

  | Журнал | Содержание |
  |---|---|
  | 17 | регрессионные тесты на коде возврата R4 (`git archive` `6ccf025`, 11/11 файлов): FAILED — на R4 сценарий подмены родителя даёт ложный `REPORT_CREATED` |
  | 18 | те же тесты на R5: OK |
  | 22 | доверенный родитель → out-dir `0700` владельцу; недоверенный (мир-записываемый без sticky) → `IO_ERROR` до создания, out-dir не создан |
  | 19, 20, 21 | воспроизведение и стоимость замечания 1 (принято в R2, остаётся зелёным) |

Статус PASS означает, что тест прошёл в обоих прогонах (Linux и macOS), если не указано иное.

## Общие требования и API

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| G1 | Только стандартная библиотека Python 3.12 | свой `isolation.IsolationTests.test_package_imports_only_the_standard_library` | 04, 13 | PASS |
| G2 | Импорт не вызывает CLI, чтение файлов и других побочных эффектов | свой `isolation.IsolationTests.test_import_has_no_side_effects` | 04, 13 | PASS |
| G3 | `WorkbenchError`: `.code`, `str(e) == code`, без входных значений, в том числе через `__cause__` и `__context__` | свои `report.ScopeAndRowListTests.*`, `loading.ErrorHygieneTests.test_errors_do_not_carry_input`, `loading.*` (каждая ошибка проверяет `__context__ is None`); публичный `test_parser_errors_and_precedence` | 03, 04, 13 | PASS |
| G4 | Входы не изменяются; выход не делит изменяемую память со входом | свои `report.IsolationTests.test_inputs_are_not_mutated`, `…test_output_shares_no_mutable_objects_with_input_or_between_rows`, `…test_mutating_a_report_affects_neither_input_nor_later_reports`; публичный `test_literal_golden_and_input_immutability` | 03, 04 | PASS |
| G5 | Детерминизм: результат не зависит от времени, случайности и предыдущих запусков | свои `report.IsolationTests.test_result_is_deterministic`, `html.HtmlTests.test_rendering_is_deterministic_and_does_not_mutate_the_report`; совпадение отчётов JSON- и CSV-запусков | 04, 08 | PASS |
| G6 | Логика вычисляется, а не подменяется lookup-таблицей по fixtures | свои `isolation.IsolationTests.test_package_holds_no_fixture_answers`, `properties.RandomizedInvariantTests.test_random_batches_follow_the_contract` (150 случайных наборов против независимого оракула) | 04, 13 | PASS |
| G7 | **R2.** Результат не зависит от окружения: CLI в отдельных процессах при `-X int_max_str_digits=640` и `=0`, `PYTHONINTMAXSTRDIGITS=4300`, `PYTHONHASHSEED=0` и `=4242`, `LC_ALL=C PYTHONUTF8=0` даёт тот же exit, stdout, stderr и побайтно те же отчёты; глубина JSON не зависит от `sys.setrecursionlimit`. Что остаётся зависимым — `LIMITATIONS.md`, раздел 2 | свои `environment.EnvironmentTests.test_interpreter_settings_and_locale_do_not_change_the_result`, `loading.JsonDocumentTests.test_nesting_limit_does_not_follow_sys_setrecursionlimit` | 04, 13, 18, 20 | PASS |

## §1 Scope и `analyze_rows`

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| S1 | scope — точный `dict` ровно с тремя ключами; схема сравнивается точно | свои `report.ScopeAndRowListTests.test_scope_must_be_an_exact_dict_with_exactly_three_keys`, `…test_schema_version_is_compared_exactly` | 04 | PASS |
| S2 | ID: `str`, ASCII fullmatch `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}` | свой `report.ScopeAndRowListTests.test_scope_identifiers` (границы 128/129, Unicode, перевод строки в конце) | 04 | PASS |
| S3 | Порядок `INVALID_SCOPE` → `INVALID_ROWS` → `TOO_MANY_ROWS`; 10 000 рядов допустимо | свои `report.ScopeAndRowListTests.test_check_order_is_scope_then_rows_type_then_length`, `…test_row_limit_is_inclusive`; публичный `test_scope_and_row_limits` | 03, 04 | PASS |
| S4 | Некорректный ряд становится REJECTED, а не исключением | свой `fields.RowSchemaAndCodeOrderTests.test_schema_violations_skip_field_checks`; публичный `test_empty_and_invalid_literal_reports` | 03, 04 | PASS |
| S5 | Точные builtin-типы; подклассы отвергаются; `bool` не является `int` (решение A8) | свои `report.*` (`OrderedDict`, подклассы `str` и `list`), `fields.GeneralRuleTests.test_values_must_be_exact_str`, `loading.ErrorPrecedenceTests.test_data_must_be_exact_bytes` | 04 | PASS |

## §2 Поля

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| F1 | Не `dict` или неверный набор ключей → `[INVALID_ROW_SCHEMA]`, поля не проверяются | свой `fields.RowSchemaAndCodeOrderTests.test_schema_violations_skip_field_checks` | 04 | PASS |
| F2 | Проверяются все шесть полей, не более одного кода на поле, порядок полей фиксирован | свои `fields.RowSchemaAndCodeOrderTests.test_all_six_codes_in_field_order`, `…test_codes_follow_field_order_not_key_order`; публичный `test_empty_and_invalid_literal_reports` | 03, 04 | PASS |
| F3 | Общее правило: точный `str`, ≤ 4096 code points до нормализации, без C0/DEL/суррогатов в любой позиции | свои `fields.GeneralRuleTests.*`; публичные `test_url_and_control_character_boundaries`, `test_surrogate_text_rejected` | 03, 04 | PASS |
| F4 | `company_name`: NFC, схлопывание пробелов, длина 1..200 после нормализации (NFC может удлинить строку) | свои `fields.CompanyNameTests.*` | 04 | PASS |
| F5 | `contact_email`: `strip().lower()`, ASCII, ≤ 254, regex, local ≤ 64, точки, label ≤ 63 | свои `fields.ContactEmailTests.*` (включая A1) | 04 | PASS |
| F6 | `website_url`: пустое значение, `https://`, правила hostname, запрет userinfo/порта/`:@[]`/фрагмента (в том числе пустого `#`), нормализация host, path и query без декодирования | свои `fields.WebsiteUrlTests.*`; публичный `test_url_and_control_character_boundaries` | 03, 04 | PASS |
| F7 | `country_code`: `strip().upper()`, пусто или `[A-Z]{2}` | свои `fields.CountryCodeTests.*` (включая A2) | 04 | PASS |
| F8 | `language`: пусто или `xx(-YY)`, регистр нормализуется | свои `fields.LanguageTests.*` (в том числе отказ для `ſe`: без `re.IGNORECASE`) | 04 | PASS |
| F9 | `source_ref`: `strip()`, 1..200, регистр и внутренние пробелы сохраняются | свои `fields.SourceRefTests.*` | 04 | PASS |
| F10 | Нет HTML unescape, URL decode, транслитерации и NFKC | свои `fields.CompanyNameTests.test_nfc_and_whitespace_collapse`, `fields.WebsiteUrlTests.test_valid_urls_and_normalization`, `fields.SourceRefTests.test_trim_preserves_case_and_inner_spaces` | 04 | PASS |
| F11 | Unicode NFC/casefold и Unicode-пробелы (критерий приёмки; решение A3) | свои `fields.GeneralRuleTests.test_non_ascii_whitespace_is_removed_by_strip_and_split`, `…test_c1_controls_and_format_characters_are_not_forbidden_by_the_general_rule`, `grouping.GroupingTests.test_company_name_is_compared_casefolded_after_nfc` | 04 | PASS |
| F12 | Граничные длины (критерий приёмки) | 0/1/200/201, 64/65, 63/64, 254/255, 253/254, 2048/2049, 4096/4097 — в классах `fields.*Tests` | 04 | PASS |

## §3 Группировка

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| D1 | Группируются только валидные ряды по точному email; REJECTED не влияет на группу | свой `grouping.GroupingTests.test_rejected_rows_never_join_or_split_a_group`; публичный `test_rejected_row_does_not_poison_group_and_no_fuzzy` | 03, 04 | PASS |
| D2 | Ключ — `(casefold(name), url, country, language)`, `source_ref` в него не входит | свои `grouping.GroupingTests.test_every_metadata_field_participates`, `…test_source_ref_is_not_part_of_the_key`, `…test_url_details_are_significant` | 04 | PASS |
| D3 | Первый ряд UNIQUE, остальные DUPLICATE со ссылкой на первый; представитель — первый валидный ряд | свои `grouping.GroupingTests.test_identical_rows_point_to_the_first`, `…test_representative_is_the_first_valid_row`, `…test_reordering_changes_the_representative` | 04 | PASS |
| D4 | Два и более разных ключа → вся группа CONFLICT, включая идентичные первые ряды | свой `grouping.GroupingTests.test_a_late_difference_turns_the_whole_group_into_conflicts`; публичный `test_late_conflict_updates_entire_group` | 03, 04 | PASS |
| D5 | Пустое значение и заполненное различаются (критерий приёмки) | свой `grouping.GroupingTests.test_blank_and_populated_values_conflict` | 04 | PASS |
| D6 | Без fuzzy: `+tag`, точки и похожие домены не объединяются | свой `grouping.GroupingTests.test_no_fuzzy_matching_across_emails`; публичный `test_rejected_row_does_not_poison_group_and_no_fuzzy` | 03, 04 | PASS |
| D7 | Порядок выхода совпадает со входом, номера с 1; поля не сливаются | свои `grouping.GroupingTests.test_interleaved_groups_keep_input_order`, `…test_duplicates_are_found_after_normalization_and_keep_their_own_values`, `report.ReportSchemaTests.test_rows_follow_input_order` | 04 | PASS |
| D8 | scope не меняет классификацию | свой `report.IsolationTests.test_scope_does_not_change_classification`; публичный `test_rejected_row_does_not_poison_group_and_no_fuzzy` | 03, 04 | PASS |
| D9 | Инварианты на случайных данных; перестановка не меняет REJECTED и CONFLICT | свои `properties.RandomizedInvariantTests.test_random_batches_follow_the_contract`, `…test_permutation_keeps_rejections_and_conflicts` | 04, 13 | PASS |

## §4 Выход `analyze_rows`

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| O1 | Ровно контрактные ключи и точные типы отчёта и рядов | свои `report.ReportSchemaTests.*` | 04 | PASS |
| O2 | `summary` считает ряды, а не группы; `total` равен сумме | свои `report.ReportSchemaTests.test_summary_counts_rows`, `grouping.GroupingTests.test_summary_counts_rows_not_groups` | 04 | PASS |
| O3 | Отчёт без сырого входа | свой `report.IsolationTests.test_report_never_contains_raw_input_of_rejected_rows` | 04 | PASS |
| O4 | Эталонные отчёты fixtures | публичные `test_literal_golden_and_input_immutability`, `test_empty_and_invalid_literal_reports` | 03 | PASS |

## §5 `load_rows`

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| L1 | Порядок ошибок `INVALID_DATA` → `INVALID_FORMAT` → `INPUT_TOO_LARGE` → `INVALID_ENCODING` → `INVALID_DOCUMENT` → `TOO_MANY_ROWS` | свои `loading.ErrorPrecedenceTests.*`; публичный `test_parser_errors_and_precedence` | 03, 04 | PASS |
| L2 | Лимит 10 485 760 байт включительно (BOM учитывается) | свои `loading.LimitTests.test_json_size_limit_is_inclusive`, `…test_bom_counts_towards_the_size_limit`, `…test_csv_size_limit_is_inclusive_and_huge_fields_load` | 04 | PASS |
| L3 | Строгий UTF-8; допускается один BOM в начале (решение A5) | свои `loading.EncodingTests.*`; публичный `test_json_csv_equivalence_and_bom` | 03, 04 | PASS |
| L4 | JSON: корень — массив; дубли ключей на любой вложенности (критерий приёмки); `NaN`/`Infinity`; хвост; `RecursionError`; пустой файл (A7, A11) | свои `loading.JsonDocumentTests.*` | 04 | PASS |
| L5 | CSV: заголовок ровно из шести полей в любом порядке, ровно 6 ячеек, пустые записи, malformed и quoted cells (критерий приёмки), конечный перевод строки, CR (A4), канонический порядок ключей (A12) | свои `loading.CsvDocumentTests.*` | 04 | PASS |
| L6 | Лимит рядов проверяется после полного разбора | свои `loading.LimitTests.test_row_count_limit_is_inclusive`, `loading.ErrorPrecedenceTests.test_syntax_is_checked_before_row_count` | 04 | PASS |
| L7 | `csv.field_size_limit` поднимается и восстанавливается, в том числе после ошибки | свои `loading.CsvFieldSizeLimitTests.*` | 04 | PASS |
| L8 | Исключения не содержат фрагментов входа | свой `loading.ErrorHygieneTests.test_errors_do_not_carry_input` | 04 | PASS |
| L9 | JSON и CSV эквивалентны | свой `properties.RandomizedInvariantTests.test_json_and_csv_inputs_are_equivalent`; публичный `test_json_csv_equivalence_and_bom` | 03, 04 | PASS |
| L10 | **R2, замечание 1 (принято).** JSON number любой длины проходит `load_rows` с точным значением и отклоняется анализатором как ряд (`INVALID_ROW_SCHEMA`) или поле. Результат одинаков при `sys.set_int_max_str_digits` 4300, 640 и 0; настройка процесса не меняется даже временно (решение A6) | свои `loading.IntegerDigitLimitTests.test_review_reproduction_is_a_rejected_row_under_every_limit`, `…test_long_integers_keep_their_exact_value_at_any_depth`, `…test_long_integer_field_value_reaches_its_field_rule`, `…test_the_process_wide_setting_is_never_changed`; `environment.EnvironmentTests.*` | 04, 13, 18, 19, 20, 21 | PASS |

## §6 `render_html`

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| H1 | Полный документ: doctype, html, head, meta charset, body | свой `html.HtmlTests.test_document_skeleton` | 04 | PASS |
| H2 | Виден весь результат (scope, summary, все ряды и поля, коды, `duplicate_of_row`); поля не скрыты и не сокращены | свои `html.HtmlTests.test_every_row_and_value_is_shown_in_full`, `…test_scope_and_summary_are_visible`, `…test_internal_whitespace_is_kept_for_display`; визуальная проверка R1 (`TASK_REPORT.md` §5) | 04 | PASS |
| H3 | Для REJECTED показывается причина без исходного входа | свой `html.HtmlTests.test_rejected_rows_show_reasons_but_never_raw_input` | 04 | PASS |
| H4 | Пустой набор показан явно | свой `html.HtmlTests.test_empty_report_is_explicit` | 04 | PASS |
| H5 | Всё экранируется через `html.escape(str(v), quote=True)`, в том числе в переданном вручную отчёте (A15) | свои `html.HtmlTests.test_text_is_escaped_with_html_escape_quote_true`, `…test_values_from_a_crafted_report_are_escaped`; публичный `test_html_escapes_visible_data` | 03, 04 | PASS |
| H6 | Нет ссылок и атрибутов из данных, script/iframe/form, JS и внешних ресурсов | свои `html.HtmlTests.test_only_allowlisted_tags_and_static_attributes` (белый список тегов, атрибутов и значений), `…test_template_contains_no_active_content_or_resource_references` | 04 | PASS |
| H7 | Детерминированный HTML | свой `html.HtmlTests.test_rendering_is_deterministic_and_does_not_mutate_the_report`; публичный `test_html_escapes_visible_data` | 03, 04 | PASS |

## §7 CLI

| ID | Требование | Тесты | Журнал | Статус |
|---|---|---|---|---|
| C1 | Все пять параметров обязательны; ошибки argparse дают exit 2; сокращения опций не принимаются | свои `cli.ArgumentTests.*` | 04 | PASS |
| C2 | Успех: ровно `report.json` и `report.html`; формат JSON побайтно; stdout `REPORT_CREATED\n`; stderr пуст; exit 0 | свои `cli.SuccessTests.test_json_and_csv_produce_the_same_report_files`, `cli.InProcessTests.test_successful_run`; публичный `test_cli_json_csv_and_no_overwrite` | 03, 04, 05, 07, 08 | PASS |
| C3 | Существующий out-dir любого вида → `OUTPUT_EXISTS`, ничего не меняется | свои `cli.OutputExistsTests.*` | 04, 06 | PASS |
| C4 | symlink не разыменовывается (критерий приёмки): на каталог, висячий, поставленный на место каталога после `mkdir`; **R2:** в том числе при `/` и `//` в конце `--out-dir` (ядро иначе разыменовывает последний symlink); цель symlink `0o700` того же владельца, чтобы проверку режима не заслонила проверка режима | свои `cli.OutputExistsTests.test_symlink_to_a_directory_is_not_followed`, `…test_dangling_symlink_is_not_followed`, `cli.DirectorySwapTests.test_symlink_swapped_in_after_mkdir_is_not_followed` | 04, 13, 18 | PASS |
| C5 | Проблемы чтения и родителя → `IO_ERROR` (ошибки ФС — критерий приёмки) | свои `cli.IoErrorTests.*` | 04, 13 | PASS |
| C6 | Ошибка входа приоритетнее существующего out-dir; при ошибке каталог не создаётся | свои `cli.InputErrorTests.*`; публичный `test_cli_bad_input_creates_no_output_or_input_leak` | 03, 04, 09 | PASS |
| C7 | Чтение ограничено `limit + 1` байтами | свой `cli.IoErrorTests.test_endless_input_is_read_only_up_to_the_limit` (`/dev/zero`) | 04, 09 | PASS |
| C8 | Сбой записи после `mkdir` → `IO_ERROR` без заявления успеха; гонка на `mkdir` → `OUTPUT_EXISTS` | свои `cli.InProcessTests.test_write_failure_after_mkdir_is_an_io_error`, `…test_losing_the_mkdir_race_is_output_exists` | 04 | PASS |
| C9 | `KeyboardInterrupt` не превращается в успех | свой `cli.InProcessTests.test_keyboard_interrupt_is_not_swallowed` | 04 | PASS |
| C10 | Вход не изменяется; пользовательские значения не выводятся (A9) | свои `cli.SuccessTests.test_input_file_is_not_modified_and_nothing_else_is_created`, `cli.InputErrorTests.test_invalid_scope_and_format_values_are_not_echoed` | 04 | PASS |
| C11 | Пути с пробелами и Unicode; CSV, экспортированный табличным редактором (BOM, CRLF, заголовок в кавычках); **R2:** `--out-dir` с `/` в конце | свои `cli.SuccessTests.test_unicode_and_spaces_in_paths`, `…test_bom_crlf_quoted_header_spreadsheet_export`, `…test_out_dir_with_trailing_slashes` | 04 | PASS |
| C12 | Пустой `--out-dir` (A13) | свой `cli.IoErrorTests.test_empty_out_dir_argument` | 04 | PASS |
| C13 | **R5, замечание 2 (сценарий проверки).** После создания out-dir родитель переименован и подменён заранее подготовленным `spare` с пустым `out`: отчёты в подставленный каталог не пишутся, успех не заявляется (`IO_ERROR`); отчёты лежат в созданном этим запуском каталоге внутри закреплённого родителя (A16) | свой `cli.DirectorySwapTests.test_parent_renamed_and_substituted_after_pin_is_not_reported_as_created` | 04, 13, 17 (на R4 — FAIL), 18 | PASS |
| C14 | **R2, замечание 2.** Успех — только если после записи out-dir указывает на созданный каталог; каталог, переименованный после открытия, даёт `IO_ERROR`, а новый каталог по тому же пути пуст (A16) | свой `cli.DirectorySwapTests.test_directory_replaced_after_it_was_opened_is_not_reported_as_created` | 04, 13, 18 | PASS |
| C15 | **R5, замечание 2. Остаточный случай того же пользователя, не гарантия.** Реальный перенос заранее созданного пустого каталога `0o700` того же владельца в окне, в доверенном родителе: `REPORT_CREATED`. Так может только тот же пользователь или root — вне модели угроз. Проверки свойств тождество не доказывают; ничего не перезаписано, в out-dir ровно два отчёта (A16) | свой `cli.DirectorySwapTests.test_same_user_identical_substitute_in_trusted_parent_is_the_only_residual` | 04, 13, 18 | PASS |
| C16 | **R5, замечание 2 (основная защита).** Родитель закрепляется дескриптором и проверяется **до создания** out-dir. Недоверенный родитель (доступен на запись группе/прочим без sticky bit) отвергается `IO_ERROR` **до создания**; out-dir не создаётся. Так исключается подмена другим пользователем | свой `cli.ParentTrustTests.test_untrusted_writable_parent_fails_before_creating_out_dir` | 04, 13, 17 (на R4 — FAIL), 18 | PASS |
| C17 | **R4, замечание 2.** Доверенный родитель (только для владельца либо world-writable со sticky bit как `/tmp`) допускает запись: `REPORT_CREATED`. Защита в глубину: каталог, открытый группе/прочим, перенесённый в окне, отвергается `IO_ERROR` | свои `cli.ParentTrustTests.test_owner_only_parent_is_trusted`, `…test_sticky_world_writable_parent_is_trusted`, `cli.DirectorySwapTests.test_group_or_world_accessible_directory_swapped_in_is_refused` | 04, 13, 18 | PASS |
| C18 | **R3.** Успешный запуск создаёт out-dir с режимом `0700`, принадлежащий текущему пользователю (отчёты содержат контактные данные; A14, A16) | свой `cli.ParentTrustTests` (прямое наблюдение режима), журнал 22 | 22 | PASS |

## §8 Независимость и возврат

| ID | Требование | Тесты и проверки | Журнал | Статус |
|---|---|---|---|---|
| I1 | API не открывает файлы и не использует сеть | свой `isolation.IsolationTests.test_api_performs_no_file_or_network_io`; весь Linux-прогон шёл без сети | 01, 04 | PASS |
| I2 | Нет импортов вне stdlib и собственного пакета, нет пространств FIRST | свой `isolation.IsolationTests.test_package_imports_only_the_standard_library` | 04 | PASS |
| P1 | Неизменяемые файлы пакета байт-в-байт | `CHECK_PACKAGE.py` | 02 | PASS |
| P2 | Качество кода | `ruff check`, `ruff format --check`, `mypy --strict` | 10, 11, 12 | PASS |
| P3 | Свои тесты действительно ловят дефекты | мутационная проверка: 25 внесённых дефектов в 6 модулях, обнаружены все (Linux-контейнер). В R5 мутации CLI обновлены под новый порядок: удаление проверки доверенности родителя, «родитель всегда доверенный», удаление финальных проверок out-dir и пути родителя, снятие хвостового `/`; проверка владельца как защита в глубину из мутаций исключена (в одном пользователе не проверяется) | 15 | PASS |
| P4 | Нагрузка 10 000 рядов без квадратичной деградации | свой `properties.RandomizedInvariantTests.test_maximum_row_count_is_processed_quickly` (граница 30 с) | 04, 13 | PASS |
| P5 | **R5.** Регрессионные тесты замечания 2 ловят дефект R4: сценарий подмены родителя (`DirectorySwapTests.test_parent_renamed_and_substituted_after_pin...`) и требование доверенного родителя на коде возврата R4 падают, на R5 проходят. Код R4 сверен с его `RETURN_MANIFEST.json`, 11/11 файлов | `IntegerDigitLimitTests`, `EnvironmentTests`, `ParentTrustTests`, `DirectorySwapTests`, `test_out_dir_with_trailing_slashes` | 17 (FAILED), 18 (OK) | PASS |

## Не проверено

| Условие | Статус | Комментарий |
|---|---|---|
| Windows | NOT_RUN | Запусков на Windows не было. В `cli.py` для платформ без `dir_fd` есть запасная ветка (`O_EXCL` по полному пути, без проверок A16); ни один прогон её не исполнял |
| Другие патч-версии CPython 3.12 и версии Unicode | NOT_RUN | Проверено только CPython 3.12.13 (`unicodedata` 15.0.0). Граница вложенности JSON (A7) зависит от сборки |
| Настоящая гонка ФС: каталог подменяет другой процесс | NOT_RUN | Подмена моделируется внутри процесса реальными ФС-операциями (`os.rename`, `chmod`) ровно в окне: symlink, каталог с доступом группе/прочим, непустой и пустой каталог `0o700` того же владельца, переименование после открытия, переименование и подмена родителя после закрепления; плюс недоверенный/доверенный родитель. Отдельно моделируются `FileExistsError` от `mkdir` и `OSError` при записи. Реальный параллельный процесс не запускался |
| Непосредственный родитель принадлежит другому пользователю; вышележащие каталоги | NOT_RUN | Проверяется доверенность непосредственного родителя (владелец + права). Полный покомпонентный обход вышележащих каталогов без следования symlink не реализован (возможен в stdlib, но объёмен) — вышележащие предполагаются доверенными. См. `docs/R5_REWORK.md`, раздел 4 |
| Отображающие владельца ФС (NFS `all_squash`/`root_squash`, часть sshfs/SMB/vfat) | NOT_RUN | Проверка доверенности родителя сравнивает владельца с `euid`. На таких монтированиях владелец может не совпасть, и штатный запуск вернёт `IO_ERROR`. Проверено на APFS (macOS), tmpfs и ext4 в контейнере, bind-mount `fakeowner` Docker (журнал 22); перечисленные сетевые ФС не проверялись. Цена — `docs/R5_REWORK.md`, раздел 4 |
| Настоящий сбой диска (ENOSPC, EIO) | NOT_RUN | Смоделирован через `OSError(28)` при создании второго файла |
| Права доступа под root | NOT_RUN | Тесты прав пропускаются при uid 0. Оба прогона шли не от root, поэтому эти тесты выполнились |
| Одновременное использование `csv.field_size_limit` чужим кодом в другом потоке | NOT_RUN | Параллельные вызовы самого `load_rows` упорядочены замком; влияние на чужой код в других потоках не проверялось (см. `LIMITATIONS.md`) |
| Стоимость длинного целого на другом оборудовании | NOT_RUN | Худший случай (один литерал на 10 MiB) измерен только в Linux-контейнере на Apple M4 Pro: 12,4–12,6 с (журнал 21) |
| Светлая тема и печать HTML | NOT_RUN | В R1 визуально проверена только тёмная тема в Chrome на macOS; стили для светлой темы и печати проверены только как CSS. Шаблон HTML в R2 не менялся, отчёты побайтно совпадают с R1 |

## Не гарантируется

| Свойство | Почему | Где описано |
|---|---|---|
| Тождество открытого каталога созданному `mkdir` | POSIX и stdlib не дают его доказать (нет атомарного создания-с-дескриптором, нет `renameat2(RENAME_NOREPLACE)`/`O_TMPFILE` для каталогов). Поэтому защита от другого пользователя строится на доверенности родителя, а не на свойствах каталога | `docs/R5_REWORK.md` 1–2; `LIMITATIONS.md` A16 |
| Отчёты попадают именно в каталог, созданный `mkdir`, если **тот же пользователь** (или root) подменил его в доверенном родителе | В доверенном родителе переименовать запись может только тот же пользователь или root — вне модели угроз: такой процесс и так читает/меняет отчёты напрямую. Зафиксировано тестом C15 | `docs/R5_REWORK.md` 4 |
| Закрытость при недоверенном родителе без отказа | Реализация выбирает безопасность по умолчанию: при недоверенном родителе — `IO_ERROR` до записи, не запись в возможно подставленный каталог. Это предлагаемое условие эксплуатации, **на согласовании**; до согласования замечание не считается закрытым | `docs/R5_REWORK.md` 4 |
