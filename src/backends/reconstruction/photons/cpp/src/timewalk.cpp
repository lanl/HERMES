#include "timewalk.h"

#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

namespace hermes_photon_clusterer {

namespace {

double requiredParameter(const nlohmann::json& parameters,
                         const std::string& key,
                         const std::string& model_name) {
    const auto entry = parameters.find(key);
    if (entry == parameters.end() || !entry->is_number()) {
        throw std::runtime_error("time-walk correction " + model_name +
                                 " model requires numeric parameter '" + key +
                                 "'");
    }
    const double value = entry->get<double>();
    if (!std::isfinite(value)) {
        throw std::runtime_error("time-walk parameter '" + key + "' must be finite");
    }
    return value;
}

}  // namespace

TimewalkCorrection loadTimewalkCorrection(const std::string& path) {
    std::ifstream input(path);
    if (!input.is_open()) {
        throw std::runtime_error("cannot open time-walk correction file: " +
                                 path);
    }

    nlohmann::json document;
    try {
        input >> document;
    } catch (const nlohmann::json::exception& error) {
        throw std::runtime_error("malformed time-walk correction JSON in " +
                                 path + ": " + error.what());
    }

    if (!document.is_object()) {
        throw std::runtime_error("time-walk correction must be a JSON object: " +
                                 path);
    }

    const auto time_unit = document.value("time_unit", std::string{});
    if (time_unit != "canonical_ticks") {
        throw std::runtime_error(
            "time-walk correction time_unit must be 'canonical_ticks', got '" +
            time_unit + "'");
    }

    if (!document.contains("model") || !document["model"].is_string()) {
        throw std::runtime_error(
            "time-walk correction requires a string 'model' field");
    }
    if (!document.contains("parameters") ||
        !document["parameters"].is_object()) {
        throw std::runtime_error(
            "time-walk correction requires a 'parameters' object");
    }
    if (!document.contains("high_tot_anchor") ||
        !document["high_tot_anchor"].is_number()) {
        throw std::runtime_error(
            "time-walk correction requires a numeric 'high_tot_anchor'");
    }

    const std::string model = document["model"].get<std::string>();
    const nlohmann::json& parameters = document["parameters"];

    TimewalkCorrection correction;
    correction.high_tot_anchor = document["high_tot_anchor"].get<double>();
    if (!std::isfinite(correction.high_tot_anchor) ||
        correction.high_tot_anchor < 0.0 || correction.high_tot_anchor > 1023.0) {
        throw std::runtime_error("time-walk high_tot_anchor must be finite and in 0-1023");
    }

    if (model == "inverse") {
        correction.model = TimewalkCorrection::Model::kInverse;
        correction.a = requiredParameter(parameters, "a", "inverse");
        correction.b = requiredParameter(parameters, "b", "inverse");
        if (correction.b <= 0.0 && correction.b >= -1023.0) {
            throw std::runtime_error(
                "inverse time-walk curve has a pole in ToT range 0-1023");
        }
    } else if (model == "linear") {
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = requiredParameter(parameters, "m", "linear");
    } else {
        throw std::runtime_error(
            "time-walk correction has unknown model '" + model +
            "' (expected 'inverse' or 'linear')");
    }

    for (std::uint16_t tot = 0; tot <= 1023; ++tot) {
        timewalkDelay(tot, correction);
    }
    return correction;
}

double timewalkDelay(std::uint16_t tot_raw,
                     const TimewalkCorrection& correction) {
    if (tot_raw > 1023) {
        throw std::runtime_error("time-walk ToT must be in 0-1023");
    }
    const double tot = static_cast<double>(tot_raw);
    const double anchor = correction.high_tot_anchor;
    double delta_t = 0.0;
    if (correction.model == TimewalkCorrection::Model::kInverse) {
        delta_t = correction.a *
                  (1.0 / (tot + correction.b) - 1.0 / (anchor + correction.b));
    } else {
        delta_t = correction.m * (tot - anchor);
    }
    if (!std::isfinite(delta_t)) {
        throw std::runtime_error("time-walk correction must be finite");
    }
    return delta_t;
}

double correctedToa(std::uint64_t raw_toa,
                    std::uint16_t tot_raw,
                    const TimewalkCorrection& correction) {
    return static_cast<double>(raw_toa) - timewalkDelay(tot_raw, correction);
}

double earliestCorrectedToa(const PixelCluster& cluster,
                            const TimewalkCorrection& correction) {
    bool first = true;
    double earliest = 0.0;
    for (const auto& hit : cluster.hits) {
        const double corrected =
            correctedToa(hit.timestamp_canonical, hit.tot_raw, correction);
        if (first || corrected < earliest) {
            earliest = corrected;
            first = false;
        }
    }
    return earliest;
}

}  // namespace hermes_photon_clusterer
