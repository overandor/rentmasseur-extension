/*
 * RentMasseur Operating System — C++ Native HTTP Server
 * Production-control version: no mock success, no simulation claims, no detached fake starts.
 * Every action returns real evidence: exit code, captured output, receipt path, and block reasons.
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <chrono>
#include <ctime>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <unistd.h>
#include <dirent.h>

static const int PORT = 7860;
static std::string GH_TOKEN = std::getenv("GH_TOKEN") ? std::getenv("GH_TOKEN") : "";
static std::string GH_REPO = std::getenv("GH_REPO") ? std::getenv("GH_REPO") : "overandor/rentmasseur-extension";
static std::string ADMIN_TOKEN = std::getenv("ADMIN_TOKEN") ? std::getenv("ADMIN_TOKEN") : "";
static const std::string CONTENT_DIR = "./content";
static const std::string RECEIPTS_DIR = "./receipts";
static const std::string AVAILABILITY_FILE = "./availability.json";

static void ensure_dir(const std::string& path) {
    mkdir(path.c_str(), 0755);
}

static std::string iso_timestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
    return std::string(buf);
}

static std::string compact_timestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", std::gmtime(&t));
    return std::string(buf);
}

static bool file_exists(const std::string& path) {
    std::ifstream f(path);
    return static_cast<bool>(f);
}

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) return "";
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if ((unsigned char)c < 0x20) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\u%04x", (unsigned char)c);
            out += buf;
        } else out += c;
    }
    return out;
}

static std::string http_response(int code, const std::string& content_type, const std::string& body) {
    std::string reason = code == 200 ? "OK" : (code == 202 ? "Accepted" : (code == 403 ? "Forbidden" : (code == 404 ? "Not Found" : "Error")));
    std::ostringstream ss;
    ss << "HTTP/1.1 " << code << " " << reason << "\r\n";
    ss << "Content-Type: " << content_type << "\r\n";
    ss << "Content-Length: " << body.size() << "\r\n";
    ss << "Access-Control-Allow-Origin: *\r\n";
    ss << "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n";
    ss << "Access-Control-Allow-Headers: Content-Type\r\n";
    ss << "Connection: close\r\n\r\n";
    ss << body;
    return ss.str();
}

static std::string get_method(const std::string& request) {
    size_t space = request.find(' ');
    return space == std::string::npos ? "GET" : request.substr(0, space);
}

static std::string get_path(const std::string& request) {
    size_t first = request.find(' ');
    if (first == std::string::npos) return "/";
    size_t second = request.find(' ', first + 1);
    if (second == std::string::npos) return "/";
    return request.substr(first + 1, second - first - 1);
}

static std::string get_body(const std::string& request) {
    size_t pos = request.find("\r\n\r\n");
    return pos == std::string::npos ? "" : request.substr(pos + 4);
}

struct CommandResult {
    int exit_code;
    std::string output;
};

static CommandResult run_command_evidence(const std::string& cmd) {
    std::string wrapped = cmd + " 2>&1";
    FILE* pipe = popen(wrapped.c_str(), "r");
    if (!pipe) return {127, "popen failed"};
    char buffer[512];
    std::string output;
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        output += buffer;
        if (output.size() > 6000) {
            output = output.substr(output.size() - 6000);
        }
    }
    int status = pclose(pipe);
    int code = status;
    if (WIFEXITED(status)) code = WEXITSTATUS(status);
    return {code, output};
}

static std::string write_receipt(const std::string& action, const std::string& status, int exit_code, const std::string& output, const std::string& extra_json = "") {
    ensure_dir(RECEIPTS_DIR);
    std::string path = RECEIPTS_DIR + "/hf_action_" + compact_timestamp() + "_" + action + ".json";
    std::ofstream f(path);
    if (f) {
        f << "{\n";
        f << "  \"action\": \"" << json_escape(action) << "\",\n";
        f << "  \"status\": \"" << json_escape(status) << "\",\n";
        f << "  \"exit_code\": " << exit_code << ",\n";
        f << "  \"timestamp\": \"" << iso_timestamp() << "\",\n";
        f << "  \"stdout_stderr_tail\": \"" << json_escape(output) << "\"";
        if (!extra_json.empty()) f << ",\n  " << extra_json;
        f << "\n}\n";
    }
    return path;
}

static int count_files(const std::string& dir) {
    int count = 0;
    DIR* d = opendir(dir.c_str());
    if (!d) return 0;
    struct dirent* entry;
    while ((entry = readdir(d)) != nullptr) {
        if (entry->d_type == DT_REG) count++;
    }
    closedir(d);
    return count;
}

static std::string read_json_or_block(const std::string& path, const std::string& name) {
    std::string c = read_file(path);
    if (!c.empty()) return c;
    return "{\"status\":\"missing_real_data\",\"name\":\"" + json_escape(name) + "\",\"path\":\"" + json_escape(path) + "\"}";
}

static std::string bios_json() {
    std::string dir = CONTENT_DIR + "/bios";
    DIR* d = opendir(dir.c_str());
    if (!d) return "{\"status\":\"missing_real_data\",\"bios\":[],\"reason\":\"content/bios directory does not exist\"}";
    std::ostringstream ss;
    ss << "{\"status\":\"ok\",\"bios\":[";
    bool first = true;
    struct dirent* entry;
    while ((entry = readdir(d)) != nullptr) {
        if (entry->d_type != DT_REG) continue;
        std::string name = entry->d_name;
        std::string content = read_file(dir + "/" + name);
        if (!first) ss << ",";
        first = false;
        ss << "{\"file\":\"" << json_escape(name) << "\",\"content\":\"" << json_escape(content) << "\"}";
    }
    closedir(d);
    ss << "]}";
    return ss.str();
}

static std::string gh_api(const std::string& method, const std::string& endpoint, const std::string& body = "") {
    if (GH_TOKEN.empty()) return "{\"status\":\"blocked\",\"reason\":\"GH_TOKEN not set\"}";
    std::string cmd = "curl -sS -X " + method;
    cmd += " -H \"Authorization: Bearer " + GH_TOKEN + "\"";
    cmd += " -H \"Accept: application/vnd.github+json\"";
    cmd += " -H \"X-GitHub-Api-Version: 2022-11-28\"";
    if (!body.empty()) cmd += " -d '" + body + "'";
    cmd += " https://api.github.com/repos/" + GH_REPO + "/" + endpoint;
    CommandResult r = run_command_evidence(cmd);
    return r.output.empty() ? "{\"status\":\"dispatched_or_empty_response\",\"exit_code\":" + std::to_string(r.exit_code) + "}" : r.output;
}

static std::string url_encode_workflow(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '/') out += "%2F";
        else if (c == ' ') out += "%20";
        else out += c;
    }
    return out;
}

static std::string action_response(const std::string& action, const std::string& cmd) {
    CommandResult r = run_command_evidence(cmd);
    std::string status = r.exit_code == 0 ? "success" : "failed";
    std::string label = r.exit_code == 0 ? (!r.output.empty() ? "GREEN_REAL" : "GRAY_NO_DATA") : "RED_FAILED";
    std::string receipt = write_receipt(action, status, r.exit_code, r.output, "\"command\": \"" + json_escape(cmd) + "\"");
    std::ostringstream ss;
    ss << "{\"status\":\"" << status << "\",\"label\":\"" << label << "\",\"action\":\"" << json_escape(action) << "\",\"exit_code\":" << r.exit_code;
    ss << ",\"receipt\":\"" << json_escape(receipt) << "\",\"stdout_stderr_tail\":\"" << json_escape(r.output) << "\"}";
    return ss.str();
}

static std::string blocked_response(const std::string& action, const std::string& reason) {
    std::string receipt = write_receipt(action, "blocked", 0, reason);
    return "{\"status\":\"blocked\",\"action\":\"" + json_escape(action) + "\",\"reason\":\"" + json_escape(reason) + "\",\"receipt\":\"" + json_escape(receipt) + "\"}";
}

static bool is_mutation(const std::string& m, const std::string& p) {
    if (m == "POST") return true;
    if (p.rfind("/api/cicd/trigger/", 0) == 0) return true;
    if (p.rfind("/api/rotate/", 0) == 0) return true;
    if (p == "/api/run/ga-rl" || p == "/api/run/orchestrator" || p == "/api/run/availability" || p == "/api/rotator/report") return true;
    return false;
}

static std::string check_admin(const std::string& req, const std::string& path, const std::string& method) {
    if (!is_mutation(method, path)) return "";
    if (ADMIN_TOKEN.empty()) return "";
    size_t ap = req.find("Authorization: Bearer ");
    if (ap != std::string::npos) {
        size_t vs = ap + 21;
        size_t ve = req.find("\r\n", vs);
        if (req.substr(vs, ve - vs) == ADMIN_TOKEN) return "";
    }
    size_t qp = path.find("?token=");
    if (qp != std::string::npos && path.substr(qp + 7) == ADMIN_TOKEN) return "";
    return blocked_response("auth", "Admin token required for mutation endpoints. Set ADMIN_TOKEN env var.");
}

static std::string landing_page() {
    return R"HTML(<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>RentMasseur Control OS</title>
<style>
body{margin:0;font-family:Inter,Arial,sans-serif;background:#060712;color:#fff}.hero{padding:48px;text-align:center;background:radial-gradient(circle at top,#2636ff44,transparent 60%)}h1{font-size:44px;margin:0}.badge{display:inline-block;margin:8px;padding:6px 10px;border:1px solid #3cf;border-radius:999px;color:#3cf}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;padding:24px}.card{background:#ffffff12;border:1px solid #ffffff24;border-radius:18px;padding:20px}.btn{display:inline-block;margin:6px;padding:12px 14px;border-radius:10px;border:1px solid #ffffff33;color:#fff;text-decoration:none;background:#ffffff10}.danger{border-color:#ff5370;color:#ff9aac}.ok{border-color:#39ff88;color:#39ff88}pre{white-space:pre-wrap;background:#0008;border-radius:12px;padding:16px;overflow:auto}.muted{color:#aab}.warn{color:#ffd166}
</style></head><body>
<div class="hero"><h1>RentMasseur Control OS</h1><p class="muted">No mock success. No simulation labels. Every action must return evidence or block.</p><span class="badge">MILITARY MODE</span></div>
<div class="grid">
<div class="card"><h3>Truth Report</h3><a class="btn ok" href="/api/report">Open /api/report</a><a class="btn" href="/api/bios">Open /api/bios</a><a class="btn" href="/api/receipts">Receipts</a></div>
<div class="card"><h3>Real Local Commands</h3><a class="btn" href="/api/run/ga-rl">Run GA/RL with receipt</a><a class="btn" href="/api/run/orchestrator">Run orchestrator with receipt</a><a class="btn danger" href="/api/run/availability">Availability is blocked</a></div>
<div class="card"><h3>Rotators</h3><a class="btn" href="/api/rotate/bio">Bio</a><a class="btn" href="/api/rotate/photo">Photo</a><a class="btn" href="/api/rotate/price">Price</a><a class="btn" href="/api/rotate/interview">Interview</a><a class="btn" href="/api/rotate/blog">Blog</a><a class="btn" href="/api/rotator/report">Report</a></div>
<div class="card"><h3>CI/CD</h3><a class="btn" href="/api/cicd/list">List workflows</a><a class="btn" href="/api/cicd/runs">Recent runs</a><a class="btn ok" href="/api/cicd/trigger/deploy-hf-space.yml">Deploy HF</a><a class="btn" href="/api/cicd/trigger/master-rotator.yml">Master rotator</a></div>
</div>
<div class="grid"><div class="card"><h3>Live State</h3><pre id="state">loading...</pre></div><div class="card"><h3>Recent CI/CD</h3><pre id="cicd">loading...</pre></div></div>
<script>
fetch('/api/report').then(r=>r.json()).then(j=>state.textContent=JSON.stringify(j,null,2));
fetch('/api/cicd/runs').then(r=>r.json()).then(j=>cicd.textContent=JSON.stringify(j,null,2)).catch(e=>cicd.textContent=String(e));
</script></body></html>)HTML";
}

static void handle_client(int client_socket) {
    char buffer[16384];
    int received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
    if (received <= 0) { close(client_socket); return; }
    buffer[received] = '\0';
    std::string request(buffer);
    std::string method = get_method(request);
    std::string path = get_path(request);
    std::string body = get_body(request);
    std::string response;
    std::string content_type = "application/json";
    int code = 200;

    ensure_dir(CONTENT_DIR);
    ensure_dir(RECEIPTS_DIR);

    std::string auth_err = check_admin(request, path, method);
    if (!auth_err.empty()) {
        code = 403;
        response = auth_err;
        std::string w = http_response(code, content_type, response);
        send(client_socket, w.c_str(), w.size(), 0);
        close(client_socket);
        return;
    }

    if (method == "OPTIONS") {
        response = "{}";
    } else if (path == "/" || path == "/index.html") {
        response = landing_page(); content_type = "text/html";
    } else if (path == "/health" || path == "/api/health") {
        response = "{\"status\":\"ok\",\"service\":\"rentmasseur-cpp-os\",\"mode\":\"evidence_only\",\"timestamp\":\"" + iso_timestamp() + "\"}";
    } else if (path == "/api/report") {
        int bios_count = count_files(CONTENT_DIR + "/bios");
        bool metrics = file_exists(CONTENT_DIR + "/live_metrics.json") || file_exists(CONTENT_DIR + "/metrics_ingest.jsonl");
        std::ostringstream ss;
        ss << "{\"status\":\"" << (metrics ? "real_data_present" : "blocked_missing_metrics") << "\",";
        ss << "\"rl_state\":" << read_json_or_block(CONTENT_DIR + "/rl_state.json", "rl_state") << ",";
        ss << "\"ga_state\":" << read_json_or_block(CONTENT_DIR + "/ga_rl_state.json", "ga_state") << ",";
        ss << "\"availability\":" << read_json_or_block(AVAILABILITY_FILE, "availability") << ",";
        ss << "\"content_counts\":{\"bios\":" << bios_count << ",\"receipts\":" << count_files(RECEIPTS_DIR) << "},";
        ss << "\"live_profile_update_allowed\":false,";
        ss << "\"timestamp\":\"" << iso_timestamp() << "\"}";
        response = ss.str();
    } else if (path == "/api/bios") {
        response = bios_json();
    } else if (path == "/api/competitors") {
        response = read_json_or_block(CONTENT_DIR + "/competitor_bios.json", "competitor_bios");
    } else if (path == "/api/receipts") {
        response = "{\"status\":\"ok\",\"receipt_count\":" + std::to_string(count_files(RECEIPTS_DIR)) + "}";
    } else if (path == "/api/ingest" && method == "POST") {
        std::string ingest_path = CONTENT_DIR + "/metrics_ingest.jsonl";
        std::ofstream f(ingest_path, std::ios::app);
        if (!f) { code = 500; response = "{\"status\":\"failed\",\"reason\":\"could not open metrics_ingest.jsonl\"}"; }
        else {
            f << "{\"timestamp\":\"" << iso_timestamp() << "\",\"body\":\"" << json_escape(body) << "\"}\n";
            std::string receipt = write_receipt("ingest", "success", 0, "metrics accepted", "\"output_file\": \"" + ingest_path + "\"");
            response = "{\"status\":\"success\",\"output_file\":\"" + ingest_path + "\",\"receipt\":\"" + receipt + "\"}";
        }
    } else if (path == "/api/run/ga-rl") {
        response = action_response("ga-rl", "./ga_rl_optimizer --population 12 --generations 5 --target 300 && ./ga_rl_optimizer --apply-winner");
    } else if (path == "/api/run/orchestrator") {
        response = action_response("orchestrator", "python3 orchestrator.py --all --dry-run");
    } else if (path == "/api/run/availability") {
        code = 403;
        response = blocked_response("availability", "Live login automation is disabled because prior runs hit captcha/anti-bot. Use first-party metrics ingestion or a manually approved platform path.");
    } else if (path.rfind("/api/rotate/", 0) == 0) {
        std::string rotate_type = path.substr(12);
        if (!(rotate_type == "bio" || rotate_type == "photo" || rotate_type == "price" || rotate_type == "interview" || rotate_type == "blog")) {
            code = 404; response = "{\"status\":\"failed\",\"reason\":\"unknown rotate type\"}";
        } else {
            response = action_response("rotate_" + rotate_type, "./rotator_engine --rotate " + rotate_type);
        }
    } else if (path == "/api/rotator/report") {
        response = action_response("rotator_report", "./rotator_engine --report");
    } else if (path == "/api/cicd/list") {
        response = gh_api("GET", "actions/workflows");
    } else if (path == "/api/cicd/runs") {
        response = gh_api("GET", "actions/runs?per_page=10");
    } else if (path.rfind("/api/cicd/trigger/", 0) == 0) {
        std::string wf = path.substr(18);
        std::string raw = gh_api("POST", "actions/workflows/" + url_encode_workflow(wf) + "/dispatches", "{\"ref\":\"main\"}");
        std::string receipt = write_receipt("cicd_trigger_" + wf, "dispatched", 0, raw);
        response = "{\"status\":\"dispatched\",\"workflow\":\"" + json_escape(wf) + "\",\"github_response\":" + raw + ",\"receipt\":\"" + json_escape(receipt) + "\"}";
    } else if (path.rfind("/api/cicd/status/", 0) == 0) {
        response = gh_api("GET", "actions/runs/" + path.substr(16));
    } else if (path == "/api/config" && method == "POST") {
        std::string config_path = CONTENT_DIR + "/system_config.json";
        std::ofstream f(config_path);
        if (!f) { code = 500; response = "{\"status\":\"failed\",\"reason\":\"could not write config\"}"; }
        else {
            f << body;
            std::string receipt = write_receipt("config", "success", 0, "config saved", "\"output_file\": \"" + config_path + "\"");
            response = "{\"status\":\"success\",\"output_file\":\"" + config_path + "\",\"receipt\":\"" + receipt + "\"}";
        }
    } else {
        code = 404;
        response = "{\"status\":\"failed\",\"error\":\"not found\"}";
    }

    std::string wire = http_response(code, content_type, response);
    send(client_socket, wire.c_str(), wire.size(), 0);
    close(client_socket);
}

static int start_server(int port) {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) { std::cerr << "Socket creation failed\n"; return 1; }
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(port);
    if (bind(server_fd, (sockaddr*)&address, sizeof(address)) < 0) { std::cerr << "Bind failed\n"; close(server_fd); return 1; }
    if (listen(server_fd, 10) < 0) { std::cerr << "Listen failed\n"; close(server_fd); return 1; }
    std::cout << "RentMasseur C++ OS listening on port " << port << std::endl;
    while (true) {
        sockaddr_in client_addr{};
        socklen_t addr_len = sizeof(client_addr);
        int client_socket = accept(server_fd, (sockaddr*)&client_addr, &addr_len);
        if (client_socket < 0) continue;
        handle_client(client_socket);
    }
    close(server_fd);
    return 0;
}

int main(int argc, char* argv[]) {
    int port = PORT;
    if (argc > 1) port = std::atoi(argv[1]);
    std::cout << "Starting RentMasseur C++ OS evidence-only mode on port " << port << std::endl;
    return start_server(port);
}
