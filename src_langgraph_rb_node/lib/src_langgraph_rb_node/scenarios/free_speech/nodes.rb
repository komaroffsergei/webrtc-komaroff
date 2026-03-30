# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      # Ноды сценария свободного разговора.
      # Этот сценарий не вызывает внешние инструменты и строится вокруг двух задач:
      # 1. Понять, к какой сущности из контекста относится пользовательская референция.
      # 2. Сформировать хороший ответ от LLM, а если первый проход слабый,
      #    запустить повторный проход с усиленной инструкцией на использование общих знаний.
      class Nodes < BaseNodes
        # Регулярное выражение для ссылок в единственном числе.
        # Нужен, чтобы распознавать запросы вида "когда он построен?" или "что это?".
        SINGULAR_REF_RE = /\b(он|она|оно|его|ее|её|нему|ней|нем|этот|эта|это|данный|данная)\b/i

        # Регулярное выражение для ссылок во множественном числе.
        # Нужен для запросов вроде "они", "эти", "их".
        PLURAL_REF_RE = /\b(они|их|ими|эти|этих|этим)\b/i

        # Эвристика для распознавания "фактологических" вопросов,
        # где ответ должен содержать знания о датах, истории, авторстве и т.д.
        FACT_QUERY_RE = /\b(когда|в каком году|какого года|какой год|какие годы|кем|кто|где|почему|что известно|история|год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?|основан(?:а|о|ы)?|основание|построен(?:а|о|ы)?|постройк(?:а|и)|строительств(?:о|а)|открыт(?:а|о|ы)?|создан(?:а|о|ы)?)\b/i

        # Более узкая эвристика для вопросов именно про год/дату.
        YEAR_QUERY_RE = /\b(в каком году|какого года|какой год|какие годы|год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?)\b/i

        # Эвристика для проверки, содержит ли текст конкретное четырехзначное значение года.
        YEAR_VALUE_RE = /\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b/

        # Фразы-маркеры, по которым можно понять, что модель ответила
        # слишком "контекстно-ограниченно" и не использовала общие знания,
        # хотя для свободного диалога это желательно.
        CONTEXT_ONLY_REFUSAL_HINTS = [
          "в текущих данных нет",
          "в текущем контексте нет",
          "в контексте нет этой информации",
          "в контексте нет данных",
          "в диалоге нет этой информации",
          "в текущем диалоге нет",
          "нет подтвержденной информации",
          "не могу указать",
          "к сожалению, я не уверен",
          "я не уверен, кто",
          "могу помочь с тем, что известно в текущем диалоге",
          "данных о годе"
        ].freeze

        # Базовая инструкция для первичного LLM-прохода.
        # Она задает стиль ответа, работу с референциями
        # и разрешает модели использовать не только контекст, но и общие знания.
        TASK = "Побеседуй с пользователем в свободной форме.\n" \
               "Отвечай кратко, по-русски, дружелюбно и по делу.\n" \
               "Если вопрос непонятен, задай уточняющий вопрос.\n" \
               "Используй context_artifacts и dialog_context для референций вроде 'он/этот' и 'они/эти'.\n" \
               "При resolved_reference_mode=single не задавай повторный вопрос о том, что имелось в виду.\n" \
               "При resolved_reference_mode=multi и запросе во множественном числе отвечай по каждой сущности из resolved_entities.\n" \
               "Используй не только контекст диалога, но и общие знания модели.\n" \
               "Если в знании не уверен, явно укажи неопределенность."

        # Сценарный контекст для LLM.
        SCENARIO_CONTEXT = "Свободный диалог без сценария.\n" \
                           "Инструменты не используются.\n" \
                           "Цель — помочь пользователю и поддерживать разговор."

        # Резервный текст, если модель не вернула никакого ответа.
        FALLBACK_MESSAGE = "Сервис ответов временно недоступен. Попробуйте повторить запрос."

        # Усиливающий суффикс для второго прохода LLM.
        # Он нужен, когда первый ответ получился слишком осторожным
        # или не использовал фактические знания модели.
        KNOWLEDGE_RETRY_TASK_SUFFIX = "Если вопрос пользователя требует фактов, не ограничивайся только полями из context_artifacts.\n" \
                                      "Используй общие знания модели вместе с контекстом диалога.\n" \
                                      "Считай context_artifacts подсказками, а не ограничением знаний.\n" \
                                      "Для вопросов про даты/историю/авторство используй знания модели, даже если в context_artifacts нет этих данных.\n" \
                                      "Не отвечай шаблоном о нехватке данных, если факт можно дать из общих знаний.\n" \
                                      "Если уверенность низкая, прямо укажи это в ответе."

        # Подготавливает контекст для дальнейшей генерации ответа.
        # На этом шаге мы не спрашиваем LLM, а только разбираем локальные артефакты
        # и пытаемся понять, к каким сущностям может относиться запрос пользователя.
        def prepare_context(state)
          # Из дополнительных артефактов извлекаем список потенциальных сущностей,
          # на которые пользователь может ссылаться местоимениями.
          entities = extract_entities_from_artifacts(Runtime::Util.extract_hash(state[:context_extra]))

          # Разрешаем референцию пользователя:
          # single  -> речь об одной сущности,
          # multi   -> речь о нескольких,
          # clarify -> нужно уточнение,
          # none    -> явной референции нет.
          resolved_mode, resolved_entities, resolved_hint = resolve_entity_reference(
            state.dig(:req, :text).to_s,
            entities,
            dialog_context: state[:dialog_context].to_s
          )

          # Собираем общие поля состояния для следующих нод.
          out = {
            resolved_mode: resolved_mode,
            resolved_entities: resolved_entities,
            resolved_hint: resolved_hint,
            prepare_status: resolved_mode == "clarify" ? "clarify" : "continue"
          }

          # Если нужна явная развилка через уточняющий вопрос, формируем текст уточнения.
          out[:clarify_message] = clarify_entity_message(resolved_entities) if resolved_mode == "clarify"
          out
        end

        # Routing после анализа контекста.
        def route_after_prepare(state)
          if state[:prepare_status] == "clarify"
            AsyncGraph::Command.goto(:clarify_reference)
          else
            AsyncGraph::Command.goto(:compose_response)
          end
        end

        # Возвращает пользователю уточняющий вопрос, если референция неоднозначна.
        def clarify_reference(state)
          { response: done_response(state.fetch(:req), state[:clarify_message]) }
        end

        # Основная нода генерации ответа.
        # Здесь используется двухпроходная стратегия:
        # 1. Первый LLM-ответ в штатном режиме.
        # 2. Если ответ слабый или слишком "контекстно-ограниченный",
        #    запускается knowledge retry с усиленной инструкцией.
        def compose_response(state, await)
          # Исходный req нужен в первую очередь для текста пользователя.
          req = state.fetch(:req)

          # Собираем единый input для первого прохода модели.
          primary_input = {
            task: TASK,
            user_message: req[:text],
            tool_results: [],
            scenario_context: SCENARIO_CONTEXT,
            dialog_context: state[:dialog_context].to_s,
            context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts]),
            resolved_reference_mode: %w[single multi].include?(state[:resolved_mode]) ? state[:resolved_mode] : "none",
            resolved_entities: Array(state[:resolved_entities]).first(5),
            resolved_hint: state[:resolved_hint].to_s,
            free_speech_pass: "primary"
          }

          # Сценарий только описывает запрос к модели.
          # AsyncGraph/runtime фактически выполняет LLM-вызов и вернет ответ обратно в ноду.
          primary_resp = await.call(
            "free_speech_primary",
            :llm,
            mode: "final_response",
            input_data: primary_input,
            constraints: { temperature: 0.4 }
          )

          # Извлекаем текст первого ответа.
          primary_text = extract_llm_text(primary_resp)
          # Если текст пустой, сразу отдаём безопасный fallback.
          return { response_message: FALLBACK_MESSAGE } if primary_text.empty?

          # Если признаков проблем нет, второй проход не нужен.
          unless needs_knowledge_retry(
            user_text: req[:text].to_s,
            response_text: primary_text,
            resolved_mode: state[:resolved_mode].to_s,
            resolved_entities: Array(state[:resolved_entities])
          )
            return { response_message: primary_text }
          end

          # Для второго прохода:
          # - усиливаем task,
          # - сжимаем dialog_context,
          # - при необходимости фокусируем context_artifacts на resolved_entities,
          # - передаем причину retry для прозрачности.
          secondary_resp = await.call(
            "free_speech_retry",
            :llm,
            mode: "final_response",
            input_data: primary_input.merge(
              task: [TASK, KNOWLEDGE_RETRY_TASK_SUFFIX].join("\n"),
              dialog_context: short_dialog_context(state[:dialog_context].to_s),
              context_artifacts: retry_context_artifacts(
                context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts]),
                resolved_entities: Array(state[:resolved_entities])
              ),
              free_speech_pass: "knowledge_retry",
              retry_reason: retry_reason(
                user_text: req[:text].to_s,
                response_text: primary_text,
                resolved_mode: state[:resolved_mode].to_s,
                resolved_entities: Array(state[:resolved_entities])
              )
            ),
            constraints: { temperature: 0.3 }
          )

          # Извлекаем текст второго ответа.
          secondary_text = extract_llm_text(secondary_resp)

          # Оцениваем качество обоих ответов по простой эвристике.
          primary_score = response_quality_score(
            user_text: req[:text].to_s,
            response_text: primary_text,
            resolved_mode: state[:resolved_mode].to_s,
            resolved_entities: Array(state[:resolved_entities])
          )
          secondary_score = response_quality_score(
            user_text: req[:text].to_s,
            response_text: secondary_text,
            resolved_mode: state[:resolved_mode].to_s,
            resolved_entities: Array(state[:resolved_entities])
          )

          # По умолчанию побеждает ответ с большим score.
          best_text = secondary_score >= primary_score ? secondary_text : primary_text
          # Если победивший ответ пустой, откатываемся к первому.
          best_text = primary_text if best_text.to_s.empty?
          # Если и он пуст, возвращаем глобальный fallback.
          best_text = FALLBACK_MESSAGE if best_text.to_s.empty?
          { response_message: best_text }
        end

        # Заворачивает уже выбранный текст в стандартный done-response.
        def emit_final_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        private

        # Возвращает красивую подпись сущности:
        # сначала пытается взять label/name/title,
        # затем дополняет кодом/id/key, если он есть.
        def entity_label(entity, fallback: "объект")
          # Нормализуем payload сущности в hash.
          payload = Runtime::Util.extract_hash(entity)
          # Ищем наиболее подходящее человекочитаемое название сущности.
          title = [payload[:label], payload[:name], payload[:title]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
          # Ищем машинный/короткий идентификатор сущности.
          code = [payload[:code], payload[:id], payload[:key]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
          # Если есть и название, и код, объединяем их.
          return "#{title} (#{code})" unless title.empty? || code.empty?
          # Если есть только название, возвращаем его.
          return title unless title.empty?
          # Если есть только код, возвращаем его.
          return code unless code.empty?

          # Если в сущности нет понятных полей, используем fallback-ярлык.
          fallback
        end

        # Разбивает label сущности на токены для более гибкого поиска упоминаний в тексте.
        def tokenize_label(label)
          # Нормализуем вход.
          compact = label.to_s.strip
          # Для пустого label нет смысла строить токены.
          return [] if compact.empty?

          # Делим строку по пробелам, скобкам и знакам препинания.
          compact.split(/[()\s,.;:]+/).reject(&:empty?)
        end

        # Проверяет, похож ли payload на сущность, пригодную для референций.
        def looks_like_entity(payload)
          # Нормализуем payload.
          data = Runtime::Util.extract_hash(payload)
          %i[label name title code id key].any? do |key|
            value = data[key]
            # Для id/code/key допускаем любое непустое скалярное значение.
            next !value.nil? && !value.is_a?(Hash) && !value.is_a?(Array) if %i[id code key].include?(key)

            # Для label/name/title нужен непустой string.
            value.is_a?(String) && !value.strip.empty?
          end
        end

        # Извлекает список сущностей из context_extra.artifact_memory.
        # На выходе каждая сущность имеет:
        # - label  -> человекочитаемый ярлык,
        # - source -> откуда она взялась,
        # - raw    -> исходный hash для последующего использования.
        def extract_entities_from_artifacts(context_extra)
          # Берем memory-артефакт, в котором могут лежать коллекции сущностей.
          artifact = Runtime::Util.extract_hash(context_extra[:artifact_memory])
          # Если артефактов нет, сразу возвращаем пустой список.
          return [] if artifact.empty?

          # Здесь будем накапливать кандидатов в сущности.
          entities = []
          artifact.each do |key, value|
            if value.is_a?(Array)
              # Для массивов берем только первые элементы, чтобы не раздувать контекст.
              value.first(10).each_with_index do |item, idx|
                # Пропускаем все, что не похоже на сущность.
                next unless item.is_a?(Hash) && looks_like_entity(item)

                # Для каждого валидного элемента строим компактное описание сущности.
                entities << { label: entity_label(item, fallback: "#{key}[#{idx + 1}]"), source: key.to_s, raw: Runtime::Util.extract_hash(item) }
              end
            elsif value.is_a?(Hash) && looks_like_entity(value)
              # Если значение само по себе является сущностью, добавляем его как одиночный объект.
              entities << { label: entity_label(value, fallback: key.to_s), source: key.to_s, raw: Runtime::Util.extract_hash(value) }
            end
          end

          # Удаляем дубликаты по label в case-insensitive виде.
          seen = {}
          entities.each_with_object([]) do |row, out|
            label = row[:label].to_s.strip
            next if label.empty?

            lower = label.downcase
            next if seen[lower]

            seen[lower] = true
            out << row
          end
        end

        # Находит сущности, которые пользователь явно упомянул в тексте,
        # а не только косвенно через местоимение.
        def explicit_entity_mentions(text, entities)
          # Оригинальный текст нужен для regex-проверок.
          clean = text.to_s
          # lower нужен для дешевого case-insensitive include?.
          lower = clean.downcase
          entities.select do |entity|
            label = entity[:label].to_s.strip
            next false if label.empty?
            # Прямое вхождение полного label.
            next true if lower.include?(label.downcase)

            # Либо совпадение по отдельным токенам label.
            tokenize_label(label).any? { |token| /\b#{Regexp.escape(token)}\b/i.match?(clean) }
          end
        end

        # Возвращает последнюю реплику ассистента из dialog_context.
        def last_assistant_turn(dialog_context)
          assistant_lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?).select { |line| line.start_with?("- Assistant:") }
          assistant_lines.last.to_s
        end

        # Пытается выбрать главную сущность по последней реплике ассистента.
        # Это полезно для кейсов, где пользователь пишет "а когда он был построен?".
        def pick_primary_by_recent_assistant(entities, dialog_context)
          # Берем последнюю реплику ассистента как источник "текущего фокуса" разговора.
          last = last_assistant_turn(dialog_context)
          return nil if last.empty?

          # Ищем сущности, явно встречающиеся в последнем ответе ассистента.
          matches = entities.select do |entity|
            label = entity[:label].to_s.strip
            next false if label.empty?
            next true if last.downcase.include?(label.downcase)

            tokenize_label(label).any? { |token| last.downcase.include?(token.downcase) }
          end
          # Если совпадение ровно одно, считаем его текущей главной сущностью.
          matches.length == 1 ? matches.first : nil
        end

        # Центральная функция разрешения референций.
        # Она пытается понять, что именно пользователь имеет в виду под местоимениями
        # или короткими ссылками на уже известные сущности.
        def resolve_entity_reference(text, entities, dialog_context:)
          # Сначала ищем явные упоминания сущностей в пользовательском тексте.
          mentions = explicit_entity_mentions(text, entities)
          if mentions.length == 1
            label = entity_label(mentions.first)
            return ["single", mentions, "Запрос относится к сущности #{label}."]
          end
          if mentions.length > 1
            labels = mentions.first(5).map { |item| entity_label(item) }.join(", ")
            return ["multi", mentions.first(5), "Запрос относится к нескольким сущностям: #{labels}."]
          end

          # Если явных упоминаний нет, анализируем местоимения.
          plural = PLURAL_REF_RE.match?(text.to_s)
          singular = SINGULAR_REF_RE.match?(text.to_s)

          # Для множественного числа считаем, что пользователь имеет в виду
          # все сущности из текущего контекста.
          if plural && !entities.empty?
            labels = entities.first(5).map { |item| entity_label(item) }.join(", ")
            return ["multi", entities.first(5), "Запрос относится к сущностям из контекста: #{labels}."]
          end

          if singular
            # Для единственного числа сначала пробуем угадать по последней реплике ассистента.
            primary = pick_primary_by_recent_assistant(entities, dialog_context)
            if primary
              label = entity_label(primary)
              return ["single", [primary], "Запрос относится к последней фокусной сущности: #{label}."]
            end
            # Если сущность в контексте всего одна, ambiguity нет.
            if entities.length == 1
              label = entity_label(entities.first)
              return ["single", entities.first(1), "В контексте только одна сущность: #{label}."]
            end
            # Если сущностей несколько, а местоимение в единственном числе,
            # безопаснее попросить пользователя уточнить, о ком именно речь.
            return ["clarify", entities.first(5), "Единственное число при нескольких сущностях требует уточнения."] if entities.length > 1
          end

          # Даже без явного местоимения, если в контексте только одна сущность,
          # можно аккуратно считать ее основной.
          if entities.length == 1
            label = entity_label(entities.first)
            return ["single", entities.first(1), "В контексте только одна сущность: #{label}."]
          end

          # Если никакой референции не найдено, идем дальше без специальных подсказок.
          ["none", [], ""]
        end

        # Формирует текст уточнения для неоднозначной референции.
        def clarify_entity_message(entities)
          # Если список пуст, задаем общий вопрос.
          return "Уточните, о каком объекте речь." if entities.empty?

          # Иначе перечисляем первые несколько возможных кандидатов.
          "Уточните, о каком объекте речь: #{entities.first(5).map { |item| entity_label(item) }.join(', ')}."
        end

        # Проверяет, выглядит ли запрос как фактологический вопрос.
        def fact_query?(text)
          clean = text.to_s.strip
          !clean.empty? && (FACT_QUERY_RE.match?(clean) || YEAR_QUERY_RE.match?(clean))
        end

        # Проверяет, является ли вопрос specifically запросом про год/дату.
        def year_query?(text)
          clean = text.to_s.strip
          !clean.empty? && YEAR_QUERY_RE.match?(clean)
        end

        # Проверяет, содержит ли ответ конкретное значение года.
        def contains_year?(text)
          YEAR_VALUE_RE.match?(text.to_s)
        end

        # Определяет, не ответила ли модель шаблоном "в контексте нет данных".
        def contains_context_only_refusal?(text)
          lower = text.to_s.downcase
          !lower.empty? && CONTEXT_ONLY_REFUSAL_HINTS.any? { |marker| lower.include?(marker) }
        end

        # Проверяет, упомянуты ли в ответе те сущности, которые ранее были разрешены.
        # Это полезно для оценки качества ответа при single/multi reference mode.
        def mentions_resolved_entities?(text, resolved_entities)
          # Если сущности не были разрешены, считать это условие выполненным.
          return true if resolved_entities.empty?

          clean = text.to_s
          # Пустой ответ точно не может упоминать сущности.
          return false if clean.empty?

          # Считаем число разрешенных сущностей, которые явно встретились в ответе.
          hits = resolved_entities.first(5).count do |entity|
            label = entity_label(entity).strip
            next false if label.empty?
            next true if clean.downcase.include?(label.downcase)

            tokenize_label(label).select { |token| token.length >= 3 }.any? { |token| /\b#{Regexp.escape(token)}\b/i.match?(clean) }
          end

          # Для single достаточно одного попадания.
          # Для multi требуем минимум два или все количество сущностей, если их меньше двух.
          resolved_entities.length <= 1 ? hits >= 1 : hits >= [2, resolved_entities.length].min
        end

        # Простая эвристика качества ответа.
        # Чем выше score, тем лучше ответ подходит под задачу.
        def response_quality_score(user_text:, response_text:, resolved_mode:, resolved_entities:)
          # Нормализуем текст ответа.
          text = response_text.to_s.strip
          # Пустой ответ получает минимальный score.
          return 0 if text.empty?

          # Базовый балл за непустой ответ.
          score = 1
          # Бонус, если модель не ушла в шаблон "в контексте нет данных".
          score += 2 unless contains_context_only_refusal?(text)
          # Бонус, если в ответе на вопрос про год действительно есть год.
          score += 2 if year_query?(user_text) && contains_year?(text)
          # Бонус, если при resolved reference mode ответ явно упоминает нужные сущности.
          score += 1 if %w[single multi].include?(resolved_mode) && mentions_resolved_entities?(text, resolved_entities)
          score
        end

        # Решает, нужен ли второй knowledge-aware проход LLM.
        def needs_knowledge_retry(user_text:, response_text:, resolved_mode:, resolved_entities:)
          # Нормализуем текст первого ответа.
          text = response_text.to_s.strip
          # Пустой ответ всегда требует retry.
          return true if text.empty?
          # Если ответ похож на "у меня нет данных в контексте", тоже retry.
          return true if contains_context_only_refusal?(text)
          # Если модель проигнорировала resolved entities, делаем retry.
          return true if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
          # Если вопрос про год, а ответа с годом нет, retry обязателен.
          return true if year_query?(user_text) && !contains_year?(text)
          # Для фактологических вопросов дополнительно проверяем score.
          return response_quality_score(user_text:, response_text: text, resolved_mode:, resolved_entities:) < 4 if fact_query?(user_text)

          # Иначе первого ответа достаточно.
          false
        end

        # Возвращает machine-readable причину запуска повторного прохода.
        def retry_reason(user_text:, response_text:, resolved_mode:, resolved_entities:)
          # Нормализуем текст ответа.
          text = response_text.to_s.strip
          # Причины проверяются в порядке от самых очевидных к более общим.
          return "empty_response" if text.empty?
          return "context_only_refusal" if contains_context_only_refusal?(text)
          return "missing_year_for_year_query" if year_query?(user_text) && !contains_year?(text)
          return "missing_resolved_entity_reference" if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
          return "low_quality_fact_answer" if fact_query?(user_text)

          # Если конкретная причина не определена, указываем общий secondary pass.
          "generic_secondary_pass"
        end

        # Сжимает dialog_context для второго LLM-прохода,
        # чтобы не отправлять слишком длинную историю целиком.
        def short_dialog_context(dialog_context, max_lines: 10, max_chars: 2400)
          # Разбиваем историю на строки, очищаем и убираем пустые.
          lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?)
          # Если истории нет, возвращаем пустую строку.
          return "" if lines.empty?

          # Берем только хвост истории, поскольку он наиболее релевантен.
          tail = lines.last(max_lines).join("\n")
          # Если хвост короткий, возвращаем его целиком; иначе обрезаем по символам.
          tail.length <= max_chars ? tail : tail[-max_chars..]
        end

        # Подготавливает context_artifacts для второго прохода.
        # Если resolved_entities известны, вместо полного контекста можно передать
        # только их raw-представления, чтобы усилить фокус ответа.
        def retry_context_artifacts(context_artifacts:, resolved_entities:)
          # Если сущности не были разрешены, оставляем исходный контекст без изменений.
          return context_artifacts if resolved_entities.empty?

          # Собираем raw-представления только для первых нескольких resolved entities.
          resolved_raw = resolved_entities.first(5).filter_map do |row|
            raw = Runtime::Util.extract_hash(row[:raw])
            raw unless raw.empty?
          end
          # Если собрать raw не удалось, оставляем исходный контекст.
          return context_artifacts if resolved_raw.empty?

          # Иначе передаем во второй проход только сфокусированный набор сущностей.
          { resolved_entities: resolved_raw }
        end
      end
    end
  end
end
