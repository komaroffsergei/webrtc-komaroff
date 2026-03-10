# frozen_string_literal: true

RSpec.describe "validation rules" do
  it "rejects inline routers to keep the DSL declarative" do
    expect do
      SrcLanggraphRb.build_catalog do
        scenario "invalid_router@1.0.0" do
          graph do
            entry_point :start
            node :start, kind: :router
            node :done, kind: :final_response
            conditional_edge :start, ->(_state) { :done }, { "done" => :done }
            finish_point :done
          end
        end
      end
    end.to raise_error(SrcLanggraphRb::ValidationError, /Inline router callables/)
  end

  it "rejects duplicate scenario ids" do
    expect do
      SrcLanggraphRb.build_catalog do
        scenario "demo@1.0.0" do
          graph do
            entry_point :start
            node :start, kind: :local
            finish_point :start
          end
        end

        scenario "demo@1.0.0" do
          graph do
            entry_point :start
            node :start, kind: :local
            finish_point :start
          end
        end
      end
    end.to raise_error(SrcLanggraphRb::RegistryError, /already registered/)
  end

  it "rejects graphs without entry points" do
    expect do
      SrcLanggraphRb.build_catalog do
        scenario "missing_entry@1.0.0" do
          graph do
            node :start, kind: :local
            finish_point :start
          end
        end
      end
    end.to raise_error(SrcLanggraphRb::ValidationError, /entry point/)
  end
end
