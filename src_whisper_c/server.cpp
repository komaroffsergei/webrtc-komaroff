#include "whisper.h"
#include "json.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cctype>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <ctime>
#include <memory>
#include <mutex>
#include <optional>
#include <queue>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "Ws2_32.lib")
#else
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

using json = nlohmann::json;
namespace fs = std::filesystem;

namespace {

#ifdef _WIN32
struct WinsockInit {
    WinsockInit() {
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2, 2), &wsaData);
    }
    ~WinsockInit() {
        WSACleanup();
    }
};
WinsockInit g_winsock_init;
#endif

#ifdef _WIN32
using socket_t = SOCKET;
constexpr socket_t kInvalidSocket = INVALID_SOCKET;
#else
using socket_t = int;
constexpr socket_t kInvalidSocket = -1;
#endif

void close_socket(socket_t sock) {
#ifdef _WIN32
    if (sock != kInvalidSocket) {
        closesocket(sock);
    }
#else
    if (sock != kInvalidSocket) {
        ::close(sock);
    }
#endif
}

#ifndef _WIN32
void shutdown_socket(socket_t sock) {
    if (sock != kInvalidSocket) {
        shutdown(sock, SHUT_RDWR);
    }
}
#else
void shutdown_socket(socket_t sock) {
    if (sock != kInvalidSocket) {
        shutdown(sock, SD_BOTH);
    }
}
#endif

std::string trim_copy(std::string value) {
    auto it = std::find_if_not(value.begin(), value.end(), [](unsigned char ch) { return std::isspace(ch); });
    value.erase(value.begin(), it);
    auto rit = std::find_if_not(value.rbegin(), value.rend(), [](unsigned char ch) { return std::isspace(ch); });
    value.erase(rit.base(), value.end());
    return value;
}

std::string to_lower_copy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    return value;
}

std::string getenv_or(const char *key, const std::string &def) {
    const char *value = std::getenv(key);
    if (!value || !*value) {
        return def;
    }
    return value;
}

bool env_flag(const char *key, bool default_value) {
    const char *value = std::getenv(key);
    if (!value) {
        return default_value;
    }
    std::string normalized = to_lower_copy(trim_copy(value));
    if (normalized.empty()) {
        return default_value;
    }
    if (normalized == "1" || normalized == "true" || normalized == "yes" || normalized == "on") {
        return true;
    }
    if (normalized == "0" || normalized == "false" || normalized == "no" || normalized == "off") {
        return false;
    }
    return default_value;
}

int env_int(const char *key, int default_value) {
    const char *value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return default_value;
    }
}

std::string iso_timestamp() {
    using clock = std::chrono::system_clock;
    const auto now = clock::now();
    const auto sec = std::chrono::time_point_cast<std::chrono::seconds>(now);
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - sec).count();
    std::time_t t = clock::to_time_t(sec);
    std::tm tm{};
#ifdef _WIN32
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    char buffer[48];
    std::snprintf(buffer, sizeof(buffer), "%04d-%02d-%02dT%02d:%02d:%02d.%03lldZ",
                  tm.tm_year + 1900,
                  tm.tm_mon + 1,
                  tm.tm_mday,
                  tm.tm_hour,
                  tm.tm_min,
                  tm.tm_sec,
                  static_cast<long long>(ms));
    return buffer;
}

struct ServiceConfig {
    std::string service_name;
    std::string nats_url;
    std::string frames_subject;
    std::string logs_subject;
    std::string models_dir;
    std::string model_path;
    std::string model_url;
    std::string model_sha1;
    std::string language;
    int threads;
    int processors;
    int beam_size;
    int max_concurrency;
    int min_phrase_ms;
    bool use_gpu;
    bool flash_attn;
};

constexpr const char *kDefaultModelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin";
constexpr const char *kDefaultModelSha1 = "55356645c2b361a969dfd0ef2c5a50d530afd8d5";

ServiceConfig load_config() {
    ServiceConfig cfg{};
    cfg.service_name = getenv_or("STACK_SERVICE_NAME", "src_whisper_c");
    cfg.nats_url = getenv_or("NATS_URL", "nats://127.0.0.1:4222");
    cfg.frames_subject = getenv_or("NATS_FRAMES_SUBJECT", "nats.frames");
    cfg.logs_subject = getenv_or("NATS_LOGS_SUBJECT", "nats.logs");
    cfg.models_dir = getenv_or("ASR_MODELS", "models/asr");
    cfg.model_path = getenv_or("ASR_MODEL_PATH", "");
    cfg.model_url = getenv_or("ASR_MODEL_URL", kDefaultModelUrl);
    cfg.model_sha1 = getenv_or("ASR_MODEL_SHA1", kDefaultModelSha1);
    cfg.language = getenv_or("ASR_LANGUAGE", "ru");
    cfg.threads = env_int("ASR_THREADS", static_cast<int>(std::max(1u, std::thread::hardware_concurrency())));
    cfg.processors = env_int("ASR_PROCESSORS", 1);
    cfg.beam_size = std::max(1, env_int("ASR_BEAM_SIZE", 1));
    cfg.max_concurrency = std::max(1, env_int("ASR_MAX_CONCURRENCY", 1));
    cfg.min_phrase_ms = std::max(1, env_int("ASR_MIN_PHRASE_MS", 100));
    cfg.use_gpu = env_flag("ASR_USE_GPU", false);
    cfg.flash_attn = env_flag("WHISPERCPP_FLASH_ATTN", true);

    if (env_flag("WHISPERCPP_FORCE_CPU", false) || env_flag("WHISPERCPP_DISABLE_GPU", false) ||
        env_flag("WHISPER_NO_GPU", false) || env_flag("GGML_NO_GPU", false)) {
        cfg.use_gpu = false;
    }

    if (std::getenv("GGML_USE_GPU")) {
        cfg.use_gpu = env_flag("GGML_USE_GPU", cfg.use_gpu);
    }

    if (env_flag("ASR_FORCE_CPU", false)) {
        cfg.use_gpu = false;
    }
    if (env_flag("ASR_FORCE_GPU", false)) {
        cfg.use_gpu = true;
    }

    return cfg;
}

struct PhrasePacket {
    std::string phrase_id;
    int sample_rate = 16000;
    float duration = 0.0f;
    std::vector<float> audio;

    static PhrasePacket Parse(const std::vector<uint8_t> &payload) {
        if (payload.size() < 4) {
            throw std::runtime_error("packet too short");
        }
        uint32_t meta_size = (payload[0] << 24) | (payload[1] << 16) | (payload[2] << 8) | payload[3];
        if (payload.size() < 4 + meta_size) {
            throw std::runtime_error("invalid metadata size");
        }
        std::string meta_str(reinterpret_cast<const char *>(payload.data() + 4), meta_size);
        json meta = json::parse(meta_str);

        PhrasePacket packet;
        packet.phrase_id = meta.value("phrase_id", std::string());
        if (packet.phrase_id.empty()) {
            throw std::runtime_error("phrase_id missing");
        }
        packet.sample_rate = meta.value("sample_rate", 0);
        if (packet.sample_rate <= 0) {
            throw std::runtime_error("sample_rate missing");
        }

        const float reported_duration = meta.value("duration", 0.0f);

        const size_t pcm_offset = 4 + meta_size;
        if (payload.size() <= pcm_offset) {
            throw std::runtime_error("packet does not contain audio");
        }
        const size_t pcm_size = payload.size() - pcm_offset;
        if (pcm_size % 2 != 0) {
            throw std::runtime_error("invalid PCM size");
        }
        const size_t sample_count = pcm_size / 2;
        packet.audio.resize(sample_count);
        const uint8_t *pcm_ptr = payload.data() + pcm_offset;
        for (size_t i = 0; i < sample_count; ++i) {
            int16_t sample = static_cast<int16_t>(pcm_ptr[2 * i] | (pcm_ptr[2 * i + 1] << 8));
            packet.audio[i] = static_cast<float>(sample) / 32768.0f;
        }
        if (reported_duration > 0.0f) {
            packet.duration = reported_duration;
        } else {
            packet.duration = static_cast<float>(packet.audio.size()) / static_cast<float>(packet.sample_rate);
        }
        return packet;
    }
};

class Sha1 {
public:
    Sha1() { reset(); }

    void update(const uint8_t *data, size_t len) {
        for (size_t i = 0; i < len; ++i) {
            append_byte(data[i]);
            bit_len_ += 8;
        }
    }

    void update(const char *data, size_t len) {
        update(reinterpret_cast<const uint8_t *>(data), len);
    }

    void update(const std::vector<uint8_t> &data) {
        update(data.data(), data.size());
    }

    std::array<uint8_t, 20> finalize() {
        append_byte(0x80);
        while (buffer_len_ != 56) {
            append_byte(0x00);
        }
        for (int i = 7; i >= 0; --i) {
            append_byte(static_cast<uint8_t>((bit_len_ >> (i * 8)) & 0xFF));
        }
        std::array<uint8_t, 20> digest{};
        for (int i = 0; i < 5; ++i) {
            digest[i * 4] = static_cast<uint8_t>((state_[i] >> 24) & 0xFF);
            digest[i * 4 + 1] = static_cast<uint8_t>((state_[i] >> 16) & 0xFF);
            digest[i * 4 + 2] = static_cast<uint8_t>((state_[i] >> 8) & 0xFF);
            digest[i * 4 + 3] = static_cast<uint8_t>(state_[i] & 0xFF);
        }
        reset();
        return digest;
    }

private:
    void reset() {
        state_[0] = 0x67452301u;
        state_[1] = 0xEFCDAB89u;
        state_[2] = 0x98BADCFEu;
        state_[3] = 0x10325476u;
        state_[4] = 0xC3D2E1F0u;
        bit_len_ = 0;
        buffer_len_ = 0;
    }

    void append_byte(uint8_t byte) {
        buffer_[buffer_len_++] = byte;
        if (buffer_len_ == 64) {
            process_block(buffer_.data());
            buffer_len_ = 0;
        }
    }

    static uint32_t rotl(uint32_t value, int bits) {
        return (value << bits) | (value >> (32 - bits));
    }

    void process_block(const uint8_t *block) {
        uint32_t w[80];
        for (int i = 0; i < 16; ++i) {
            w[i] = (block[i * 4] << 24) |
                   (block[i * 4 + 1] << 16) |
                   (block[i * 4 + 2] << 8) |
                   (block[i * 4 + 3]);
        }
        for (int i = 16; i < 80; ++i) {
            w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        }

        uint32_t a = state_[0];
        uint32_t b = state_[1];
        uint32_t c = state_[2];
        uint32_t d = state_[3];
        uint32_t e = state_[4];

        for (int i = 0; i < 80; ++i) {
            uint32_t f = 0;
            uint32_t k = 0;
            if (i < 20) {
                f = (b & c) | ((~b) & d);
                k = 0x5A827999;
            } else if (i < 40) {
                f = b ^ c ^ d;
                k = 0x6ED9EBA1;
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8F1BBCDC;
            } else {
                f = b ^ c ^ d;
                k = 0xCA62C1D6;
            }
            uint32_t temp = rotl(a, 5) + f + e + k + w[i];
            e = d;
            d = c;
            c = rotl(b, 30);
            b = a;
            a = temp;
        }

        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
    }

    uint32_t state_[5];
    uint64_t bit_len_ = 0;
    std::array<uint8_t, 64> buffer_{};
    size_t buffer_len_ = 0;
};

std::string bytes_to_hex(const std::array<uint8_t, 20> &bytes) {
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (uint8_t byte : bytes) {
        oss << std::setw(2) << static_cast<int>(byte);
    }
    return oss.str();
}

std::string compute_file_sha1(const fs::path &file) {
    std::ifstream stream(file, std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open file for sha1");
    }
    Sha1 sha;
    std::array<char, 8192> buffer{};
    while (stream) {
        stream.read(buffer.data(), buffer.size());
        const std::streamsize read = stream.gcount();
        if (read > 0) {
            sha.update(buffer.data(), static_cast<size_t>(read));
        }
    }
    return bytes_to_hex(sha.finalize());
}

bool sha_matches(const std::string &actual, const std::string &expected) {
    if (expected.empty()) {
        return true;
    }
    return to_lower_copy(actual) == to_lower_copy(expected);
}

std::string file_name_from_url(const std::string &url) {
    const auto slash = url.find_last_of('/') ;
    std::string candidate = (slash == std::string::npos) ? url : url.substr(slash + 1);
    const auto query = candidate.find('?');
    if (query != std::string::npos) {
        candidate = candidate.substr(0, query);
    }
    if (candidate.empty()) {
        candidate = "model.bin";
    }
    return candidate;
}

class NatsLogger;

std::string ensure_model_file(ServiceConfig &cfg, NatsLogger *logger);

class TaskExecutor {
public:
    explicit TaskExecutor(int concurrency) : stop_(false) {
        const int workers = std::max(1, concurrency);
        for (int i = 0; i < workers; ++i) {
            workers_.emplace_back([this]() { worker_loop(); });
        }
    }

    ~TaskExecutor() {
        stop();
    }

    void submit(std::function<void()> job) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stop_) {
                return;
            }
            queue_.push(std::move(job));
        }
        cv_.notify_one();
    }

    void stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stop_) {
                return;
            }
            stop_ = true;
        }
        cv_.notify_all();
        for (auto &thread : workers_) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        workers_.clear();
    }

private:
    void worker_loop() {
        while (true) {
            std::function<void()> job;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                cv_.wait(lock, [this]() { return stop_ || !queue_.empty(); });
                if (stop_ && queue_.empty()) {
                    return;
                }
                job = std::move(queue_.front());
                queue_.pop();
            }
            try {
                job();
            } catch (const std::exception &ex) {
                fprintf(stderr, "task error: %s\n", ex.what());
            }
        }
    }

    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> queue_;
    std::mutex mutex_;
    std::condition_variable cv_;
    bool stop_;
};

struct NatsMessage {
    std::string subject;
    std::string reply;
    std::vector<uint8_t> data;
};

class NatsClient {
public:
    using MessageHandler = std::function<void(NatsMessage)>;

    NatsClient() = default;
    ~NatsClient() {
        close();
    }

    NatsClient(const NatsClient &) = delete;
    NatsClient &operator=(const NatsClient &) = delete;

    bool connect(const std::string &url, const std::string &name) {
        if (socket_ != kInvalidSocket) {
            return true;
        }
        auto urls = split_urls(url);
        std::string last_error;
        for (const auto &candidate : urls) {
            auto parts = parse_url(candidate);
            socket_ = open_socket(parts.host, parts.port, last_error);
            if (socket_ != kInvalidSocket) {
                connected_url_ = parts.host + ":" + parts.port;
                break;
            }
        }
        if (socket_ == kInvalidSocket) {
            fprintf(stderr, "failed to connect to NATS: %s\n", last_error.c_str());
            return false;
        }
        name_ = name;
        if (!send_connect()) {
            close();
            return false;
        }
        running_.store(true);
        reader_thread_ = std::thread([this]() { reader_loop(); });
        return true;
    }

    void close() {
        running_.store(false);
        if (socket_ != kInvalidSocket) {
            shutdown_socket(socket_);
        }
        if (reader_thread_.joinable()) {
            reader_thread_.join();
        }
        close_socket(socket_);
        socket_ = kInvalidSocket;
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_.clear();
    }

    bool publish(const std::string &subject, const std::string &payload) {
        return publish(subject, std::string(), payload);
    }

    bool publish(const std::string &subject, const std::string &reply, const std::string &payload) {
        if (socket_ == kInvalidSocket) {
            return false;
        }
        std::ostringstream oss;
        oss << "PUB " << subject << ' ';
        if (!reply.empty()) {
            oss << reply << ' ';
        }
        oss << payload.size() << "\r\n";
        const std::string header = oss.str();
        const std::string trailer = "\r\n";
        std::lock_guard<std::mutex> lock(write_mutex_);
        return write_all(header) && write_all(payload) && write_all(trailer);
    }

    int subscribe(const std::string &subject, MessageHandler handler) {
        if (socket_ == kInvalidSocket) {
            return -1;
        }
        const int sid = next_sid_++;
        std::ostringstream oss;
        oss << "SUB " << subject << ' ' << sid << "\r\n";
        {
            std::lock_guard<std::mutex> lock(write_mutex_);
            if (!write_all(oss.str())) {
                return -1;
            }
        }
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[sid] = std::move(handler);
        return sid;
    }

    std::string connected_url() const {
        return connected_url_;
    }

private:
    struct UrlParts {
        std::string host;
        std::string port;
    };

    static std::vector<std::string> split_urls(const std::string &urls) {
        std::vector<std::string> result;
        std::stringstream ss(urls);
        std::string segment;
        while (std::getline(ss, segment, ',')) {
            const std::string trimmed = trim_copy(segment);
            if (!trimmed.empty()) {
                result.push_back(trimmed);
            }
        }
        if (result.empty()) {
            result.push_back(urls);
        }
        return result;
    }

    static UrlParts parse_url(const std::string &url) {
        std::string rest = url;
        const auto scheme = rest.find("://");
        if (scheme != std::string::npos) {
            rest = rest.substr(scheme + 3);
        }
        const auto slash = rest.find('/');
        if (slash != std::string::npos) {
            rest = rest.substr(0, slash);
        }
        const auto at = rest.rfind('@');
        if (at != std::string::npos) {
            rest = rest.substr(at + 1);
        }
        UrlParts parts;
        const auto colon = rest.rfind(':');
        if (colon != std::string::npos) {
            parts.host = rest.substr(0, colon);
            parts.port = rest.substr(colon + 1);
        } else {
            parts.host = rest;
            parts.port = "4222";
        }
        if (parts.host.empty()) {
            parts.host = "127.0.0.1";
        }
        if (parts.port.empty()) {
            parts.port = "4222";
        }
        return parts;
    }

    socket_t open_socket(const std::string &host, const std::string &port, std::string &err) {
        struct addrinfo hints;
        std::memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;
        struct addrinfo *res = nullptr;
        const int rc = getaddrinfo(host.c_str(), port.c_str(), &hints, &res);
        if (rc != 0) {
            err = gai_strerror(rc);
            return kInvalidSocket;
        }
        socket_t sock = kInvalidSocket;
        for (struct addrinfo *ptr = res; ptr != nullptr; ptr = ptr->ai_next) {
            sock = static_cast<socket_t>(::socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol));
            if (sock == kInvalidSocket) {
                continue;
            }
            if (::connect(sock, ptr->ai_addr, static_cast<int>(ptr->ai_addrlen)) == 0) {
                break;
            }
            close_socket(sock);
            sock = kInvalidSocket;
        }
        freeaddrinfo(res);
        if (sock == kInvalidSocket) {
            err = "unable to connect";
        }
        return sock;
    }

    bool write_all(const std::string &data) {
        return write_all(data.data(), data.size());
    }

    bool write_all(const char *data, size_t len) {
        size_t total = 0;
        while (total < len) {
#ifdef _WIN32
            const int sent = send(socket_, data + total, static_cast<int>(len - total), 0);
#else
            const ssize_t sent = ::send(socket_, data + total, len - total, 0);
#endif
            if (sent <= 0) {
                return false;
            }
            total += static_cast<size_t>(sent);
        }
        return true;
    }

    bool send_connect() {
        json payload = {
            {"lang", "cpp"},
            {"version", "1.0"},
            {"name", name_},
            {"verbose", false},
            {"pedantic", false},
            {"echo", true},
        };
        std::ostringstream oss;
        oss << "CONNECT " << payload.dump() << "\r\n";
        return write_all(oss.str());
    }

    void reader_loop() {
        std::string buffer;
        buffer.reserve(16 * 1024);
        Pending pending;
        while (running_.load()) {
            char chunk[4096];
#ifdef _WIN32
            const int read_bytes = recv(socket_, chunk, sizeof(chunk), 0);
#else
            const ssize_t read_bytes = ::recv(socket_, chunk, sizeof(chunk), 0);
#endif
            if (read_bytes <= 0) {
                break;
            }
            buffer.append(chunk, static_cast<size_t>(read_bytes));
            process_buffer(buffer, pending);
        }
        running_.store(false);
    }

    struct Pending {
        bool awaiting_payload = false;
        int sid = 0;
        size_t payload_size = 0;
        std::string subject;
        std::string reply;
    };

    void process_buffer(std::string &buffer, Pending &pending) {
        while (true) {
            if (pending.awaiting_payload) {
                if (buffer.size() < pending.payload_size + 2) {
                    return;
                }
                std::vector<uint8_t> data(pending.payload_size);
                std::memcpy(data.data(), buffer.data(), pending.payload_size);
                buffer.erase(0, pending.payload_size + 2);
                pending.awaiting_payload = false;
                dispatch_message(pending.sid, pending.subject, pending.reply, std::move(data));
                continue;
            }
            const auto pos = buffer.find("\r\n");
            if (pos == std::string::npos) {
                return;
            }
            std::string line = buffer.substr(0, pos);
            buffer.erase(0, pos + 2);
            if (line.empty()) {
                continue;
            }
            if (line.rfind("MSG", 0) == 0) {
                std::istringstream iss(line);
                std::string op;
                iss >> op;
                std::string subject;
                std::string sid_str;
                std::string token;
                std::vector<std::string> tokens;
                while (iss >> token) {
                    tokens.push_back(token);
                }
                if (tokens.size() < 2) {
                    continue;
                }
                subject = tokens[0];
                sid_str = tokens[1];
                std::string reply;
                size_t size_index = 2;
                if (tokens.size() == 3) {
                    // no reply
                } else if (tokens.size() >= 4) {
                    reply = tokens[2];
                    size_index = 3;
                }
                size_t payload_size = 0;
                try {
                    payload_size = static_cast<size_t>(std::stoul(tokens[size_index]));
                } catch (...) {
                    continue;
                }
                int sid_value = 0;
                try {
                    sid_value = std::stoi(sid_str);
                } catch (...) {
                    continue;
                }
                pending.awaiting_payload = true;
                pending.sid = sid_value;
                pending.payload_size = payload_size;
                pending.subject = subject;
                pending.reply = reply;
                continue;
            }
            if (line.rfind("PING", 0) == 0) {
                write_all("PONG\r\n");
                continue;
            }
            if (line.rfind("+OK", 0) == 0 || line.rfind("PONG", 0) == 0) {
                continue;
            }
            if (line.rfind("-ERR", 0) == 0) {
                fprintf(stderr, "nats error: %s\n", line.c_str());
                continue;
            }
            // INFO or others ignored
        }
    }

    void dispatch_message(int sid, const std::string &subject, const std::string &reply, std::vector<uint8_t> data) {
        MessageHandler handler;
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            auto it = subscriptions_.find(sid);
            if (it != subscriptions_.end()) {
                handler = it->second;
            }
        }
        if (handler) {
            NatsMessage msg;
            msg.subject = subject;
            msg.reply = reply;
            msg.data = std::move(data);
            handler(std::move(msg));
        }
    }

    socket_t socket_ = kInvalidSocket;
    std::thread reader_thread_;
    std::atomic<bool> running_{false};
    std::mutex write_mutex_;
    std::mutex subscriptions_mutex_;
    std::unordered_map<int, MessageHandler> subscriptions_;
    int next_sid_ = 1;
    std::string name_;
    std::string connected_url_;
};

class NatsLogger {
public:
    NatsLogger(NatsClient &client, std::string subject, std::string service)
        : client_(client), subject_(std::move(subject)), service_(std::move(service)) {}

    void info(const std::string &message, const std::string &name = std::string()) {
        publish("log", "info", json{{"text", message}}, name);
    }

    void info(const json &message, const std::string &name) {
        publish("log", "info", json{{"payload", message}}, name);
    }

    void error(const std::string &message, const std::string &name = std::string()) {
        publish("log", "error", json{{"text", message}}, name);
    }

    void command(const std::string &kind, const json &data, const std::string &name = std::string()) {
        publish("command", kind, data, name);
    }

private:
    static std::string uuid_v4() {
        static thread_local std::mt19937_64 rng{std::random_device{}()};
        std::uniform_int_distribution<uint64_t> dist;
        uint8_t bytes[16];
        for (int i = 0; i < 16; i += 8) {
            uint64_t v = dist(rng);
            std::memcpy(bytes + i, &v, sizeof(v));
        }
        bytes[6] = (bytes[6] & 0x0F) | 0x40;
        bytes[8] = (bytes[8] & 0x3F) | 0x80;
        char out[37];
        std::snprintf(
            out,
            sizeof(out),
            "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
            bytes[0], bytes[1], bytes[2], bytes[3],
            bytes[4], bytes[5],
            bytes[6], bytes[7],
            bytes[8], bytes[9],
            bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
        );
        return std::string(out);
    }

    void publish(const std::string &type, const std::string &kind, const json &data, const std::string &name) {
        json payload = {
            {"time", iso_timestamp()},
            {"service", service_},
            {"type", type},
            {"kind", kind},
            {"data", data},
            {"name", name},
            {"uid", uuid_v4()},
        };
        if (!client_.publish(subject_, payload.dump())) {
            fprintf(stderr, "logger publish failed: %s\n", payload.dump().c_str());
        }
    }

    NatsClient &client_;
    std::string subject_;
    std::string service_;
};

FILE *open_pipe(const std::string &command) {
#ifdef _WIN32
    return _popen(command.c_str(), "r");
#else
    return popen(command.c_str(), "r");
#endif
}

int close_pipe(FILE *pipe) {
#ifdef _WIN32
    return _pclose(pipe);
#else
    return pclose(pipe);
#endif
}

int run_with_progress_logging(const std::string &command, const std::function<void(int)> &on_percent) {
    std::string full_command = command + " 2>&1";
    FILE *pipe = open_pipe(full_command);
    if (!pipe) {
        return -1;
    }

    std::string buffer;
    buffer.reserve(256);
    int last_percent = -1;

    auto process_line = [&](std::string line) {
        line = trim_copy(line);
        if (line.empty()) {
            return;
        }
        unsigned char first = static_cast<unsigned char>(line[0]);
        if (!std::isdigit(first)) {
            fprintf(stderr, "%s\n", line.c_str());
            return;
        }
        try {
            int percent = static_cast<int>(std::stod(line));
            percent = std::clamp(percent, 0, 100);
            if (percent != last_percent) {
                last_percent = percent;
                if (on_percent) {
                    on_percent(percent);
                }
            }
        } catch (...) {
            fprintf(stderr, "%s\n", line.c_str());
        }
    };

    char chunk[256];
    while (fgets(chunk, sizeof(chunk), pipe)) {
        buffer.append(chunk);
        size_t keep_from = 0;
        while (true) {
            size_t delim = buffer.find_first_of("\r\n", keep_from);
            if (delim == std::string::npos) {
                buffer.erase(0, keep_from);
                break;
            }
            std::string line = buffer.substr(keep_from, delim - keep_from);
            process_line(line);
            keep_from = delim + 1;
            while (keep_from < buffer.size() && (buffer[keep_from] == '\r' || buffer[keep_from] == '\n')) {
                ++keep_from;
            }
        }
    }

    if (!buffer.empty()) {
        process_line(buffer);
    }

    return close_pipe(pipe);
}

std::string ensure_model_file(ServiceConfig &cfg, NatsLogger *logger) {
    fs::path models_dir = fs::absolute(cfg.models_dir);
    std::error_code ec;
    fs::create_directories(models_dir, ec);
    if (ec) {
        fprintf(stderr, "failed to create models dir: %s\n", ec.message().c_str());
    }

    fs::path model_path;
    if (!cfg.model_path.empty()) {
        model_path = fs::absolute(cfg.model_path);
    } else {
        model_path = models_dir / file_name_from_url(cfg.model_url);
        cfg.model_path = model_path.string();
    }

    auto publish_status_asr = [&](const std::string &status, std::optional<int> percent = std::nullopt) {
        if (!logger) {
            return;
        }
        json data = {{"status", status}};
        if (percent.has_value()) {
            data["percent"] = percent.value();
        }
        logger->command("status_asr", data);
    };

    if (fs::exists(model_path)) {
        if (!cfg.model_sha1.empty()) {
            const std::string actual = compute_file_sha1(model_path);
            if (!sha_matches(actual, cfg.model_sha1)) {
                if (logger) {
                    logger->info("Checksum mismatch, redownloading");
                }
                fs::remove(model_path);
            } else {
                publish_status_asr("ready");
                return model_path.string();
            }
        } else {
            publish_status_asr("ready");
            return model_path.string();
        }
    }

    if (cfg.model_url.empty()) {
        throw std::runtime_error("model missing and ASR_MODEL_URL is not set");
    }

    publish_status_asr("downloading", 0);

    fs::path tmp_path = model_path;
    tmp_path += ".download";

    std::ostringstream cmd;
    cmd << "curl -L --fail --retry 5 --retry-delay 2 -o "
        << std::quoted(tmp_path.string()) << ' '
        << std::quoted(cfg.model_url);

    auto progress_logger = [&](int percent) {
        publish_status_asr("downloading", percent);
    };
    const int rc = run_with_progress_logging(cmd.str(), progress_logger);
    if (rc != 0 || !fs::exists(tmp_path)) {
        throw std::runtime_error("failed to download model from " + cfg.model_url);
    }

    if (!cfg.model_sha1.empty()) {
        const std::string actual = compute_file_sha1(tmp_path);
        if (!sha_matches(actual, cfg.model_sha1)) {
            fs::remove(tmp_path);
            throw std::runtime_error("checksum mismatch after download");
        }
    }

    fs::rename(tmp_path, model_path);

    publish_status_asr("downloading", 100);
    publish_status_asr("ready");
    return model_path.string();
}

class WhisperEngine {
public:
    WhisperEngine(const ServiceConfig &cfg, const std::string &model_path) : config_(cfg) {
        struct whisper_context_params cparams = whisper_context_default_params();
        cparams.use_gpu = cfg.use_gpu;
        cparams.flash_attn = cfg.flash_attn;
        ctx_ = whisper_init_from_file_with_params(model_path.c_str(), cparams);
        if (!ctx_) {
            throw std::runtime_error("failed to initialize whisper context");
        }
        whisper_ctx_init_openvino_encoder(ctx_, nullptr, "CPU", nullptr);
    }

    ~WhisperEngine() {
        if (ctx_) {
            whisper_free(ctx_);
            ctx_ = nullptr;
        }
    }

    std::string transcribe(const PhrasePacket &packet) {
        std::vector<float> audio = packet.audio;
        const size_t min_samples = static_cast<size_t>(std::max(1, config_.min_phrase_ms) * packet.sample_rate / 1000);
        if (audio.size() < min_samples) {
            audio.resize(min_samples, 0.0f);
        }

        const bool beam_search = config_.beam_size > 1;
        whisper_full_params wparams = whisper_full_default_params(
            beam_search ? WHISPER_SAMPLING_BEAM_SEARCH : WHISPER_SAMPLING_GREEDY);

        wparams.print_realtime = false;
        wparams.print_progress = false;
        wparams.print_timestamps = false;
        wparams.translate = false;
        wparams.no_timestamps = true;
        wparams.language = config_.language.c_str();
        wparams.detect_language = false;
        wparams.n_threads = std::max(1, config_.threads);
        wparams.n_max_text_ctx = 0;
        wparams.offset_ms = 0;
        wparams.duration_ms = 0;
        wparams.max_len = 0;
        wparams.temperature = 0.0f;
        wparams.temperature_inc = 0.2f;
        wparams.entropy_thold = 2.4f;
        wparams.logprob_thold = -1.0f;
        wparams.thold_pt = 0.01f;
        wparams.no_context = true;
        wparams.single_segment = true;
        wparams.greedy.best_of = std::max(1, config_.beam_size);
        wparams.beam_search.beam_size = std::max(1, config_.beam_size);
        wparams.suppress_blank = true;

        std::lock_guard<std::mutex> lock(mutex_);
        const int rc = whisper_full_parallel(ctx_, wparams, audio.data(), audio.size(), std::max(1, config_.processors));
        if (rc != 0) {
            throw std::runtime_error("whisper_full_parallel failed");
        }
        const int segments = whisper_full_n_segments(ctx_);
        std::string text;
        for (int i = 0; i < segments; ++i) {
            const char *segment_text = whisper_full_get_segment_text(ctx_, i);
            if (segment_text && *segment_text) {
                if (!text.empty()) {
                    text.push_back(' ');
                }
                text += segment_text;
            }
        }
        return trim_copy(text);
    }

private:
    ServiceConfig config_;
    struct whisper_context *ctx_ = nullptr;
    std::mutex mutex_;
};

class WhisperService {
public:
    explicit WhisperService(ServiceConfig cfg)
        : config_(std::move(cfg)), executor_(config_.max_concurrency) {}

    bool start() {
        if (!nats_.connect(config_.nats_url, config_.service_name)) {
            fprintf(stderr, "failed to connect to NATS\n");
            return false;
        }
        logger_ = std::make_unique<NatsLogger>(nats_, config_.logs_subject, config_.service_name);
        logger_->info("Whisper C++ service connected");
        if (!nats_.connected_url().empty()) {
            logger_->info("Connected to " + nats_.connected_url());
        }
        try {
            const std::string model_path = ensure_model_file(config_, logger_.get());
            engine_ = std::make_unique<WhisperEngine>(config_, model_path);
            logger_->info(std::string("Model loaded"), std::string("model_status"));
        } catch (const std::exception &ex) {
            logger_->error(std::string("Model preparation failed: ") + ex.what(), std::string("model_status"));
            return false;
        }
        const int sid = nats_.subscribe(config_.frames_subject, [this](NatsMessage msg) {
            handle_message(std::move(msg));
        });
        if (sid < 0) {
            logger_->error("Failed to subscribe to frames subject");
            return false;
        }
        logger_->info("Subscribed to " + config_.frames_subject);
        started_.store(true);
        return true;
    }

    void request_stop() {
        if (!stop_requested_.exchange(true)) {
            logger_->info("Shutdown requested");
        }
    }

    bool stop_requested() const {
        return stop_requested_.load();
    }

    void shutdown() {
        executor_.stop();
        nats_.close();
        engine_.reset();
    }

private:
    void handle_message(NatsMessage msg) {
        if (stop_requested()) {
            return;
        }
        executor_.submit([this, message = std::move(msg)]() mutable {
            process_message(std::move(message));
        });
    }

    void process_message(NatsMessage msg) {
        if (msg.data.empty()) {
            return;
        }
        PhrasePacket packet;
        try {
            packet = PhrasePacket::Parse(msg.data);
        } catch (const std::exception &ex) {
            logger_->error(std::string("Invalid packet: ") + ex.what());
            reply_error(msg, "invalid_packet", ex.what(), "");
            return;
        }

        logger_->info("Phrase received id=" + packet.phrase_id + " dur=" + std::to_string(packet.duration));
        logger_->info("Transcription started phrase_id=" + packet.phrase_id);

        const auto started = std::chrono::steady_clock::now();
        try {
            const std::string text = engine_->transcribe(packet);
            const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
            json payload = {
                {"phrase_id", packet.phrase_id},
                {"text", text},
                {"duration", packet.duration},
                {"transcribe_time", elapsed},
            };
            logger_->info("Transcription finished phrase_id=" + packet.phrase_id + " time=" + std::to_string(elapsed) + "s");
            logger_->info(payload, "transcription_result");
            reply(msg, payload);
        } catch (const std::exception &ex) {
            logger_->error(std::string("Transcription error: ") + ex.what());
            reply_error(msg, "transcription_failed", ex.what(), packet.phrase_id);
        }
    }

    void reply(const NatsMessage &msg, const json &payload) {
        if (msg.reply.empty()) {
            return;
        }
        nats_.publish(msg.reply, payload.dump());
    }

    void reply_error(const NatsMessage &msg, const std::string &error, const std::string &details, const std::string &phrase_id) {
        if (msg.reply.empty()) {
            return;
        }
        json payload = {
            {"error", error},
            {"details", details},
        };
        if (!phrase_id.empty()) {
            payload["phrase_id"] = phrase_id;
        }
        nats_.publish(msg.reply, payload.dump());
    }

    ServiceConfig config_;
    NatsClient nats_;
    std::unique_ptr<NatsLogger> logger_;
    std::unique_ptr<WhisperEngine> engine_;
    TaskExecutor executor_;
    std::atomic<bool> stop_requested_{false};
    std::atomic<bool> started_{false};
};

std::unique_ptr<WhisperService> g_service;
std::atomic<bool> g_signal_stop{false};

void handle_signal(int) {
    g_signal_stop.store(true);
}

} // namespace

int main() {
    ggml_backend_load_all();
    ServiceConfig config = load_config();
    g_service = std::make_unique<WhisperService>(config);

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    if (!g_service->start()) {
        fprintf(stderr, "whisper service failed to start\n");
        g_service->shutdown();
        return 1;
    }

    while (!g_signal_stop.load() && !g_service->stop_requested()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    g_service->request_stop();
    g_service->shutdown();
    return 0;
}
