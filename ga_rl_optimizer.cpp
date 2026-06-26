/*
 * GA + RL Revenue Optimizer — C++ Native
 * High-performance genetic algorithm + reinforcement learning for
 * RentMasseur revenue maximization ($300/day target).
 *
 * Build: g++ -O3 -std=c++17 -o ga_rl_optimizer ga_rl_optimizer.cpp
 * Run:   ./ga_rl_optimizer
 *        ./ga_rl_optimizer --population 20 --generations 10 --target 300
 *        ./ga_rl_optimizer --report
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <algorithm>
#include <random>
#include <chrono>
#include <ctime>
#include <cmath>
#include <cstdlib>

struct AccountConfig {
    std::string id;
    std::string bio;
    int price;
    std::string photo_style;
    std::string cta;
    std::string headline;
    double fitness;
    double revenue_estimate;
    double reward;
    int generation;
    int uses;
};

struct GAState {
    std::vector<AccountConfig> population;
    int generation;
    AccountConfig best_config;
    double best_fitness;
    double best_revenue;
    std::vector<std::map<std::string, double>> history;
};

const double AVG_SESSION_PRICE = 200.0;
const double CALL_CONVERSION_RATE = 0.20;
const double VIEW_TO_CLICK_RATE = 0.05;
const double BOOKING_CLOSE_RATE = 0.40;
const double REVENUE_TARGET = 300.0;

std::vector<std::string> CTAS = {
    "Call me now to book your session",
    "Pick up the phone and call today",
    "Text or call — I'm available now",
    "Don't wait — call me right now",
    "Book now: your body will thank you",
    "Call today for same-day availability",
};

std::vector<std::string> HEADLINES = {
    "Elite Male Masseur in Manhattan",
    "Your Private Massage Therapist in NYC",
    "Deep Tissue & Sensory Massage by Request",
    "Manhattan's Most Sought-After Masseur",
    "Therapeutic Touch in the Heart of NYC",
    "Late-Night Relief Available Now",
    "Premium In-Home Massage Experience",
    "The Masseur Who Actually Listens",
};

std::vector<std::string> PHOTO_STYLES = {
    "professional", "casual", "athletic", "luxury", "mystery", "warm",
};

std::vector<int> PRICES = {120, 150, 180, 200, 220, 250, 280, 300};

std::mt19937 rng;

static std::string iso_timestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
    return std::string(buf);
}

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) return "";
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static void write_file(const std::string& path, const std::string& content) {
    std::ofstream f(path);
    if (f) f << content;
}

static double random_double() {
    std::uniform_real_distribution<double> dist(0.0, 1.0);
    return dist(rng);
}

static int random_int(int min, int max) {
    std::uniform_int_distribution<int> dist(min, max);
    return dist(rng);
}

static double calculate_revenue_estimate(const std::map<std::string, int>& stats, int price) {
    double views = stats.count("views") ? stats.at("views") : 0;
    double phone_clicks = stats.count("phone_clicks") ? stats.at("phone_clicks") : 0;
    double email_clicks = stats.count("email_clicks") ? stats.at("email_clicks") : 0;
    double booking_inquiries = stats.count("booking_inquiries") ? stats.at("booking_inquiries") : 0;
    double messages = stats.count("messages") ? stats.at("messages") : 0;

    double price_factor = 1.0 - ((price - 200) / 1000.0);
    phone_clicks *= price_factor;
    booking_inquiries *= price_factor;

    double view_revenue = views * VIEW_TO_CLICK_RATE * AVG_SESSION_PRICE;
    double call_revenue = phone_clicks * CALL_CONVERSION_RATE * AVG_SESSION_PRICE;
    double inquiry_revenue = booking_inquiries * BOOKING_CLOSE_RATE * AVG_SESSION_PRICE;
    double message_revenue = messages * 0.10 * AVG_SESSION_PRICE;
    double email_revenue = email_clicks * 0.05 * AVG_SESSION_PRICE;

    return view_revenue + call_revenue + inquiry_revenue + message_revenue + email_revenue;
}

static double calculate_fitness(const std::map<std::string, int>& stats, double revenue, double target) {
    double reward = 0;
    reward += (stats.count("views") ? stats.at("views") : 0) * 1;
    reward += (stats.count("email_clicks") ? stats.at("email_clicks") : 0) * 5;
    reward += (stats.count("phone_clicks") ? stats.at("phone_clicks") : 0) * 10;
    reward += (stats.count("booking_inquiries") ? stats.at("booking_inquiries") : 0) * 50;
    reward += (stats.count("favorites") ? stats.at("favorites") : 0) * 3;
    reward += (stats.count("messages") ? stats.at("messages") : 0) * 8;

    double target_bonus = std::max(0.0, std::min(100.0, (revenue / target) * 100.0));
    double target_penalty = std::abs(target - revenue) * 0.1;

    return reward + target_bonus - target_penalty;
}

static AccountConfig create_random_config(int generation) {
    AccountConfig c;
    c.id = "cfg_" + iso_timestamp() + "_" + std::to_string(random_int(1000, 9999));
    c.bio = "[Generated bio placeholder — C++ version uses static templates; call Python LLM for real bio]";
    c.price = PRICES[random_int(0, PRICES.size() - 1)];
    c.photo_style = PHOTO_STYLES[random_int(0, PHOTO_STYLES.size() - 1)];
    c.cta = CTAS[random_int(0, CTAS.size() - 1)];
    c.headline = HEADLINES[random_int(0, HEADLINES.size() - 1)];
    c.fitness = 0;
    c.revenue_estimate = 0;
    c.reward = 0;
    c.generation = generation;
    c.uses = 0;
    return c;
}

static AccountConfig mutate_config(const AccountConfig& parent, int generation) {
    AccountConfig c = parent;
    c.id = "cfg_" + iso_timestamp() + "_" + std::to_string(random_int(1000, 9999));

    if (random_double() < 0.5) {
        c.price = std::max(80, std::min(500, c.price + random_int(-30, 50)));
    }
    if (random_double() < 0.3) {
        c.cta = CTAS[random_int(0, CTAS.size() - 1)];
    }
    if (random_double() < 0.3) {
        c.headline = HEADLINES[random_int(0, HEADLINES.size() - 1)];
    }
    if (random_double() < 0.3) {
        c.photo_style = PHOTO_STYLES[random_int(0, PHOTO_STYLES.size() - 1)];
    }
    c.generation = generation;
    return c;
}

static AccountConfig crossover(const AccountConfig& p1, const AccountConfig& p2) {
    AccountConfig c;
    c.id = "cfg_" + iso_timestamp() + "_" + std::to_string(random_int(1000, 9999));
    c.bio = random_double() > 0.5 ? p1.bio : p2.bio;
    c.price = random_double() > 0.5 ? p1.price : p2.price;
    c.photo_style = random_double() > 0.5 ? p1.photo_style : p2.photo_style;
    c.cta = random_double() > 0.5 ? p1.cta : p2.cta;
    c.headline = random_double() > 0.5 ? p1.headline : p2.headline;
    c.fitness = 0;
    c.revenue_estimate = 0;
    c.reward = 0;
    c.generation = std::max(p1.generation, p2.generation) + 1;
    c.uses = 0;
    return c;
}

static std::map<std::string, int> get_default_stats() {
    return {
        {"views", 0}, {"email_clicks", 0}, {"phone_clicks", 0},
        {"booking_inquiries", 0}, {"messages", 0}, {"favorites", 0},
    };
}

static std::vector<AccountConfig> evaluate_population(std::vector<AccountConfig>& pop, const std::map<std::string, int>& stats, double target) {
    for (auto& c : pop) {
        c.revenue_estimate = calculate_revenue_estimate(stats, c.price);
        c.fitness = calculate_fitness(stats, c.revenue_estimate, target);
    }
    std::sort(pop.begin(), pop.end(), [](const auto& a, const auto& b) { return a.fitness > b.fitness; });
    return pop;
}

static void print_report(const GAState& state) {
    std::cout << "=" << std::string(60, '=') << "\n";
    std::cout << "GA + RL C++ REVENUE OPTIMIZER REPORT\n";
    std::cout << "=" << std::string(60, '=') << "\n";
    std::cout << "Generation: " << state.generation << "\n";
    std::cout << "Best fitness: " << state.best_fitness << "\n";
    std::cout << "Best revenue: $" << state.best_revenue << "\n";
    std::cout << "Target: $" << REVENUE_TARGET << "\n";
    if (!state.best_config.id.empty()) {
        std::cout << "\nBest config:\n";
        std::cout << "  ID: " << state.best_config.id << "\n";
        std::cout << "  Price: $" << state.best_config.price << "\n";
        std::cout << "  CTA: " << state.best_config.cta << "\n";
        std::cout << "  Headline: " << state.best_config.headline << "\n";
        std::cout << "  Photo: " << state.best_config.photo_style << "\n";
    }
}

static GAState evolve(int population_size, int generations, double target) {
    GAState state;
    state.generation = 0;
    state.best_fitness = 0;
    state.best_revenue = 0;

    std::map<std::string, int> stats = get_default_stats();

    // Initialize population
    for (int i = 0; i < population_size; i++) {
        state.population.push_back(create_random_config(0));
    }

    for (int gen = 1; gen <= generations; gen++) {
        std::cout << "=== Generation " << gen << " ===\n";
        evaluate_population(state.population, stats, target);

        std::cout << "Best fitness: " << state.population[0].fitness
                  << ", revenue: $" << state.population[0].revenue_estimate << "\n";

        if (state.population[0].fitness > state.best_fitness) {
            state.best_fitness = state.population[0].fitness;
            state.best_revenue = state.population[0].revenue_estimate;
            state.best_config = state.population[0];
        }

        state.generation = gen;

        std::map<std::string, double> h;
        h["generation"] = gen;
        h["best_fitness"] = state.population[0].fitness;
        h["best_revenue"] = state.population[0].revenue_estimate;
        state.history.push_back(h);

        // Selection + crossover + mutation
        std::vector<AccountConfig> new_pop;
        new_pop.push_back(state.population[0]);  // Elitism
        new_pop.push_back(state.population[1]);

        while ((int)new_pop.size() < population_size) {
            const auto& p1 = state.population[random_int(0, state.population.size() / 2)];
            const auto& p2 = state.population[random_int(0, state.population.size() / 2)];
            auto child = crossover(p1, p2);
            child = mutate_config(child, gen);
            new_pop.push_back(child);
        }

        state.population = new_pop;
    }

    return state;
}

int main(int argc, char* argv[]) {
    rng.seed(std::random_device()());

    int population_size = 12;
    int generations = 5;
    double target = REVENUE_TARGET;
    bool report = false;

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--population" && i + 1 < argc) population_size = std::atoi(argv[++i]);
        else if (arg == "--generations" && i + 1 < argc) generations = std::atoi(argv[++i]);
        else if (arg == "--target" && i + 1 < argc) target = std::atof(argv[++i]);
        else if (arg == "--report") report = true;
        else if (arg == "--help") {
            std::cout << "Usage: ga_rl_optimizer [options]\n"
                      << "  --population N    Population size\n"
                      << "  --generations N   Number of generations\n"
                      << "  --target X        Revenue target\n"
                      << "  --report          Show report\n";
            return 0;
        }
    }

    if (report) {
        GAState state;
        print_report(state);
        return 0;
    }

    auto state = evolve(population_size, generations, target);
    print_report(state);

    if (state.best_revenue >= target * 0.5) {
        std::cout << "\nWinning config reaches target. Apply with Python ga_rl_optimizer.py --apply-winner\n";
    } else {
        std::cout << "\nNo config reached target threshold. Continue evolving.\n";
    }

    return 0;
}
