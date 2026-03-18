# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Router
      module_function

      ROUTER_TASK = "Определи, какой сценарий лучше всего подходит для запроса пользователя.\n" \
                    "Выбирай только один сценарий из списка.\n" \
                    "Если не подходит ни один инструментальный сценарий, выбери free_speech@2.0.0."

      def choose_scenario(req, io, catalog:, dialog_context:, excluded_scenarios: nil, context_artifacts: nil)
        scenarios = filtered_scenarios(catalog, excluded_scenarios)
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

      def filtered_scenarios(catalog, excluded_scenarios)
        excluded = Array(excluded_scenarios).map(&:to_s).reject(&:empty?).to_set
        catalog.all.filter_map do |scenario|
          scenario_id = scenario.id.to_s.strip
          next if scenario_id.empty? || excluded.include?(scenario_id)

          metadata = scenario.metadata
          description = metadata.routing_description.to_s.strip
          description = metadata.description.to_s.strip if description.empty?
          next if description.empty?

          { id: scenario_id, description: description }
        end
      end
      private_class_method :filtered_scenarios
    end
  end
end
