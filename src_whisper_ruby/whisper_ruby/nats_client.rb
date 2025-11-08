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
    ack = @nats.publish subj, message.to_json
    LOGGER.info "PUBLISHED ack: #{ack}"
  end

  def loop_sub( subject, params = {})
    pull_subscription = @nats.pull_subscribe subject

    loop do
      msgs = pull_subscription.fetch 1 #, timeout: 1
      msgs.each do |msg|
        # meta = msg.metadata
        msg.in_progress
        yield msg
        msg.ack_sync # :ack, :ack_sync, :nak, :term
      end
    end
  ensure
    pull_subscription.unsubscribe
  end

end