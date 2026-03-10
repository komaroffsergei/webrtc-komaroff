# frozen_string_literal: true

RSpec.describe SrcLanggraphRb::Scenarios::BuiltInCatalog do
  it "registers the default declarative scenarios" do
    catalog = described_class.build

    expect(catalog.all.map(&:id)).to eq(
      [
        "find_nearest_airport@2.0.0",
        "free_speech@2.0.0",
        "where_my_flight@2.0.0"
      ]
    )
  end
end
