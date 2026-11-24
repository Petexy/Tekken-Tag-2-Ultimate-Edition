// One launcher per user: the message (see single_instance.h).

#include "single_instance.h"

namespace launcher {

namespace {

std::string escape(const std::string& text) {
    std::string out;
    for (const char c : text) {
        if (c == '\\') {
            out += "\\\\";
        } else if (c == '\n') {
            out += "\\n";
        } else if (c == '\r') {
            out += "\\r";
        } else {
            out += c;
        }
    }
    return out;
}

bool unescape(std::string_view text, std::string* out) {
    out->clear();
    for (size_t i = 0; i < text.size(); ++i) {
        if (text[i] != '\\') {
            *out += text[i];
            continue;
        }
        if (++i == text.size()) return false;
        if (text[i] == '\\') {
            *out += '\\';
        } else if (text[i] == 'n') {
            *out += '\n';
        } else if (text[i] == 'r') {
            *out += '\r';
        } else {
            return false;
        }
    }
    return true;
}

} // namespace

std::string encode_forwarded(const Forwarded& message) {
    std::string out;
    for (const std::string& arg : message.args) out += "arg " + escape(arg) + "\n";
    if (!message.token.empty()) out += "token " + escape(message.token) + "\n";
    return out + "end\n";
}

bool decode_forwarded(const std::string& text, Forwarded* message) {
    Forwarded m;
    for (size_t start = 0; start < text.size();) {
        const size_t end = text.find('\n', start);
        if (end == std::string::npos) return false;
        const std::string_view line = std::string_view(text).substr(start, end - start);
        start = end + 1;
        std::string value;
        if (line == "end") {
            *message = std::move(m);
            return start == text.size();
        }
        if (line.rfind("arg ", 0) == 0 && unescape(line.substr(4), &value)) {
            m.args.push_back(value);
        } else if (line.rfind("token ", 0) == 0 && unescape(line.substr(6), &value)) {
            m.token = value;
        } else {
            return false;
        }
    }
    return false;
}

std::vector<Forwarded> SingleInstance::take() {
    std::lock_guard lock(shared_->mutex);
    std::vector<Forwarded> out;
    out.swap(shared_->arrived);
    return out;
}

} // namespace launcher
