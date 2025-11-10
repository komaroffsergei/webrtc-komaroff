require 'nats'
require 'json'

ENV['NATS_RECONNECT'] = 'true'
# ENV['NATS_VERBOSE'] = 'true'
ENV['NATS_RECONNECT_TIME_WAIT'] = '2'
ENV['NATS_MAX_RECONNECT_ATTEMPTS'] = '-1'

class NATSClient

  def req( request, params = {} )
    JSON @nats.request(request, params.to_json).data, symbolize_names: true
  end

  def initialize(url, options={})
    nc = NATS::Client.new
    nc.on_close &->{ LOGGER.info "NATS Client closed", _1 }
    nc.on_error &->{ LOGGER.error "NATS Client failed", _1 }
    nc.on_disconnect &->{ LOGGER.info "NATS Client disconnected", _1 }
    nc.on_reconnect &->{ LOGGER.info "NATS Client reconnected", _1 }

    @nats = nc.connect url, options
  end

  def publish(subj, message)
    payload = message.is_a?(String) ? message : message.to_json
    @nats.publish subj, payload
  end

  def loop_sub(subject)
    @nats.subscribe(subject) do |msg|
      yield msg
    end
  end


end
  def connected?
    @nats&.connected?
  end

  def connected_server
    @nats&.uri
  end

  def uri
    @nats&.uri
  end
