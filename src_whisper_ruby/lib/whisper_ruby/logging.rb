# frozen_string_literal: true

require "logger"

module WhisperRuby
  module LogTag
    TAG = "[src_whisper_ruby]"

    module_function

    def apply(message)
      str = message.to_s
      str.start_with?(TAG) ? str : "#{TAG} #{str}"
    end
  end

  class TaggedLogger < Logger
    def initialize(logdev = $stdout, shift_age = 0, shift_size = 1_048_576, tag: LogTag::TAG)
      super(logdev, shift_age, shift_size)
      @tag = tag
    end

    def add(severity, message = nil, progname = nil)
      if message.nil?
        if block_given?
          message = yield
        else
          message = progname
          progname = nil
        end
      end

      message = tag_message(message) if message
      super(severity, message, progname)
    end

    private

    def tag_message(message)
      str = message.to_s
      str.start_with?(@tag) ? str : "#{@tag} #{str}"
    end
  end
end
