# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Router
      module_function

      CFG = Runtime::ConfigLoader.load_config("router")
      ROUTER_TASK = Runtime::ConfigLoader.text_block(
        CFG[:task],
        "Определи, какой сценарий лучше всего подходит для запроса пользователя. Выбирай только один сценарий из списка."
      )
      ROUTER_SCENARIOS = Runtime::ConfigLoader.list_of_dicts(
        CFG[:available_scenarios],
        [
          {
            id: Runtime::ScenarioIds::WHERE_MY_FLIGHT,
            description: "Найти статус рейса по номеру рейса или фамилии пассажира"
          },
          {
            id: Runtime::ScenarioIds::FIND_NEAREST_AIRPORT,
            description: "Найти ближайший аэропорт и построить маршрут до него"
          },
          {
            id: Runtime::ScenarioIds::FREE_SPEECH,
            description: "Свободный разговор: общение с пользователем без инструментов"
          }
        ]
      )

      def choose_scenario(req, io, dialog_context:, excluded_scenarios: nil, context_artifacts: nil)
        scenarios = filtered_scenarios(excluded_scenarios)
        allowed_ids = scenarios.map { |item| item[:id].to_s.strip }.to_set
        return [Runtime::ScenarioIds::FREE_SPEECH, { reason: "No scenarios available after exclusions" }] if scenarios.empty?

        llm_input = {
          task: ROUTER_TASK,
          text: req[:text],
          available_scenarios: scenarios,
          dialog_context: dialog_context
        }
        llm_input[:context_artifacts] = Runtime::Util.extract_hash(context_artifacts) if context_artifacts.is_a?(Hash) && !context_artifacts.empty?

        llm_resp = io.call_llm(parent: req, mode: "routing_decision", input_data: llm_input, constraints: { temperature: 0 })
        return [Runtime::ScenarioIds::FREE_SPEECH, {}] unless llm_resp[:ok] && llm_resp[:data].is_a?(Hash)

        data = Runtime::Util.extract_hash(llm_resp[:data])
        candidate = data[:workflow_id].to_s.strip
        return [candidate, data] if allowed_ids.include?(candidate)

        [Runtime::ScenarioIds::FREE_SPEECH, data]
      end

      def filtered_scenarios(excluded_scenarios)
        excluded = Array(excluded_scenarios).map(&:to_s).reject(&:empty?).to_set
        ROUTER_SCENARIOS.filter_map do |row|
          item = Runtime::Util.extract_hash(row)
          scenario_id = item[:id].to_s.strip
          next if scenario_id.empty? || excluded.include?(scenario_id)

          { id: scenario_id, description: item[:description].to_s.strip }
        end
      end
      private_class_method :filtered_scenarios
    end
  end
end
