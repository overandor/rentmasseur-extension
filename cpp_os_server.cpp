/*
 * RentMasseur Operating System — C++ Native HTTP Server
 * Serves glassmorphism landing page + metrics API + triggers native orchestration.
 * Designed to run as a binary inside a Hugging Face Docker Space.
 *
 * Build:
 *   g++ -O3 -std=c++17 -pthread cpp_os_server.cpp -o cpp_os_server
 *
 * Run:
 *   ./cpp_os_server 7860
 *
 * Endpoints:
 *   GET /              — landing page
 *   GET /api/health    — health check
 *   GET /api/report    — operating system report
 *   GET /api/bios      — bio candidates
 *   GET /api/competitors — competitor intelligence
 *   POST /api/ingest   — ingest metrics
 *   GET /api/run/{cmd} — trigger command (orchestrator, availability, ga-rl)
 *   GET /api/cicd/list — list all GitHub Actions workflows
 *   GET /api/cicd/trigger/{workflow} — trigger a GitHub Actions workflow
 *   GET /api/cicd/status/{run_id} — get status of a specific run
 *   GET /api/cicd/runs — list recent workflow runs
 *   GET /api/rotate/{type} — trigger rotator engine (bio, photo, price, interview, blog)
 *   GET /api/rotator/report — full rotator performance report
 *   GET /api/logs — recent server logs
 *   POST /api/config — update system configuration
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <thread>
#include <mutex>
#include <chrono>
#include <ctime>
#include <cstring>
#include <cstdlib>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <dirent.h>
#include <iomanip>

static const int PORT = 7860;
static std::string GH_TOKEN = std::getenv("GH_TOKEN") ? std::getenv("GH_TOKEN") : "";
static std::string GH_REPO = std::getenv("GH_REPO") ? std::getenv("GH_REPO") : "overandor/rentmasseur-extension";
static std::string HF_TOKEN = std::getenv("HF_TOKEN") ? std::getenv("HF_TOKEN") : "";
static std::string HF_SPACE = std::getenv("HF_SPACE_NAME") ? std::getenv("HF_SPACE_NAME") : "josephrw/rentmasseur-optimizer";
static const std::string CONTENT_DIR = "./content";
static const std::string AVAILABILITY_FILE = "./availability.json";

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) return "";
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static std::string iso_timestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
    return std::string(buf);
}

static std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 0x20) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\u%04x", (unsigned char)c);
            out += buf;
        } else out += c;
    }
    return out;
}

static std::string http_response(int code, const std::string& content_type, const std::string& body) {
    std::ostringstream ss;
    ss << "HTTP/1.1 " << code << " OK\r\n";
    ss << "Content-Type: " << content_type << "\r\n";
    ss << "Content-Length: " << body.size() << "\r\n";
    ss << "Access-Control-Allow-Origin: *\r\n";
    ss << "Connection: close\r\n";
    ss << "\r\n";
    ss << body;
    return ss.str();
}

static std::string get_path(const std::string& request) {
    size_t first = request.find(" ");
    if (first == std::string::npos) return "/";
    size_t second = request.find(" ", first + 1);
    if (second == std::string::npos) return "/";
    return request.substr(first + 1, second - first - 1);
}

static std::string get_method(const std::string& request) {
    size_t space = request.find(" ");
    if (space == std::string::npos) return "GET";
    return request.substr(0, space);
}

static std::string get_body(const std::string& request) {
    size_t pos = request.find("\r\n\r\n");
    if (pos == std::string::npos) return "";
    return request.substr(pos + 4);
}

static std::string load_json_or_empty(const std::string& path) {
    std::string content = read_file(path);
    return content.empty() ? "{}" : content;
}

static int count_files(const std::string& dir) {
    int count = 0;
    DIR* d = opendir(dir.c_str());
    if (d) {
        struct dirent* entry;
        while ((entry = readdir(d)) != nullptr) {
            if (entry->d_type == DT_REG) count++;
        }
        closedir(d);
    }
    return count;
}

static std::string run_command(const std::string& cmd) {
    char buffer[128];
    std::string result;
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return "error";
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        result += buffer;
    }
    pclose(pipe);
    return result;
}

static std::string gh_api(const std::string& method, const std::string& endpoint, const std::string& body = "") {
    std::string cmd = "curl -s -X " + method + "";
    cmd += " -H \"Authorization: Bearer " + GH_TOKEN + "\"";
    cmd += " -H \"Accept: application/vnd.github+json\"";
    cmd += " -H \"X-GitHub-Api-Version: 2022-11-28\"";
    if (!body.empty()) {
        cmd += " -d '" + body + "'";
    }
    cmd += " https://api.github.com/repos/" + GH_REPO + "/" + endpoint;
    return run_command(cmd);
}

static std::string url_encode(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == ' ') out += "%20";
        else if (c == '/') out += "%2F";
        else out += c;
    }
    return out;
}

static std::string landing_page() {
    std::string html = R"HTML(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RentMasseur C++ OS</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0f0f2a 100%);
    color: #fff;
    min-height: 100vh;
}
.glass {
    background: rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 24px;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
}
.hero {
    padding: 60px 40px;
    text-align: center;
    background: radial-gradient(ellipse at top, rgba(0, 245, 255, 0.12), transparent 70%);
}
.hero h1 {
    font-size: 52px;
    font-weight: 800;
    margin: 0;
    background: linear-gradient(90deg, #00f5ff, #b026ff, #ff2a6d);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero p {
    font-size: 18px;
    color: rgba(255,255,255,0.6);
    margin-top: 16px;
}
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 24px;
    padding: 0 40px 40px;
}
.card {
    padding: 28px;
    transition: all 0.3s;
}
.card:hover {
    transform: translateY(-6px);
    background: rgba(255, 255, 255, 0.11);
}
.card h3 {
    margin: 0 0 14px 0;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: rgba(255,255,255,0.55);
}
.card .num {
    font-size: 48px;
    font-weight: 800;
    background: linear-gradient(90deg, #00f5ff, #b026ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.card .sub {
    font-size: 14px;
    color: rgba(255,255,255,0.55);
    margin-top: 8px;
}
.actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 14px;
    padding: 0 40px 40px;
}
.btn {
    padding: 14px 28px;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.22);
    background: rgba(255,255,255,0.08);
    color: #fff;
    text-decoration: none;
    font-weight: 600;
    font-size: 14px;
    transition: all 0.2s;
    cursor: pointer;
}
.btn:hover {
    background: rgba(255,255,255,0.18);
    border-color: rgba(255,255,255,0.4);
}
.btn.glow {
    background: linear-gradient(90deg, #00f5ff, #b026ff);
    border: none;
    color: #0a0a1a;
    box-shadow: 0 0 30px rgba(0, 245, 255, 0.3);
}
.btn.glow:hover {
    box-shadow: 0 0 40px rgba(176, 38, 255, 0.4);
}
.section {
    padding: 0 40px 40px;
}
.section h2 {
    font-size: 20px;
    margin-bottom: 18px;
    color: rgba(255,255,255,0.85);
}
pre {
    background: rgba(0,0,0,0.35);
    padding: 20px;
    border-radius: 16px;
    overflow-x: auto;
    font-size: 12px;
    color: rgba(255,255,255,0.75);
}
.footer {
    text-align: center;
    padding: 40px;
    font-size: 13px;
    color: rgba(255,255,255,0.35);
}
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    background: rgba(0, 245, 255, 0.15);
    border: 1px solid rgba(0, 245, 255, 0.3);
    color: #00f5ff;
    font-size: 11px;
    font-weight: 600;
    margin-left: 10px;
}
</style>
</head>
<body>
<div class="hero">
    <h1>RentMasseur C++ Operating System</h1>
    <p>Native high-performance orchestration. LLM-driven bio evolution. Auto-redeploying CI/CD.</p>
    <span class="badge">LIVE</span>
</div>
<div class="grid">
    <div class="card glass">
        <h3>Revenue Estimate</h3>
        <div class="num" id="revenue">$0</div>
        <div class="sub">Evolving toward $300/day</div>
    </div>
    <div class="card glass">
        <h3>24/7 Availability</h3>
        <div class="num">ON</div>
        <div class="sub">Native C++ scheduler</div>
    </div>
    <div class="card glass">
        <h3>Bio Candidates</h3>
        <div class="num" id="bios">0</div>
        <div class="sub">LLM-generated & scored</div>
    </div>
    <div class="card glass">
        <h3>GA Generations</h3>
        <div class="num" id="generations">0</div>
        <div class="sub">Continuous optimization</div>
    </div>
</div>
<div class="section">
    <h2>Pipeline Control</h2>
    <div class="glass" style="padding: 20px;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">
            <a href="/api/run/ga-rl" class="btn glow">Train GA+RL</a>
            <a href="/api/run/orchestrator" class="btn">Run Orchestrator</a>
            <a href="/api/run/availability" class="btn">Run Availability</a>
            <a href="/api/rotate/bio" class="btn">Rotate Bio</a>
            <a href="/api/rotate/photo" class="btn">Rotate Photo</a>
            <a href="/api/rotate/price" class="btn">Rotate Price</a>
            <a href="/api/rotate/interview" class="btn">Rotate Interview</a>
            <a href="/api/rotate/blog" class="btn">Rotate Blog</a>
            <a href="/api/rotator/report" class="btn">Rotator Report</a>
        </div>
    </div>
</div>
<div class="section">
    <h2>CI/CD Control <span class="badge">GitHub Actions</span></h2>
    <div class="glass" style="padding: 20px;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px;">
            <a href="/api/cicd/list" class="btn">List Workflows</a>
            <a href="/api/cicd/runs" class="btn">Recent Runs</a>
            <a href="/api/cicd/trigger/deploy-hf-space.yml" class="btn glow">Deploy HF Space</a>
            <a href="/api/cicd/trigger/master-rotator.yml" class="btn">Master Rotator</a>
            <a href="/api/cicd/trigger/availability-keeper.yml" class="btn">Availability Keeper</a>
            <a href="/api/cicd/trigger/auto-bio-update.yml" class="btn">Auto Bio Update</a>
            <a href="/api/cicd/trigger/daily-content.yml" class="btn">Daily Content</a>
            <a href="/api/cicd/trigger/weekly-report.yml" class="btn">Weekly Report</a>
        </div>
        <pre id="cicd">Loading CI/CD status...</pre>
    </div>
</div>
<div class="section">
    <h2>Operating System State</h2>
    <div class="glass" style="padding: 20px;">
        <pre id="state">Loading...</pre>
    </div>
</div>
<div class="section">
    <h2>API Reference</h2>
    <div class="glass" style="padding: 20px;">
        <pre style="font-size:11px;line-height:1.6;">
GET  /                      Landing page (this UI)
GET  /health                Health check
GET  /api/health            Health check (JSON)
GET  /api/report            Full OS report
GET  /api/bios              Bio candidates
GET  /api/competitors       Competitor intelligence
POST /api/ingest            Ingest metrics (JSON body)
GET  /api/run/ga-rl         Train GA+RL optimizer
GET  /api/run/orchestrator  Run orchestrator pipeline
GET  /api/run/availability  Run availability keeper
GET  /api/rotate/bio        Rotate bio content
GET  /api/rotate/photo      Rotate photo
GET  /api/rotate/price      Rotate price
GET  /api/rotate/interview  Rotate interview content
GET  /api/rotate/blog       Rotate blog content
GET  /api/rotator/report    Full rotator performance report
GET  /api/cicd/list         List GitHub Actions workflows
GET  /api/cicd/runs         List recent workflow runs
GET  /api/cicd/trigger/{wf} Trigger a workflow by filename
GET  /api/cicd/status/{id}  Get status of a specific run
POST /api/config            Update system config (JSON body)
        </pre>
    </div>
</div>
<div class="footer">
    RentMasseur C++ OS · Hugging Face Space · Vercel · GitHub Actions · Full CI/CD Control
</div>
<script>
fetch('/api/report').then(r => r.json()).then(data => {
    document.getElementById('state').textContent = JSON.stringify(data, null, 2);
    document.getElementById('revenue').textContent = '$' + (data.ga_state?.best_revenue || 0).toFixed(0);
    document.getElementById('bios').textContent = data.content_counts?.bios || 0;
    document.getElementById('generations').textContent = data.ga_state?.generation || 0;
});
fetch('/api/cicd/runs').then(r => r.json()).then(data => {
    document.getElementById('cicd').textContent = JSON.stringify(data, null, 2);
}).catch(e => {
    document.getElementById('cicd').textContent = 'CI/CD runs loading...';
});
</script>
</body>
</html>)HTML";
    return html;
}

static void handle_client(int client_socket) {
    char buffer[8192];
    int received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
    if (received <= 0) {
        close(client_socket);
        return;
    }
    buffer[received] = '\0';
    std::string request(buffer);
    std::string method = get_method(request);
    std::string path = get_path(request);
    std::string body = get_body(request);

    std::string response;
    std::string content_type = "application/json";

    if (path == "/" || path == "/index.html") {
        response = landing_page();
        content_type = "text/html";
    } else if (path == "/health" || path == "/api/health") {
        response = "{\"status\":\"ok\",\"service\":\"rentmasseur-cpp-os\",\"timestamp\":\"" + iso_timestamp() + "\"}";
    } else if (path == "/api/report") {
        std::ostringstream ss;
        ss << "{\"rl_state\":" << load_json_or_empty(CONTENT_DIR + "/rl_state.json") << ",";
        ss << "\"ga_state\":" << load_json_or_empty(CONTENT_DIR + "/ga_rl_state.json") << ",";
        ss << "\"availability\":" << load_json_or_empty(AVAILABILITY_FILE) << ",";
        ss << "\"content_counts\":{\"bios\":" << count_files(CONTENT_DIR + "/bios") << "},";
        ss << "\"timestamp\":\"" << iso_timestamp() << "\"}";
        response = ss.str();
    } else if (path == "/api/bios") {
        response = "{\"bios\":[]}";
    } else if (path == "/api/competitors") {
        response = load_json_or_empty(CONTENT_DIR + "/competitor_bios.json");
    } else if (path == "/api/ingest" && method == "POST") {
        std::string ingest_path = CONTENT_DIR + "/metrics_ingest.jsonl";
        std::ofstream f(ingest_path, std::ios::app);
        if (f) {
            f << "{\"timestamp\":\"" << iso_timestamp() << "\",\"body\":\"" << json_escape(body) << "\"}" << "\n";
        }
        response = "{\"status\":\"ingested\"}";
    } else if (path == "/api/run/ga-rl") {
        std::thread([]() {
            run_command("./ga_rl_optimizer --population 12 --generations 5 --target 300");
            run_command("./ga_rl_optimizer --apply-winner");
        }).detach();
        response = "{\"status\":\"started\",\"command\":\"ga+rl\"}";
    } else if (path == "/api/run/orchestrator") {
        std::thread([]() {
            run_command("python3 orchestrator.py");
        }).detach();
        response = "{\"status\":\"started\",\"command\":\"orchestrator\"}";
    } else if (path == "/api/run/availability") {
        std::thread([]() {
            run_command("python3 rentmasseur_availability.py --once --headless true");
        }).detach();
        response = "{\"status\":\"started\",\"command\":\"availability\"}";
    } else if (path.rfind("/api/rotate/", 0) == 0) {
        std::string rotate_type = path.substr(12);
        std::string cmd = "./rotator_engine --rotate " + rotate_type;
        std::thread([cmd]() { run_command(cmd); }).detach();
        response = "{\"status\":\"started\",\"command\":\"rotate " + rotate_type + "\"}";
    } else if (path == "/api/rotator/report") {
        response = run_command("./rotator_engine --report");
        if (response.empty() || response == "error") response = "{\"rotator\":\"offline\",\"content_dir\":\"" + CONTENT_DIR + "\"}";
    } else if (path == "/api/cicd/list") {
        if (GH_TOKEN.empty()) {
            response = "{\"error\":\"GH_TOKEN not set\"}";
        } else {
            response = gh_api("GET", "actions/workflows");
        }
    } else if (path == "/api/cicd/runs") {
        if (GH_TOKEN.empty()) {
            response = "{\"error\":\"GH_TOKEN not set\"}";
        } else {
            response = gh_api("GET", "actions/runs?per_page=10");
        }
    } else if (path.rfind("/api/cicd/trigger/", 0) == 0) {
        std::string wf = path.substr(18);
        if (GH_TOKEN.empty()) {
            response = "{\"error\":\"GH_TOKEN not set\"}";
        } else {
            std::string encoded = url_encode(wf);
            response = gh_api("POST", "actions/workflows/" + encoded + "/dispatches", "{\"ref\":\"main\"}");
            if (response.empty()) response = "{\"status\":\"triggered\",\"workflow\":\"" + wf + "\"}";
        }
    } else if (path.rfind("/api/cicd/status/", 0) == 0) {
        std::string run_id = path.substr(16);
        if (GH_TOKEN.empty()) {
            response = "{\"error\":\"GH_TOKEN not set\"}";
        } else {
            response = gh_api("GET", "actions/runs/" + run_id);
        }
    } else if (path == "/api/config" && method == "POST") {
        std::string config_path = CONTENT_DIR + "/system_config.json";
        std::ofstream f(config_path);
        if (f) f << body;
        response = "{\"status\":\"saved\",\"config\":\"" + json_escape(body) + "\"}";
    } else {
        response = "{\"error\":\"not found\"}";
        response = http_response(404, content_type, response);
        send(client_socket, response.c_str(), response.size(), 0);
        close(client_socket);
        return;
    }

    response = http_response(200, content_type, response);
    send(client_socket, response.c_str(), response.size(), 0);
    close(client_socket);
}

static int start_server(int port) {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        std::cerr << "Socket creation failed" << std::endl;
        return 1;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in address;
    std::memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(port);

    if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) {
        std::cerr << "Bind failed" << std::endl;
        close(server_fd);
        return 1;
    }

    if (listen(server_fd, 10) < 0) {
        std::cerr << "Listen failed" << std::endl;
        close(server_fd);
        return 1;
    }

    std::cout << "RentMasseur C++ OS listening on port " << port << std::endl;

    while (true) {
        struct sockaddr_in client_addr;
        socklen_t addr_len = sizeof(client_addr);
        int client_socket = accept(server_fd, (struct sockaddr*)&client_addr, &addr_len);
        if (client_socket < 0) continue;

        std::thread([client_socket]() {
            handle_client(client_socket);
        }).detach();
    }

    close(server_fd);
    return 0;
}

int main(int argc, char* argv[]) {
    int port = PORT;
    if (argc > 1) {
        port = std::atoi(argv[1]);
    }

    std::cout << "Starting RentMasseur C++ OS on port " << port << std::endl;
    return start_server(port);
}
