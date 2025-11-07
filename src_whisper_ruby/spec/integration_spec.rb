require "json"

RSpec.describe "Integration Tests" do
  describe "Service basics" do
    it "responds to healthcheck" do
      get "/healthcheck"
      expect(last_response.status).to eq(200)
      body = JSON.parse(last_response.body)
      expect(body.fetch("status")).to eq("ok")
    end
  end
end
