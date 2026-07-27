#include "timewalk.h"

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
    return entry->get<double>();
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

    if (model == "inverse") {
        correction.model = TimewalkCorrection::Model::kInverse;
        correction.a = requiredParameter(parameters, "a", "inverse");
        correction.b = requiredParameter(parameters, "b", "inverse");
    } else if (model == "linear") {
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = requiredParameter(parameters, "m", "linear");
    } else {
        throw std::runtime_error(
            "time-walk correction has unknown model '" + model +
            "' (expected 'inverse' or 'linear')");
    }

    return correction;
}

double correctedToa(std::uint64_t raw_toa,
                    std::uint16_t tot_raw,
                    const TimewalkCorrection& correction) {
    const double tot = static_cast<double>(tot_raw);
    const double anchor = correction.high_tot_anchor;
    double delta_t = 0.0;
    if (correction.model == TimewalkCorrection::Model::kInverse) {
        delta_t = correction.a *
                  (1.0 / (tot + correction.b) - 1.0 / (anchor + correction.b));
    } else {
        delta_t = correction.m * (tot - anchor);
    }
    return static_cast<double>(raw_toa) - delta_t;
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
